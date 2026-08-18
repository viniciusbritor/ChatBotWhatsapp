"""LLM provider: DeepSeek V4 Flash (single provider).

Every agent in the runtime uses DeepSeek V4 Flash through ``chat()``
and ``chat_with_tools()``. The default model is ``deepseek-v4-flash``
and the endpoint is OpenAI-compatible (``/chat/completions``), so native
``tool_calls`` are returned in the structured field without any inline parser.

GUARDRAIL (18/08/2026): LLM unico = DeepSeek. O Groq LLM (Llama 3.x) foi
removido do provider. O Groq permanece apenas para STT (Whisper) em
``core.audio_transcribe`` (custo zero, latencia baixa). Codigo Groq LLM
removido para reduzir superficie de erro e eliminar o cascade com timeout
sistematico do Groq (erro "'ascii' codec can't encode").

Audio transcription is intentionally NOT handled here; it lives in
``core.audio_transcribe`` and uses Groq Whisper (free tier, ~1-2s latencia).
"""
import os
import json
import time
import random
import logging
from typing import Dict, Any, List, Optional

import httpx

from core.secrets import get_secret

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the DeepSeek provider fails."""
    pass


class LLMProvider:
    """Single-provider client: DeepSeek V4 Flash (OpenAI-compatible API)."""

    DEFAULT_MODEL = "deepseek-v4-flash"
    DEFAULT_BASE_URL = "https://api.deepseek.com"
    PROVIDER_TAG = "deepseek-v4-flash"

    def __init__(self):
        self.deepseek_key = get_secret("DEEPSEEK_API_KEY")
        self.deepseek_base = os.getenv("DEEPSEEK_BASE_URL", self.DEFAULT_BASE_URL)
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", self.DEFAULT_MODEL)

    def is_available(self) -> bool:
        return bool(self.deepseek_key)

    def _backoff_sleep(self, attempt: int, base: float = 1.0, cap: float = 30.0):
        delay = min(cap, base * (2 ** attempt)) + random.uniform(0, 0.5)
        time.sleep(delay)

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.deepseek_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_MODEL,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call DeepSeek V4 Flash. Provider arg ignorado (legado do cascade)."""
        if not self.deepseek_key:
            raise LLMError("deepseek_key_not_configured")

        url = f"{self.deepseek_base}/chat/completions"
        sys_content = system_prompt or ""
        if json_mode and "json" not in sys_content.lower():
            sys_content = "JSON: " + sys_content
        payload = {
            "model": self.deepseek_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": user_prompt},
            ],
            "cache_mode": "default",
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, headers=self._build_headers(), json=payload)
        if resp.status_code == 429:
            raise LLMError("deepseek_quota_exceeded")
        if resp.status_code == 401:
            raise LLMError("deepseek_auth_failed")
        if resp.status_code >= 500:
            raise LLMError(f"deepseek_server_error_{resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise LLMError("deepseek_empty_response")
        content = data["choices"][0]["message"].get("content", "") or ""
        usage = data.get("usage") or {}
        cache_hit = int(
            usage.get("prompt_cache_hit_tokens", 0)
            or (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            or 0
        )
        return {
            "content": content,
            "model_used": data.get("model", self.deepseek_model),
            "provider": self.PROVIDER_TAG,
            "attempts": [f"{self.PROVIDER_TAG}:success"],
            "usage": {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
                "cache_hit_tokens": cache_hit,
            },
        }

    async def chat_escalating(
        self,
        system_prompt: str,
        user_prompt: str,
        fast_model: str = DEFAULT_MODEL,
        pro_model: str = "",
        threshold: int = -2,
        no_escalation: bool = True,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
        scoring_fn=None,
    ) -> Dict[str, Any]:
        """Alias for ``chat()``. Accepted for caller compatibility; the
        signature is preserved but only DeepSeek v4-flash is used
        regardless of the ``fast_model`` / ``pro_model`` arguments.
        """
        result = await self.chat(
            system_prompt, user_prompt, fast_model, json_mode, temperature, max_tokens, thinking_disabled
        )
        result["escalated"] = False
        return result

    @staticmethod
    def parse_tool_calls(response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        choices = response_data.get("choices", [])
        if not choices:
            return []
        msg = choices[0].get("message", {})
        return msg.get("tool_calls", []) or []

    async def chat_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        tool_executor=None,
        model: str = DEFAULT_MODEL,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
        max_tool_rounds: int = 5,
    ) -> Dict[str, Any]:
        """Native OpenAI-compatible tool calling. ``tool_calls`` arrive in the
        structured field; no inline parser is required.

        Tool names use ``resource.method`` convention (e.g. ``calendar.list_events``).
        DeepSeek v4-flash rejects tool names containing a dot with HTTP 400,
        so we transparently rewrite ``.`` -> ``_`` on the wire and translate
        back when the model calls the tool.
        """
        if not self.deepseek_key:
            raise LLMError("deepseek_key_not_configured")

        url = f"{self.deepseek_base}/chat/completions"
        model_id = self.deepseek_model
        headers = self._build_headers()
        provider_tag = self.PROVIDER_TAG

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        tool_count = 0
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        wire_to_real: Dict[str, str] = {}
        if tools:
            wire_tools = []
            for tool in tools:
                fn = tool.get("function", {}) if isinstance(tool, dict) else {}
                real_name = fn.get("name", "")
                wire_name = real_name.replace(".", "_")
                if wire_name != real_name:
                    wire_to_real[wire_name] = real_name
                wire_tools.append({
                    "type": tool.get("type", "function"),
                    "function": {**fn, "name": wire_name},
                })
            tools = wire_tools

        while tool_count < max_tool_rounds:
            payload = {
                "model": model_id,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": messages,
                "cache_mode": "default",
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            if tools:
                payload["tools"] = tools
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 429:
                raise LLMError("deepseek_quota_exceeded")
            if resp.status_code == 401:
                raise LLMError("deepseek_auth_failed")
            if resp.status_code >= 500:
                raise LLMError(f"deepseek_server_error_{resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            round_usage = data.get("usage") or {}
            total_usage["prompt_tokens"] += int(round_usage.get("prompt_tokens", 0) or 0)
            total_usage["completion_tokens"] += int(round_usage.get("completion_tokens", 0) or 0)
            total_usage["total_tokens"] += int(round_usage.get("total_tokens", 0) or 0)
            cache_hit = int(
                round_usage.get("prompt_cache_hit_tokens", 0)
                or (round_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                or 0
            )
            if cache_hit:
                total_usage["cache_hit_tokens"] = total_usage.get("cache_hit_tokens", 0) + cache_hit
            if not choices:
                return {
                    "content": "Resposta vazia do LLM.",
                    "model_used": model_id,
                    "tool_rounds": tool_count,
                    "provider": provider_tag,
                    "usage": total_usage,
                }
            msg = choices[0].get("message", {})
            content = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return {
                    "content": content,
                    "model_used": model_id,
                    "tool_rounds": tool_count,
                    "provider": provider_tag,
                    "usage": total_usage,
                }
            for tc in tool_calls:
                func = tc.get("function", {})
                wire_name = func.get("name", "")
                real_name = wire_to_real.get(wire_name, wire_name)
                func["name"] = real_name
            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    safe_args = {k: str(v)[:120] for k, v in args.items()}
                except Exception:
                    args = {}
                    safe_args = {"raw": args_str[:120]}
                logger.info("tool_start round=%d tool=%s args=%s", tool_count + 1, name, safe_args)
                try:
                    if tool_executor:
                        tool_result = await tool_executor(name, args)
                    else:
                        tool_result = json.dumps({"error": "tool_executor_not_configured"})
                except Exception as e:
                    tool_result = json.dumps({"error": str(e)})

                # Truncate payload to 1500 chars to avoid prompt token explosion across rounds
                raw_tool_content = str(tool_result) if isinstance(tool_result, str) else json.dumps(tool_result)
                if len(raw_tool_content) > 1500:
                    truncated_content = raw_tool_content[:1500] + "... [truncado para economia de tokens]"
                else:
                    truncated_content = raw_tool_content

                result_preview = truncated_content[:200]
                logger.info("tool_result round=%d tool=%s result=%s", tool_count + 1, name, result_preview)
                messages.append({
                    "role": "tool",
                    "content": truncated_content,
                    "tool_call_id": tc.get("id", ""),
                })
            tool_count += 1

        logger.warning("tool_loop_exhausted rounds=%d", tool_count)
        try:
            fallback_prompt = (
                "Voce atingiu o limite de chamadas de ferramentas. "
                "Responda agora em portugues, 1-2 frases, com base SOMENTE nos tool_results abaixo. "
                "Se faltarem dados, diga ao usuario o que conseguiu obter. NAO invente nada.\n\n"
                "Tool results acumulados:\n"
            )
            for m in messages[-8:]:
                if m.get("role") == "tool":
                    content = str(m.get("content", ""))[:500]
                    fallback_prompt += f"\n- {content}\n"
            return await self.chat(
                system_prompt="Voce e a Jennifer, assistente que responde com concisao.",
                user_prompt=fallback_prompt,
                model=model_id,
                temperature=0.5,
                max_tokens=300,
            )
        except Exception as fallback_exc:
            logger.error("fallback_chat_failed exc=%s", fallback_exc)
            return {
                "content": "Maximo de execucoes atingido.",
                "model_used": model_id,
                "tool_rounds": tool_count,
                "provider": self.PROVIDER_TAG,
                "usage": total_usage,
            }

    async def transcribe_audio_base64(self, audio_b64: str, mimetype: str = "audio/ogg") -> str:
        from tools.audio_transcribe import transcribe_base64

        try:
            result = await transcribe_base64(audio_b64, mimetype)
            return result.get("transcript", "")
        except Exception as exc:
            logger.warning("Local audio transcription failed: %s", type(exc).__name__)
            return "[audio]"

    async def transcribe_audio(self, audio_url: str, mimetype: str = "audio/ogg") -> str:
        from tools.audio_transcribe import transcribe_url

        try:
            result = await transcribe_url(audio_url, mimetype)
            return result.get("transcript", "")
        except Exception as exc:
            logger.warning("Local audio URL transcription failed: %s", type(exc).__name__)
            return "[audio]"
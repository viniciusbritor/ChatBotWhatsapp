"""LLM provider: DeepSeek V4 Flash (single provider, no cascade).

Every agent in the runtime uses DeepSeek V4 Flash through ``chat()``,
``chat_escalating()`` and ``chat_with_tools()``. The default model is
``deepseek-v4-flash`` and the endpoint is OpenAI-compatible
(``/chat/completions``), so native ``tool_calls`` are returned in the
structured field without any inline parser.

Audio transcription is intentionally NOT handled here; it lives in
``core.audio_transcribe`` and uses Gemini 2.5 Flash directly.
"""
import os
import json
import time
import random
import logging
from typing import Optional, Dict, Any, List

import httpx

from core.secrets import get_secret

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the DeepSeek provider fails."""
    pass


class LLMProvider:
    """DeepSeek V4 Flash client. OpenAI-compatible API."""

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
    ) -> Dict[str, Any]:
        """Single call to DeepSeek V4 Flash. No cascade. The ``model`` arg is
        accepted for backward compatibility but always resolves to
        ``self.deepseek_model`` (env-configurable via ``DEEPSEEK_MODEL``)."""
        if not self.deepseek_key:
            raise LLMError("deepseek_key_not_configured")
        url = f"{self.deepseek_base}/chat/completions"
        payload = {
            "model": self.deepseek_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "thinking": {"type": "disabled"} if thinking_disabled else {"type": "enabled"},
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
        return {
            "content": content,
            "model_used": data.get("model", self.deepseek_model),
            "provider": self.PROVIDER_TAG,
            "attempts": [f"{self.PROVIDER_TAG}:success"],
        }

    async def chat_escalating(
        self,
        system_prompt: str,
        user_prompt: str,
        fast_model: str = DEFAULT_MODEL,
        pro_model: str = DEFAULT_MODEL,
        threshold: int = -2,
        no_escalation: bool = True,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
        scoring_fn=None,
    ) -> Dict[str, Any]:
        """DeepSeek-only. No escalation path. ``fast_model``, ``pro_model``,
        ``threshold`` and ``scoring_fn`` are kept for caller compatibility but
        the method always answers with the single DeepSeek provider."""
        result = await self.chat(
            system_prompt, user_prompt, fast_model, json_mode, temperature, max_tokens, thinking_disabled
        )
        if scoring_fn is not None and not no_escalation:
            try:
                score = scoring_fn(result["content"])
                result["confidence_score"] = score
            except Exception as e:
                logger.warning("scoring_fn_failed: %s", e)
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
        structured field; no inline parser is required."""
        if not self.deepseek_key:
            raise LLMError("deepseek_key_not_configured")
        url = f"{self.deepseek_base}/chat/completions"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        model_id = self.deepseek_model
        tool_count = 0

        while tool_count < max_tool_rounds:
            payload = {
                "model": model_id,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": messages,
                "thinking": {"type": "disabled"} if thinking_disabled else {"type": "enabled"},
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            if tools:
                payload["tools"] = tools
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(url, headers=self._build_headers(), json=payload)
            if resp.status_code == 429:
                raise LLMError("deepseek_quota_exceeded")
            if resp.status_code == 401:
                raise LLMError("deepseek_auth_failed")
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return {
                    "content": "Resposta vazia do LLM.",
                    "model_used": model_id,
                    "tool_rounds": tool_count,
                    "provider": self.PROVIDER_TAG,
                }
            msg = choices[0].get("message", {})
            content = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return {
                    "content": content,
                    "model_used": model_id,
                    "tool_rounds": tool_count,
                    "provider": self.PROVIDER_TAG,
                }
            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    if tool_executor:
                        tool_result = await tool_executor(name, args)
                    else:
                        tool_result = json.dumps({"error": "tool_executor_not_configured"})
                except Exception as e:
                    tool_result = json.dumps({"error": str(e)})
                messages.append({
                    "role": "tool",
                    "content": str(tool_result) if isinstance(tool_result, str) else json.dumps(tool_result),
                    "tool_call_id": tc.get("id", ""),
                })
            tool_count += 1

        return {
            "content": "Maximo de execucoes atingido.",
            "model_used": model_id,
            "tool_rounds": tool_count,
            "provider": self.PROVIDER_TAG,
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

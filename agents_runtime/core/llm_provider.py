"""LLM cascade: MiniMax M2.7-highspeed -> Gemini 2.5 Flash.

Every agent in the runtime uses this cascade through the
``chat()``, ``chat_with_tools()`` and ``chat_escalating()`` entry
points. The defaults are:

- ``fast_model`` (first try): ``MiniMax-M2.7-highspeed``.
- ``pro_model`` (escalation target): ``gemini-2.5-flash``.

Features:
- Cascade fallback on failure (quota, auth, timeout)
- Exponential backoff with jitter
- JSON mode support
- Thinking mode toggle per request
- chat_with_tools handles MiniMax-style tool_call tags emitted inside content
"""
import os
import re
import json
import time
import random
import asyncio
import logging
from typing import Optional, Dict, Any, List

import httpx
import requests
from core.secrets import get_secret

logger = logging.getLogger(__name__)

_MINIMAX_INVOKE_RE = re.compile(
    r'<\s*invoke\s+name="([^"]+)"[^>]*>(.*?)</\s*invoke\s*>',
    re.DOTALL,
)
_MINIMAX_ACTION_RE = re.compile(r'<\s*action\b[^>]*>(.*?)</\s*action\s*>', re.DOTALL)
_MINIMAX_TOOL_CALL_BLOCK_RE = re.compile(r'<\s*tool_call\s*>.*?</\s*tool_call\s*>', re.DOTALL)


def _extract_minimax_tool_calls(content: str) -> tuple:
    """Best-effort extractor for MiniMax-style inline tool calls.

    Some providers return tool invocations embedded in `content` instead of the
    structured `tool_calls` field. Returns (tool_calls_list, cleaned_content).
    """
    if not content:
        return [], content
    invoke_matches = list(_MINIMAX_INVOKE_RE.finditer(content))
    if not invoke_matches:
        return [], content

    cleaned = content
    tool_calls: List[Dict[str, Any]] = []
    for idx, match in enumerate(invoke_matches):
        name = match.group(1).strip()
        inner = match.group(2)
        action = _MINIMAX_ACTION_RE.search(inner)
        args_str = action.group(1).strip() if action else "{}"
        try:
            args = json.loads(args_str) if args_str else {}
            if not isinstance(args, dict):
                args = {"value": args}
        except json.JSONDecodeError:
            args = {"raw": args_str}
        tool_calls.append({
            "id": f"minimax_call_{idx}_{name}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        })
        cleaned = cleaned.replace(match.group(0), "")

    cleaned = _MINIMAX_TOOL_CALL_BLOCK_RE.sub("", cleaned)
    cleaned = re.sub(r'\[\s*<\s*minimax\s*>\s*\[', '', cleaned)
    cleaned = re.sub(r'\]\s*<\s*/?\s*minimax\s*>\s*\]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return tool_calls, cleaned


class LLMError(Exception):
    """Raised when all providers fail."""
    pass


class LLMProvider:
    """Multi-provider LLM client with cascade fallback."""

    def __init__(self):
        self.minimax_key = get_secret("MINIMAX_API_KEY")
        self.gemini_key = get_secret("GEMINI_API_KEY")

        self.minimax_base = os.getenv(
            "MINIMAX_BASE_URL", "https://api.minimax.io/v1"
        )
        self.gemini_base = os.getenv(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"
        )
        self.minimax_model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7-highspeed")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def is_available(self) -> bool:
        return bool(self.minimax_key or self.gemini_key)

    def gemini_available(self) -> bool:
        return bool(self.gemini_key)

    def _backoff_sleep(self, attempt: int, base: float = 1.0, cap: float = 30.0):
        delay = min(cap, base * (2 ** attempt)) + random.uniform(0, 0.5)
        time.sleep(delay)

    def _build_payload(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        thinking_disabled: bool,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if thinking_disabled and ("pro" in model.lower() or "reason" in model.lower()):
            payload["thinking"] = {"type": "disabled"}
        if tools:
            payload["tools"] = tools
        return payload

    def _call_minimax(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not self.minimax_key:
            raise LLMError("minimax_key_not_configured")
        url = f"{self.minimax_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.minimax_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(
            self.minimax_model, system_prompt, user_prompt,
            json_mode, temperature, max_tokens, True,
        )

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        if resp.status_code == 429:
            raise LLMError("minimax_quota_exceeded")
        if resp.status_code == 401:
            raise LLMError("minimax_auth_failed")
        if resp.status_code >= 500:
            raise LLMError(f"minimax_server_error_{resp.status_code}")
        resp.raise_for_status()

        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise LLMError("minimax_empty_response")

        if "base_resp" in data:
            base_resp = data["base_resp"]
            if base_resp.get("status_code", 0) != 0:
                raise LLMError(f"minimax_in_body_error: {base_resp.get('status_msg')}")

        return data["choices"][0]["message"]["content"]

    def _build_cascade_providers(self, model: str, skip_gemini: bool = False):
        """Build interleaved cascade list, skipping providers without keys.

        Cascade order (todos os agentes):
        1. MiniMax M2.7-highspeed (primario)
        2. Gemini 2.5 Flash (fallback)
        """
        providers = []

        if self.minimax_key:
            providers.append(("minimax-hs", "MiniMax-M2.7-highspeed", "_call_minimax", "MiniMax-M2.7-highspeed"))
        if not skip_gemini and self.gemini_key:
            providers.append(("gemini-2.5-flash", "gemini-2.5-flash", "_call_gemini", "gemini-2.5-flash"))

        if not providers:
            raise LLMError("no_provider_keys_configured")

        return providers

    async def _call_gemini(self, model: str, sp, user_prompt, json_mode, temperature, max_tokens, thinking_disabled):
        if not self.gemini_key:
            raise LLMError("gemini_key_not_configured")
        try:
            from google.generativeai import configure as _ga_configure
            from google.generativeai import GenerativeModel
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"gemini_sdk_missing: {exc}")

        _ga_configure(api_key=self.gemini_key)
        gen_model = GenerativeModel(model_name=model)
        system_instruction = sp or ""
        full_prompt = (
            f"{system_instruction}\n\n{user_prompt}" if system_instruction else user_prompt
        )
        generation_config: Dict[str, Any] = {
            "temperature": float(temperature or 0.7),
            "max_output_tokens": int(max_tokens or 1024),
        }
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        response = await asyncio.to_thread(
            gen_model.generate_content,
            full_prompt,
            generation_config=generation_config,
        )
        text = (response.text or "").strip()
        return text

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "MiniMax-M2.7-highspeed",
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
    ) -> Dict[str, Any]:
        """Call LLM with cascade fallback. Async."""
        attempts = []

        cascade = self._build_cascade_providers(model)

        for attempt_idx, (provider_name, provider_model, method_name, call_model) in enumerate(cascade):
            try:
                if method_name == "_call_minimax":
                    content = await asyncio.to_thread(
                        self._call_minimax,
                        system_prompt, user_prompt, json_mode, temperature, max_tokens
                    )
                elif method_name == "_call_gemini":
                    content = await self._call_gemini(
                        call_model, system_prompt, user_prompt,
                        json_mode, temperature, max_tokens, thinking_disabled
                    )
                else:
                    raise LLMError(f"unknown_method: {method_name}")

                attempts.append(f"{provider_name}:success")
                return {
                    "content": content,
                    "model_used": provider_model,
                    "provider": provider_name,
                    "attempts": attempts,
                }
            except LLMError as e:
                attempts.append(f"{provider_name}:{str(e)}")
                logger.warning(f"Provider {provider_name} failed: {e}")
                self._backoff_sleep(attempt_idx)
                continue
            except Exception as e:
                attempts.append(f"{provider_name}:unexpected:{type(e).__name__}")
                logger.exception(f"Unexpected error in {provider_name}")
                continue

        raise LLMError(f"all_providers_failed: {attempts}")

    async def chat_escalating(
        self,
        system_prompt: str,
        user_prompt: str,
        fast_model: str = "MiniMax-M2.7-highspeed",
        pro_model: str = "gemini-2.5-flash",
        threshold: int = -2,
        no_escalation: bool = False,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
        scoring_fn=None,
    ) -> Dict[str, Any]:
        """Try fast (MiniMax) first; if cascade fails or low score, escalate to pro (Gemini)."""
        if no_escalation:
            result = await self.chat(
                system_prompt, user_prompt, fast_model, json_mode, temperature, max_tokens, thinking_disabled
            )
            return {**result, "escalated": False}

        fast_resp = await self.chat(
            system_prompt, user_prompt, fast_model, json_mode, temperature, max_tokens, thinking_disabled
        )
        if scoring_fn is None:
            return {**fast_resp, "escalated": False}
        try:
            score = scoring_fn(fast_resp["content"])
        except Exception as e:
            logger.warning(f"Scoring function failed: {e}")
            return {**fast_resp, "escalated": False}
        if score > threshold:
            return {**fast_resp, "escalated": False, "confidence_score": score}

        logger.info(f"Escalating to {pro_model} (score={score}, threshold={threshold})")
        pro_resp = await self.chat(
            system_prompt, user_prompt, pro_model, json_mode, temperature, max_tokens, thinking_disabled
        )
        return {**pro_resp, "escalated": True, "confidence_score": score, "fast_response": fast_resp}

    @staticmethod
    def parse_tool_calls(response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        choices = response_data.get("choices", [])
        if not choices:
            return []
        msg = choices[0].get("message", {})
        return msg.get("tool_calls", [])

    async def chat_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        tool_executor=None,
        model: str = "MiniMax-M2.7-highspeed",
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
        max_tool_rounds: int = 5,
    ) -> Dict[str, Any]:
        """Call LLM with tool calling support. Async version."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        tool_count = 0
        last_content = ""

        while tool_count < max_tool_rounds:
            payload = self._build_payload(
                model, "", "", json_mode, temperature, max_tokens, thinking_disabled, tools
            )
            payload["messages"] = messages

            response_data = await self._call_provider(payload, model)
            choices = response_data.get("choices", [])
            if not choices:
                return {"content": "Resposta vazia do LLM.", "model_used": model, "tool_rounds": tool_count}

            msg = choices[0].get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            if not tool_calls and content:
                extracted, cleaned_content = _extract_minimax_tool_calls(content)
                if extracted:
                    tool_calls = extracted
                    content = cleaned_content
                    logger.info(
                        "minimax_inline_tool_calls extracted count=%d", len(tool_calls)
                    )
            last_content = content

            if not tool_calls:
                return {"content": content, "model_used": model, "tool_rounds": tool_count}

            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    logger.info(f"Executing tool: {name}({args})")
                    if tool_executor:
                        tool_result = await tool_executor(name, args)
                    else:
                        tool_result = json.dumps({"error": "tool_executor not configured"})
                except Exception as e:
                    tool_result = json.dumps({"error": str(e)})
                messages.append({
                    "role": "tool",
                    "content": str(tool_result) if isinstance(tool_result, str) else json.dumps(tool_result),
                    "tool_call_id": tc.get("id", ""),
                })
            tool_count += 1

        return {"content": last_content or "Maximo de execucoes atingido.", "model_used": model, "tool_rounds": tool_count}

    async def _call_provider(self, payload: Dict[str, Any], model: str) -> Dict[str, Any]:
        cascade = self._build_cascade_providers(model)

        for attempt_idx, (pname, pmodel, method_name, call_model) in enumerate(cascade):
            try:
                if method_name == "_call_minimax":
                    data = await self._call_minimax_raw(payload)
                elif method_name == "_call_gemini":
                    data = await self._call_gemini_raw(call_model, payload)
                else:
                    raise LLMError(f"unknown_method: {method_name}")
                return data
            except LLMError:
                self._backoff_sleep(attempt_idx)
                continue
            except Exception:
                continue
        raise LLMError("all_providers_failed")

    async def _call_minimax_raw(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.minimax_key:
            raise LLMError("minimax_key_not_configured")
        url = f"{self.minimax_base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.minimax_key}", "Content-Type": "application/json"}
        payload["model"] = self.minimax_model
        payload.pop("thinking", None)
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code == 429:
            raise LLMError("minimax_quota_exceeded")
        if resp.status_code == 401:
            raise LLMError("minimax_auth_failed")
        resp.raise_for_status()
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise LLMError("minimax_empty_response")
        if "base_resp" in data:
            base_resp = data["base_resp"]
            if base_resp.get("status_code", 0) != 0:
                raise LLMError(f"minimax_in_body_error: {base_resp.get('status_msg')}")
        return data

    async def _call_gemini_raw(self, model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.gemini_key:
            raise LLMError("gemini_key_not_configured")
        # Translate OpenAI messages[] to Gemini generateContent shape.
        text = await self._call_gemini(
            model,
            next((m["content"] for m in payload["messages"] if m["role"] == "system"), ""),
            next((m["content"] for m in payload["messages"] if m["role"] == "user"), ""),
            json_mode=payload.get("response_format", {}).get("type") == "json_object",
            temperature=payload.get("temperature", 0.7),
            max_tokens=payload.get("max_tokens", 1024),
            thinking_disabled=True,
        )
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": text,
                    }
                }
            ]
        }

    async def transcribe_audio_base64(self, audio_b64: str, mimetype: str = "audio/ogg") -> str:
        from tools.audio_transcribe import transcribe_base64

        try:
            return await transcribe_base64(audio_b64, mimetype)
        except Exception as exc:
            logger.warning("Local Whisper STT failed: %s", type(exc).__name__)
            return "[audio]"

    async def transcribe_audio(self, audio_url: str, mimetype: str = "audio/ogg") -> str:
        from tools.audio_transcribe import transcribe_url

        try:
            return await transcribe_url(audio_url, mimetype)
        except Exception as exc:
            logger.warning("Local Whisper URL STT failed: %s", type(exc).__name__)
            return "[audio]"

    async def _stt_gemini(self, audio_b64: str, mimetype: str) -> str:
        """Fallback STT via Gemini 2.5 Flash (only when Whisper fails)."""
        if not self.gemini_key:
            raise LLMError("gemini_key_not_configured")
        try:
            from google.generativeai import configure as _ga_configure
            from google.generativeai import GenerativeModel
            import base64 as _b64
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"gemini_sdk_missing: {exc}")

        _ga_configure(api_key=self.gemini_key)
        gen_model = GenerativeModel(model_name=self.gemini_model)
        raw = _b64.b64decode(audio_b64) if isinstance(audio_b64, str) else audio_b64
        response = await asyncio.to_thread(
            gen_model.generate_content,
            [
                {"inline_data": {"mime_type": mimetype, "data": _b64.b64encode(raw).decode()}},
                "Transcreva este audio em portugues brasileiro.",
            ],
            generation_config={
                "temperature": 0.0,
                "max_output_tokens": 1024,
            },
        )
        return (response.text or "").strip()

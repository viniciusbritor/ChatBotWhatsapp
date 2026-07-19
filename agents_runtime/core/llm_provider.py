"""LLM cascade: DeepSeek V4 Flash -> NVIDIA V4 Flash -> DeepSeek V4 Pro -> NVIDIA V4 Pro -> MiniMax M3.

Features:
- Cascade fallback on failure (quota, auth, timeout)
- Exponential backoff with jitter
- JSON mode support (auto-injects "JSON:" prefix per DeepSeek requirement)
- Thinking mode toggle per request
- chat_escalating uses built-in cascade order (Pro comes after Flash in fallback chain)
"""
import os
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


class LLMError(Exception):
    """Raised when all providers fail."""
    pass


class LLMProvider:
    """Multi-provider LLM client with cascade fallback."""

    def __init__(self):
        self.deepseek_key = get_secret("DEEPSEEK_API_KEY")
        self.nvidia_key = get_secret("NVIDIA_API_KEY")
        self.minimax_key = get_secret("MINIMAX_API_KEY")

        self.deepseek_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.nvidia_base = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.minimax_base = os.getenv(
            "MINIMAX_BASE_URL", "https://api.minimax.io/v1"
        )
        self.minimax_model = os.getenv("MINIMAX_MODEL", "MiniMax-M3")

    def is_available(self) -> bool:
        """Check if at least one provider is configured."""
        return bool(self.deepseek_key or self.nvidia_key or self.minimax_key)

    def gemini_available(self) -> bool:
        return False

    def _backoff_sleep(self, attempt: int, base: float = 1.0, cap: float = 30.0):
        """Exponential backoff with jitter."""
        delay = min(cap, base * (2 ** attempt)) + random.uniform(0, 0.5)
        time.sleep(delay)

    def _maybe_inject_json_marker(self, system_prompt: str, json_mode: bool) -> str:
        """DeepSeek requires 'json' keyword in prompt for response_format=json_object."""
        if not json_mode:
            return system_prompt
        if "json" in system_prompt.lower():
            return system_prompt
        return "JSON: " + system_prompt

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
        """Build request payload (OpenAI-compatible)."""
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

    def _call_deepseek(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        thinking_disabled: bool,
    ) -> str:
        """Call DeepSeek API."""
        if not self.deepseek_key:
            raise LLMError("deepseek_key_not_configured")

        url = f"{self.deepseek_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.deepseek_key}",
            "Content-Type": "application/json",
        }
        sp = self._maybe_inject_json_marker(system_prompt, json_mode)
        payload = self._build_payload(
            model, sp, user_prompt, json_mode, temperature, max_tokens, thinking_disabled
        )

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
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

        if "base_resp" in data:
            base_resp = data["base_resp"]
            if base_resp.get("status_code", 0) != 0:
                raise LLMError(f"deepseek_in_body_error: {base_resp.get('status_msg')}")

        return data["choices"][0]["message"]["content"]

    def _call_nvidia(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
        thinking_disabled: bool,
    ) -> str:
        """Call NVIDIA NIM API (DeepSeek V4 Flash via NIM)."""
        if not self.nvidia_key:
            raise LLMError("nvidia_key_not_configured")

        url = f"{self.nvidia_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.nvidia_key}",
            "Content-Type": "application/json",
        }
        sp = self._maybe_inject_json_marker(system_prompt, json_mode)
        payload = self._build_payload(
            model, sp, user_prompt, json_mode, temperature, max_tokens, thinking_disabled
        )

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        if resp.status_code == 429:
            raise LLMError("nvidia_quota_exceeded")
        if resp.status_code == 401:
            raise LLMError("nvidia_auth_failed")
        resp.raise_for_status()

        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise LLMError("nvidia_empty_response")
        return data["choices"][0]["message"]["content"]

    def _call_minimax(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call MiniMax M3 API."""
        if not self.minimax_key:
            raise LLMError("minimax_key_not_configured")

        url = f"{self.minimax_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.minimax_key}",
            "Content-Type": "application/json",
        }
        sp = self._maybe_inject_json_marker(system_prompt, json_mode)
        payload = self._build_payload(
            self.minimax_model, sp, user_prompt, json_mode, temperature, max_tokens, True
        )

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        if resp.status_code == 429:
            raise LLMError("minimax_quota_exceeded")
        resp.raise_for_status()

        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise LLMError("minimax_empty_response")
        return data["choices"][0]["message"]["content"]

    def _build_cascade_providers(self, model: str, skip_gemini: bool = False):
        """Build interleaved cascade list, skipping providers without keys.

        Cascade order:
        1. MiniMax M2.7-highspeed
        2. MiniMax M3
        3. DeepSeek V4 Flash
        """
        providers = []

        if self.minimax_key:
            providers.append(("minimax-hs", "MiniMax-M2.7-highspeed", "_call_minimax", "MiniMax-M2.7-highspeed"))
        if self.minimax_key:
            providers.append(("minimax", self.minimax_model, "_call_minimax", self.minimax_model))
        if self.deepseek_key:
            providers.append(("deepseek", "deepseek-v4-flash", "_call_deepseek", "deepseek-v4-flash"))

        if not providers:
            raise LLMError("no_provider_keys_configured")

        return providers

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "deepseek-v4-flash",
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
    ) -> Dict[str, Any]:
        """Call LLM with cascade fallback. Async."""
        attempts = []

        cascade = self._build_cascade_providers(model, skip_gemini=True)

        for attempt_idx, (provider_name, provider_model, method_name, call_model) in enumerate(cascade):
            try:
                if method_name == "_call_deepseek":
                    content = await asyncio.to_thread(
                        self._call_deepseek,
                        call_model, system_prompt, user_prompt, json_mode, temperature, max_tokens, thinking_disabled
                    )
                elif method_name == "_call_nvidia":
                    content = await asyncio.to_thread(
                        self._call_nvidia,
                        call_model, system_prompt, user_prompt, json_mode, temperature, max_tokens, thinking_disabled
                    )
                elif method_name == "_call_minimax":
                    content = await asyncio.to_thread(
                        self._call_minimax,
                        system_prompt, user_prompt, json_mode, temperature, max_tokens
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
        fast_model: str = "deepseek-v4-flash",
        pro_model: str = "deepseek-v4-pro",
        threshold: int = -2,
        no_escalation: bool = False,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
        scoring_fn=None,
    ) -> Dict[str, Any]:
        """Try Flash first; if cascade fails, escalate to Pro explicitly. Async."""
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
        """Extract tool_calls from LLM response."""
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
        model: str = "deepseek-v4-flash",
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
        """Execute a single provider call and return the full API response dict. Async."""
        cascade = self._build_cascade_providers(model)

        for attempt_idx, (pname, pmodel, method_name, call_model) in enumerate(cascade):
            data: Dict[str, Any]
            try:
                if method_name == "_call_deepseek":
                    data = self._normalize_raw(await self._call_deepseek_raw(call_model, payload))
                elif method_name == "_call_nvidia":
                    data = await self._call_nvidia_raw(call_model, payload)
                elif method_name == "_call_minimax":
                    data = await self._call_minimax_raw(payload)
                else:
                    raise LLMError(f"unknown_method: {method_name}")
                return data
            except LLMError:
                self._backoff_sleep(attempt_idx)
                continue
            except Exception:
                continue
        raise LLMError("all_providers_failed")

    @staticmethod
    def _normalize_raw(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {"choices": [{"message": {"content": str(value)}}]}

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
        raise LLMError("gemini_disabled_by_guardrail")

    async def _call_gemini_raw(self, model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise LLMError("gemini_disabled_by_guardrail")

    async def _call_deepseek_raw(self, model: str, payload: Dict[str, Any]) -> str:
        if not self.deepseek_key:
            raise LLMError("deepseek_key_not_configured")
        url = f"{self.deepseek_base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.deepseek_key}", "Content-Type": "application/json"}
        payload["model"] = model
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code == 429:
            raise LLMError("deepseek_quota_exceeded")
        if resp.status_code == 401:
            raise LLMError("deepseek_auth_failed")
        resp.raise_for_status()
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise LLMError("deepseek_empty_response")
        return data

    async def _call_nvidia_raw(self, model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.nvidia_key:
            raise LLMError("nvidia_key_not_configured")
        url = f"{self.nvidia_base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.nvidia_key}", "Content-Type": "application/json"}
        payload["model"] = model
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code == 429:
            raise LLMError("nvidia_quota_exceeded")
        resp.raise_for_status()
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise LLMError("nvidia_empty_response")
        return data

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
        resp.raise_for_status()
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise LLMError("minimax_empty_response")
        return data

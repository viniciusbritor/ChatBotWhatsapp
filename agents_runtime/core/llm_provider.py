"""LLM cascade: DeepSeek V4 Flash -> NVIDIA V4 Flash -> DeepSeek V4 Pro -> NVIDIA V4 Pro -> MiniMax M3.

Features:
- Cascade fallback on failure (quota, auth, timeout)
- Exponential backoff with jitter
- JSON mode support (auto-injects "JSON:" prefix per DeepSeek requirement)
- Thinking mode toggle per request
- chat_escalating uses built-in cascade order (Pro comes after Flash in fallback chain)
"""
import os
import time
import random
import logging
import requests
from typing import Optional, Dict, Any, List

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
        if thinking_disabled:
            payload["thinking"] = {"type": "disabled"}
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

    def _build_cascade_providers(self, model: str):
        """Build interleaved cascade list, skipping providers without keys.

        Cascade order (user-requested):
        1. DeepSeek V4 Flash (direct)
        2. NVIDIA NIM V4 Flash
        3. DeepSeek V4 Pro (direct)
        4. NVIDIA NIM V4 Pro
        5. MiniMax M3 (last resort)
        """
        providers = []

        if self.deepseek_key:
            providers.append(("deepseek", model, "_call_deepseek", model))
        if self.nvidia_key:
            providers.append(("nvidia-flash", "deepseek-ai/deepseek-v4-flash", "_call_nvidia", "deepseek-ai/deepseek-v4-flash"))
        if self.deepseek_key:
            providers.append(("deepseek-pro", "deepseek-v4-pro", "_call_deepseek", "deepseek-v4-pro"))
        if self.nvidia_key:
            providers.append(("nvidia-pro", "deepseek-ai/deepseek-v4-pro", "_call_nvidia", "deepseek-ai/deepseek-v4-pro"))
        if self.minimax_key:
            providers.append(("minimax", self.minimax_model, "_call_minimax", self.minimax_model))

        if not providers:
            raise LLMError("no_provider_keys_configured")

        return providers

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "deepseek-v4-flash",
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        thinking_disabled: bool = True,
    ) -> Dict[str, Any]:
        """Call LLM with cascade fallback.

        Cascade order (skips providers without keys):
        1. DeepSeek V4 Flash (direct)
        2. NVIDIA NIM V4 Flash
        3. DeepSeek V4 Pro (direct)
        4. NVIDIA NIM V4 Pro
        5. MiniMax M3 (last resort)

        Returns:
            {"content": str, "model_used": str, "attempts": List[str]}
        """
        attempts = []

        cascade = self._build_cascade_providers(model)

        for attempt_idx, (provider_name, provider_model, method_name, call_model) in enumerate(cascade):
            try:
                if method_name == "_call_deepseek":
                    content = self._call_deepseek(
                        call_model, system_prompt, user_prompt, json_mode, temperature, max_tokens, thinking_disabled
                    )
                elif method_name == "_call_nvidia":
                    content = self._call_nvidia(
                        call_model, system_prompt, user_prompt, json_mode, temperature, max_tokens, thinking_disabled
                    )
                elif method_name == "_call_minimax":
                    content = self._call_minimax(
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

    def chat_escalating(
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
        """Try Flash first; if cascade fails, escalate to Pro explicitly.

        With the 5-tier cascade (Flash -> NVIDIA Flash -> Pro -> NVIDIA Pro -> MiniMax),
        the chat() already tries Pro after Flash. This method adds heuristic escalation:
        if Flash response has low confidence, force a retry with pro_model explicitly.

        Args:
            scoring_fn: callable(text) -> int, computes confidence score.
                If score <= threshold, escalate.

        Returns:
            Same as chat() + "escalated" key (bool).
        """
        if no_escalation:
            result = self.chat(
                system_prompt, user_prompt, fast_model, json_mode, temperature, max_tokens, thinking_disabled
            )
            return {**result, "escalated": False}

        fast_resp = self.chat(
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
        pro_resp = self.chat(
            system_prompt, user_prompt, pro_model, json_mode, temperature, max_tokens, thinking_disabled
        )
        return {**pro_resp, "escalated": True, "confidence_score": score, "fast_response": fast_resp}
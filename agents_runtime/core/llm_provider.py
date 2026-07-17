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

        self.gemini_project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT", "coherence-ominichannel-fs")
        self.gemini_location = os.getenv("GEMINI_LOCATION", "us-central1")
        self.deepseek_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.nvidia_base = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.minimax_base = os.getenv(
            "MINIMAX_BASE_URL", "https://api.minimax.io/v1"
        )
        self.minimax_model = os.getenv("MINIMAX_MODEL", "MiniMax-M3")

    def is_available(self) -> bool:
        """Check if at least one provider is configured."""
        return bool(self.gemini_available() or self.deepseek_key or self.nvidia_key or self.minimax_key)

    def gemini_available(self) -> bool:
        """Vertex AI usa ADC — disponivel se GCP_PROJECT ou ADC configurado."""
        if self.gemini_project and self.gemini_project not in ("", "demo-project"):
            return True
        try:
            import google.auth
            creds, project = google.auth.default()
            return bool(project)
        except Exception:
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
        1. Gemini 2.5 Flash (primary, mais rapido + barato)
        2. DeepSeek V4 Flash (direct)
        3. DeepSeek V4 Pro (direct)
        4. NVIDIA NIM V4 Flash
        5. NVIDIA NIM V4 Pro
        6. MiniMax M3 (last resort)
        """
        providers = []

        if self.gemini_available() and not skip_gemini:
            providers.append(("gemini", "gemini-2.5-flash", "_call_gemini", "gemini-2.5-flash"))
        if self.deepseek_key:
            providers.append(("deepseek", model, "_call_deepseek", model))
        if self.deepseek_key:
            providers.append(("deepseek-pro", "deepseek-v4-pro", "_call_deepseek", "deepseek-v4-pro"))
        if self.nvidia_key:
            providers.append(("nvidia-flash", "deepseek-ai/deepseek-v4-flash", "_call_nvidia", "deepseek-ai/deepseek-v4-flash"))
        if self.nvidia_key:
            providers.append(("nvidia-pro", "deepseek-ai/deepseek-v4-pro", "_call_nvidia", "deepseek-ai/deepseek-v4-pro"))
        if self.minimax_key:
            providers.append(("minimax", self.minimax_model, "_call_minimax", self.minimax_model))

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
            try:
                if method_name == "_call_gemini":
                    data = await self._call_gemini_raw(call_model, payload)
                elif method_name == "_call_deepseek":
                    data = await self._call_deepseek_raw(call_model, payload)
                elif method_name == "_call_nvidia":
                    data = await self._call_nvidia_raw(call_model, payload)
                elif method_name == "_call_minimax":
                    data = await self._call_minimax_raw(payload)
                else:
                    raise LLMError(f"unknown_method: {method_name}")
                return data
            except LLMError as e:
                self._backoff_sleep(attempt_idx)
                continue
            except Exception as e:
                continue
        raise LLMError(f"all_providers_failed")

    async def _call_gemini_raw(self, model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call Gemini 2.5 Flash via Vertex AI (ADC, sem API key)."""
        import google.auth
        import google.auth.transport.requests

        creds, project = google.auth.default()
        project = project or self.gemini_project
        creds.refresh(google.auth.transport.requests.Request())

        url = (
            f"https://{self.gemini_location}-aiplatform.googleapis.com/v1/"
            f"projects/{project}/locations/{self.gemini_location}/"
            f"publishers/google/models/{model}:generateContent"
        )
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        }
        gemini_payload = self._to_gemini_format(payload)
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, headers=headers, json=gemini_payload)
        if resp.status_code == 429:
            raise LLMError("gemini_quota_exceeded")
        if resp.status_code >= 400:
            raise LLMError(f"gemini_error_{resp.status_code}")
        data = resp.json()
        return self._from_gemini_response(data)

    def _to_gemini_format(self, openai_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Converte payload OpenAI → Gemini format."""
        gemini = {}
        messages = openai_payload.get("messages", [])
        system_content = ""
        contents = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_content = content
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                parts = []
                if content:
                    parts.append({"text": content})
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    parts.append({"functionCall": {"name": fn.get("name", ""), "args": json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments", ""), str) else fn.get("arguments", {})}})
                contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                name = msg.get("name", "")
                contents.append({"role": "function", "parts": [{"functionResponse": {"name": name, "response": {"content": str(content)}}}]})
        if system_content:
            gemini["systemInstruction"] = {"parts": [{"text": system_content}]}
        gemini["contents"] = contents

        tools = openai_payload.get("tools", [])
        if tools:
            gemini_tools = []
            for t in tools:
                fn = t.get("function", {})
                gemini_tools.append({"functionDeclarations": [{
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                }]})
            gemini["tools"] = gemini_tools

        gen_config = {}
        if openai_payload.get("temperature"):
            gen_config["temperature"] = openai_payload["temperature"]
        if openai_payload.get("max_tokens"):
            gen_config["maxOutputTokens"] = openai_payload["max_tokens"]
        if gen_config:
            gemini["generationConfig"] = gen_config

        return gemini

    def _from_gemini_response(self, gemini_data: Dict[str, Any]) -> Dict[str, Any]:
        """Converte resposta Gemini → formato OpenAI-compatible."""
        candidates = gemini_data.get("candidates", [])
        if not candidates:
            raise LLMError("gemini_empty_response")
        candidate = candidates[0]
        content_obj = candidate.get("content", {})
        parts = content_obj.get("parts", [])
        text = ""
        tool_calls = []
        for part in parts:
            if "text" in part:
                text += part["text"]
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "id": fc.get("name", "call_0"),
                    "type": "function",
                    "function": {"name": fc["name"], "arguments": json.dumps(fc.get("args", {}))},
                })
        return {
            "choices": [{"message": {"content": text, "tool_calls": tool_calls if tool_calls else None}}]
        }

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
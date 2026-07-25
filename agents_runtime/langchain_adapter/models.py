"""Centralized LLM model factory.

Provides a single function to build the LangChain chat model used
across the runtime. Today this is DeepSeek v4-flash (single-provider,
Fase K). All callers MUST go through ``build_default_chat_model()``
so the endpoint, API key, and base URL are configured in one place.

Why not just pass ``openai:deepseek-v4-flash`` to ``create_deep_agent``?
Because LangChain's ``openai:`` prefix routes to ``api.openai.com``,
not DeepSeek. We need an explicit ``ChatOpenAI(base_url=...)`` instance.
"""
from __future__ import annotations

import os
import logging
from typing import Any

from core.secrets import get_secret

logger = logging.getLogger(__name__)


def build_default_chat_model() -> Any:
    """Return the LangChain chat model used by all agents.

    DeepSeek exposes an OpenAI-compatible endpoint at
    ``https://api.deepseek.com/v1``. We instantiate ``ChatOpenAI`` with
    the DeepSeek base URL so the underlying HTTP calls go to DeepSeek,
    not OpenAI.

    The API key is fetched from Secret Manager (or env var fallback).
    The base URL is taken from ``DEEPSEEK_BASE_URL`` so it can be
    overridden in tests.
    """
    from langchain_openai import ChatOpenAI

    api_key = get_secret("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("JENNIFER_MODEL_ID", "deepseek-v4-flash")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.7,
    )

"""LLM 客户端封装 — 统一 OpenAI SDK 兼容模型创建入口。"""

from __future__ import annotations

import logging
from typing import Any

from core.llm_openai_compat import OpenAICompatChatModel

logger = logging.getLogger(__name__)


def create_chat_model(
    llm_config: dict[str, Any] | None = None,
    *,
    streaming: bool = True,
    temperature: float = 0.0,
    **kwargs: Any,
) -> OpenAICompatChatModel:
    """创建 OpenAI SDK-backed ChatModel。"""
    cfg = llm_config or {}

    api_key = str(cfg.get("api_key", "")).strip()
    base_url = str(cfg.get("base_url", "")).strip()
    model = str(cfg.get("model", "")).strip()

    if not api_key:
        raise ValueError("Missing API Key — set LLM_API_KEY environment variable")
    if not model:
        raise ValueError("Missing model — set MODEL_NAME environment variable")

    logger.info("OpenAICompatChatModel: model=%s, base_url=%s", model, base_url or "(default)")

    return OpenAICompatChatModel(
        api_key=api_key,
        base_url=base_url or None,
        model=model,
        streaming=streaming,
        temperature=temperature,
        **kwargs,
    )

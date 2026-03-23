"""LLM 客户端封装 — 统一 ChatOpenAI 创建入口

兼容所有 OpenAI API 后端 (DeepSeek / 通义千问 / OpenAI 等)。
配置优先级: 环境变量 ``{PREFIX}_API_KEY`` > config.json ``api_key``。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def create_chat_model(
    llm_config: dict[str, Any] | None = None,
    *,
    env_prefix: str = "LLM",
    streaming: bool = True,
    temperature: float = 0.0,
    **kwargs: Any,
) -> ChatOpenAI:
    """创建 ChatOpenAI 实例。

    查找 ``{env_prefix}_API_KEY / _BASE_URL / _MODEL``，
    未设置则回退到 *llm_config* 字典中的同名键。
    """
    cfg = llm_config or {}

    def _env(suffix: str, cfg_key: str) -> str:
        return os.environ.get(f"{env_prefix}_{suffix}", "").strip() or str(cfg.get(cfg_key, ""))

    api_key  = _env("API_KEY",  "api_key")
    base_url = _env("BASE_URL", "base_url")
    model    = _env("MODEL",    "model")

    if not api_key:
        raise ValueError(f"缺少 API Key — 设置 {env_prefix}_API_KEY 或 config.json")
    if not model:
        raise ValueError(f"缺少 model — 设置 {env_prefix}_MODEL 或 config.json")

    logger.info("ChatOpenAI: model=%s, base_url=%s", model, base_url or "(default)")

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url or None,
        model=model,
        streaming=streaming,
        temperature=temperature,
        **kwargs,
    )

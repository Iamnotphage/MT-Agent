#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from typing import Any, Dict

from core.compiler import DEFAULT_MT3000_ROOT

def _load_json(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_app_config(config_path: str = "config.json") -> Dict[str, Any]:
    cfg = _load_json(config_path)
    app: Dict[str, Any] = {}

    app["mt3000_root"] = os.environ.get("MT3000_ROOT", str(cfg.get("mt3000_root", DEFAULT_MT3000_ROOT))).strip()
    analyze_cfg = cfg.get("analyze_llm", {}) if isinstance(cfg.get("analyze_llm", {}), dict) else {}
    code_cfg = cfg.get("code_llm", {}) if isinstance(cfg.get("code_llm", {}), dict) else {}

    # 向后兼容旧平铺字段
    app["analyze_llm"] = {
        "api_key": os.environ.get(
            "ANALYZE_LLM_API_KEY",
            os.environ.get("LLM_API_KEY_ANALYZE", str(analyze_cfg.get("api_key", cfg.get("api_key_classify", "")))),
        ).strip(),
        "base_url": os.environ.get(
            "ANALYZE_LLM_BASE_URL",
            os.environ.get(
                "LLM_BASE_URL_ANALYZE",
                str(analyze_cfg.get("base_url", cfg.get("base_url_classify", "https://dashscope.aliyuncs.com/compatible-mode/v1"))),
            ),
        ).strip(),
        "model": os.environ.get(
            "ANALYZE_LLM_MODEL",
            os.environ.get("LLM_MODEL_ANALYZE", str(analyze_cfg.get("model", cfg.get("model_code_classify", "qwen3-coder-flash")))),
        ).strip(),
    }
    app["code_llm"] = {
        "api_key": os.environ.get(
            "CODE_LLM_API_KEY",
            os.environ.get("LLM_API_KEY", str(code_cfg.get("api_key", cfg.get("api_key", "")))),
        ).strip(),
        "base_url": os.environ.get(
            "CODE_LLM_BASE_URL",
            os.environ.get("LLM_BASE_URL", str(code_cfg.get("base_url", cfg.get("base_url", "https://api.deepseek.com")))),
        ).strip(),
        "model": os.environ.get(
            "CODE_LLM_MODEL",
            os.environ.get("LLM_MODEL_CODE", str(code_cfg.get("model", cfg.get("model_code", "deepseek-chat")))),
        ).strip(),
    }

    app["max_retry"] = int(os.environ.get("MAX_RETRY", str(cfg.get("max_retry", 3))))
    app["output_dir"] = os.environ.get("OUTPUT_DIR", str(cfg.get("output_dir", "output"))).strip() or "output"

    return app


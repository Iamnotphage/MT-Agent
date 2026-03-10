#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from prompts.optimize_prompts import (
    build_am_optimize_prompt,
    build_regenerate_prompt,
    build_sm_optimize_prompt,
)


def _read_text(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _strip_md_block(text: str) -> str:
    content = (text or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9_]*\s*|\s*```$", "", content, flags=re.MULTILINE).strip()
    return content


class CodeOptimizer:
    def __init__(self, api_key: str, base_url: str, model_code: str):
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError("未安装 openai 包，请先在环境中安装（pip install openai）。") from e
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_code = model_code
        project_root = Path(__file__).resolve().parents[1]
        self.am_resource_root = str((project_root / "skills" / "am-vectorization-templates" / "resources").resolve())
        self.sm_resource_root = str((project_root / "skills" / "sm-cache-optimization-templates" / "resources").resolve())

    def _chat_generate(self, prompt: str, stage: str, emit: Optional[Callable[[str], None]] = None) -> str:
        log = emit or (lambda _msg: None)
        log(f"[{stage}] 调用 code LLM（non-stream）...")
        rsp = self.client.chat.completions.create(
            model=self.model_code,
            messages=[{"role": "user", "content": prompt}],
        )
        content = rsp.choices[0].message.content or ""
        normalized = _strip_md_block(content)
        log(f"[{stage}] 生成完成，字符数={len(normalized)}")
        return normalized

    def _load_am_context(self, templates: List[str]) -> Tuple[str, str]:
        function_lib = _read_text(os.path.join(self.am_resource_root, "function_lib.txt"))
        template_texts: List[str] = []
        for t in templates:
            p = os.path.join(self.am_resource_root, "vec_tempelate", f"tempelate_{t}.txt")
            txt = _read_text(p)
            if txt:
                template_texts.append(txt)
        return function_lib, "\n\n".join(template_texts)

    def _load_sm_context(self, templates: List[str]) -> Tuple[str, str]:
        cache_lib = _read_text(os.path.join(self.sm_resource_root, "cache_lib.txt"))
        template_texts: List[str] = []
        for t in templates:
            p = os.path.join(self.sm_resource_root, "sca_tempelate", f"tempelate_{t}.txt")
            txt = _read_text(p)
            if txt:
                template_texts.append(txt)
        return cache_lib, "\n\n".join(template_texts)

    def generate_am(
        self,
        source_code: str,
        templates: Optional[List[str]] = None,
        emit: Optional[Callable[[str], None]] = None,
    ) -> str:
        tpl = templates or ["Generic", "DenseMatMul", "MatVec", "Stencil"]
        function_lib, template_text = self._load_am_context(tpl)
        prompt = build_am_optimize_prompt(
            source_code=source_code,
            function_lib=function_lib,
            template_text=template_text,
        )
        return self._chat_generate(prompt, stage="optimize-am", emit=emit)

    def generate_sm(
        self,
        source_code: str,
        templates: Optional[List[str]] = None,
        emit: Optional[Callable[[str], None]] = None,
    ) -> str:
        tpl = templates or ["ScaGeneric", "ScaBulk"]
        cache_lib, template_text = self._load_sm_context(tpl)
        prompt = build_sm_optimize_prompt(
            source_code=source_code,
            cache_lib=cache_lib,
            template_text=template_text,
        )
        return self._chat_generate(prompt, stage="optimize-sm", emit=emit)

    def regenerate_with_feedback(
        self,
        mode: str,
        source_code: str,
        previous_code: str,
        compile_error_text: str,
        emit: Optional[Callable[[str], None]] = None,
    ) -> str:
        if mode == "am":
            task = "AM 向量化"
            suffix = "_vec_qwen"
        else:
            task = "SM 缓存优化"
            suffix = "_sca_qwen"
        prompt = build_regenerate_prompt(
            task=task,
            source_code=source_code,
            previous_code=previous_code,
            compile_error_text=compile_error_text,
            suffix=suffix,
        )
        return self._chat_generate(prompt, stage="regenerate", emit=emit)


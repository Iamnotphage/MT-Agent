#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from typing import Callable, Dict, Optional

from prompts.analyze_prompts import build_analyze_prompt


def _heuristic_analyze(source: str) -> Dict[str, object]:
    text = source or ""
    lower = text.lower()

    loop_count = len(re.findall(r"\bfor\s*\(", text))
    ptr_access = len(re.findall(r"\[[^\]]+\]", text))
    branch_count = len(re.findall(r"\bif\s*\(", text))

    has_stencil_pattern = bool(re.search(r"\[\s*i\s*[+-]\s*\d+", lower))
    has_scatter_like = bool(re.search(r"\w+\s*\[\s*\w+\s*\[\s*", lower))
    has_mul_add = ("*" in text and "+" in text)

    am_score = 0
    sm_score = 0
    reasons = []

    if loop_count >= 2:
        am_score += 2
        reasons.append("存在嵌套或多重循环，具备向量化潜力")
    if ptr_access >= 8:
        am_score += 1
        sm_score += 1
        reasons.append("数组访存较多，优化收益可能明显")
    if has_mul_add:
        am_score += 1
        reasons.append("存在乘加类算子")
    if has_stencil_pattern:
        sm_score += 2
        reasons.append("检测到邻域访存，缓存优化潜力较高")
    if branch_count >= 5:
        sm_score += 1
        reasons.append("分支较多，可能不利于纯向量化")
    if has_scatter_like:
        sm_score += 2
        reasons.append("检测到间接索引，更偏向缓存或标量路径")

    mode = "am" if am_score >= sm_score else "sm"
    return {
        "recommended_mode": mode,
        "am_score": am_score,
        "sm_score": sm_score,
        "reasons": reasons,
        "stats": {
            "loop_count": loop_count,
            "ptr_access_count": ptr_access,
            "branch_count": branch_count,
        },
        "analyzer": "heuristic",
    }


class SourceAnalyzer:
    def __init__(
        self,
        api_key_analyze: str = "",
        base_url_analyze: str = "",
        model_analyze: str = "",
    ):
        self.api_key_analyze = (api_key_analyze or "").strip()
        self.base_url_analyze = (base_url_analyze or "").strip()
        self.model_analyze = (model_analyze or "").strip()

    def analyze(self, source: str, emit: Optional[Callable[[str], None]] = None) -> Dict[str, object]:
        log = emit or (lambda _msg: None)
        if not self.api_key_analyze:
            log("[analyze] 未配置 analyze_llm.api_key，回退规则分析。")
            return _heuristic_analyze(source)
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            log("[analyze] 未安装 openai，回退规则分析。")
            return _heuristic_analyze(source)

        try:
            client = OpenAI(api_key=self.api_key_analyze, base_url=self.base_url_analyze)
            prompt = build_analyze_prompt(source)
            log("[analyze] 调用 analyze LLM（non-stream）...")
            rsp = client.chat.completions.create(
                model=self.model_analyze,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (rsp.choices[0].message.content or "").strip()
            m = re.search(r"\{.*\}", raw, flags=re.S)
            if not m:
                log("[analyze] 未解析到 JSON，回退规则分析。")
                return _heuristic_analyze(source)
            import json
            obj = json.loads(m.group(0))
            mode = str(obj.get("recommended_mode", "am")).strip().lower()
            if mode not in ("am", "sm"):
                mode = "am"
            reasons = obj.get("reasons", [])
            if not isinstance(reasons, list):
                reasons = [str(reasons)]
            return {
                "recommended_mode": mode,
                "reasons": reasons,
                "analyzer": "llm-analyze",
            }
        except Exception:
            log("[analyze] analyze LLM 调用失败，回退规则分析。")
            return _heuristic_analyze(source)


def analyze_source_code(
    source: str,
    analyzer: Optional[SourceAnalyzer] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> Dict[str, object]:
    if analyzer is None:
        return _heuristic_analyze(source)
    return analyzer.analyze(source, emit=emit)


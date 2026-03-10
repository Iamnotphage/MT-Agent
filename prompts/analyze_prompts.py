#!/usr/bin/env python3
# -*- coding: utf-8 -*-

ANALYZE_PROMPT_TEMPLATE = """你是 MT-3000 代码分析器。请分析下面 C 代码更适合 AM 向量化还是 SM 缓存优化。

输出严格为单行 JSON，格式：
{{"recommended_mode":"am|sm","reasons":["...","..."]}}

代码如下：
{source_code}
"""


def build_analyze_prompt(source_code: str) -> str:
    return ANALYZE_PROMPT_TEMPLATE.format(source_code=source_code)


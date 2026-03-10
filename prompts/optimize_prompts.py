#!/usr/bin/env python3
# -*- coding: utf-8 -*-

AM_OPTIMIZE_PROMPT_TEMPLATE = """
# MT-3000 AM 向量化任务

请基于以下信息，将输入 C 核函数改写为向量化版本。输出函数名后缀为 _vec_qwen。
不适合向量化部分保持标量实现。

## 向量接口
{function_lib}

## 参考模板
{template_text}

## 输入代码
{source_code}

## 约束
1. 先做线程任务划分。
2. 使用 vector_load / vector_store 搬运。
3. 使用向量算子计算并处理尾部元素。
4. 只输出完整 C 代码，不要 markdown 代码块。
"""

SM_OPTIMIZE_PROMPT_TEMPLATE = """
# MT-3000 SM 缓存优化任务

请将输入 C 核函数改写为标量缓存优化版本，输出函数名后缀为 _sca_qwen。
根据访存模式使用 CACHEd/CACHEs/CACHEb。

## 缓存接口
{cache_lib}

## 参考模板
{template_text}

## 输入代码
{source_code}

## 约束
1. 先做线程任务划分。
2. 按块执行 INIT -> RD/WT -> FLUSH/INVALID。
3. 只输出完整 C 代码，不要 markdown 代码块。
"""

REGENERATE_WITH_FEEDBACK_PROMPT_TEMPLATE = """
# MT-3000 {task} 修正任务

下面是上一次生成代码和编译错误，请修复后重新生成。

## 原始源码
{source_code}

## 上一版代码
{previous_code}

## 编译错误
{compile_error_text}

## 输出要求
1. 只输出完整 C 代码。
2. 函数名后缀保持 {suffix}。
3. 不要使用 markdown 代码块。
"""


def build_am_optimize_prompt(source_code: str, function_lib: str, template_text: str) -> str:
    return AM_OPTIMIZE_PROMPT_TEMPLATE.format(
        source_code=source_code,
        function_lib=function_lib,
        template_text=template_text,
    )


def build_sm_optimize_prompt(source_code: str, cache_lib: str, template_text: str) -> str:
    return SM_OPTIMIZE_PROMPT_TEMPLATE.format(
        source_code=source_code,
        cache_lib=cache_lib,
        template_text=template_text,
    )


def build_regenerate_prompt(task: str, source_code: str, previous_code: str, compile_error_text: str, suffix: str) -> str:
    return REGENERATE_WITH_FEEDBACK_PROMPT_TEMPLATE.format(
        task=task,
        source_code=source_code,
        previous_code=previous_code,
        compile_error_text=compile_error_text,
        suffix=suffix,
    )


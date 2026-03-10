#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from core.analyzer import SourceAnalyzer, analyze_source_code
from core.compiler import MT3000Compiler
from core.optimizer import CodeOptimizer


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: str, content: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _collect_errors(outputs: list) -> str:
    lines = []
    for out in outputs:
        if out.get("stderr"):
            lines.append(f"{out.get('step')}: {out.get('stderr')}")
    return "\n".join(lines) if lines else "无 stderr"


def _format_compile_raw(outputs: list) -> str:
    parts = []
    for out in outputs:
        step = out.get("step", "unknown")
        rc = out.get("returncode", -1)
        ok = out.get("success", False)
        stdout = out.get("stdout", "")
        stderr = out.get("stderr", "")
        parts.append(
            "\n".join(
                [
                    f"===== {step} (success={ok}, rc={rc}) =====",
                    "[stdout]",
                    stdout if stdout else "",
                    "[stderr]",
                    stderr if stderr else "",
                ]
            )
        )
    return "\n\n".join(parts)


def run_pipeline(
    source_path: str,
    compile_entry_path: str,
    mode: str,
    output_dir: str,
    app_config: Dict,
    keep_artifacts: bool = False,
) -> Dict:
    runtime_lines: List[str] = []

    def emit(msg: str) -> None:
        line = str(msg)
        print(line, flush=True)
        runtime_lines.append(line)

    source_abs = os.path.abspath(source_path)
    compile_entry_abs = os.path.abspath(compile_entry_path)
    project_root = str(Path(__file__).resolve().parents[1])

    out_root = os.path.abspath(output_dir)
    out_code = os.path.join(out_root, "code")
    out_reports = os.path.join(out_root, "reports")
    os.makedirs(out_code, exist_ok=True)
    os.makedirs(out_reports, exist_ok=True)
    emit(f"[pipeline] source={source_abs}")
    emit(f"[pipeline] compile_entry={compile_entry_abs}")
    emit(f"[pipeline] output_dir={out_root}")

    source_text = _read_text(source_abs)
    analyze_llm = app_config.get("analyze_llm", {})
    code_llm = app_config.get("code_llm", {})
    source_analyzer = SourceAnalyzer(
        api_key_analyze=analyze_llm.get("api_key", ""),
        base_url_analyze=analyze_llm.get("base_url", ""),
        model_analyze=analyze_llm.get("model", ""),
    )
    emit("[pipeline] 开始源码分析...")
    analysis = analyze_source_code(source_text, source_analyzer, emit=emit)
    use_mode = analysis["recommended_mode"] if mode == "auto" else mode
    emit(f"[pipeline] 分析完成，模式={use_mode}，analyzer={analysis.get('analyzer')}")

    if not code_llm.get("api_key"):
        raise RuntimeError("未检测到代码生成 LLM API Key。请设置 CODE_LLM_API_KEY 或 config.json 的 code_llm.api_key。")

    optimizer = CodeOptimizer(api_key=code_llm["api_key"], base_url=code_llm["base_url"], model_code=code_llm["model"])

    compiler = MT3000Compiler(mt3000_root=app_config["mt3000_root"])
    toolchain = compiler.check_toolchain()
    latest_log = os.path.join(out_reports, "latest_pipeline.log")
    if not toolchain["ok"]:
        content = "[ERROR] toolchain missing\n" + "\n".join(toolchain["missing"]) + "\n"
        _write_text(latest_log, content)
        return {"success": False, "mode": use_mode, "report_log": latest_log, "missing_tools": toolchain["missing"]}

    code_output_path = os.path.join(out_code, "kernel_generated.h")
    staged_compile_entry_path = os.path.join(out_code, "compile-entry.dev.c")
    compile_header_path = code_output_path
    source_compile_entry_dir = os.path.dirname(compile_entry_abs)
    if os.path.isfile(compile_entry_abs):
        if os.path.abspath(compile_entry_abs) != os.path.abspath(staged_compile_entry_path):
            shutil.copyfile(compile_entry_abs, staged_compile_entry_path)
            emit(f"[pipeline] 已复制编译入口到: {staged_compile_entry_path}")
        else:
            emit(f"[pipeline] 使用默认编译入口: {staged_compile_entry_path}")
    elif os.path.isfile(staged_compile_entry_path):
        emit(f"[pipeline] 使用已存在编译入口: {staged_compile_entry_path}")
    else:
        raise FileNotFoundError(
            f"compile-entry 不存在: {compile_entry_abs}。"
            f"请传入有效路径，或先在 {staged_compile_entry_path} 放置编译入口文件。"
        )

    max_retry = int(app_config.get("max_retry", 3))
    logs = []
    generated = ""
    compile_result = {"success": False, "outputs": []}

    for idx in range(max_retry):
        round_id = idx + 1
        emit(f"[pipeline] ===== Round {round_id}/{max_retry} =====")
        if round_id == 1:
            generated = (
                optimizer.generate_am(source_text, emit=emit)
                if use_mode == "am"
                else optimizer.generate_sm(source_text, emit=emit)
            )
        else:
            err_text = _collect_errors(compile_result["outputs"])
            emit("[pipeline] 编译失败，开始基于错误回灌重试生成...")
            generated = optimizer.regenerate_with_feedback(use_mode, source_text, generated, err_text, emit=emit)

        _write_text(code_output_path, generated)
        emit(f"[pipeline] 已写入生成代码: {code_output_path}")
        emit(f"[pipeline] 编译入口使用: {staged_compile_entry_path}")

        compile_result = compiler.compile_device_file(
            staged_compile_entry_path,
            keep_artifacts=keep_artifacts,
            extra_include_dirs=[project_root, out_code, source_compile_entry_dir],
        )
        emit(f"[pipeline] 编译结果 success={compile_result['success']}")
        raw_text = _format_compile_raw(compile_result["outputs"])
        logs.append(
            "\n".join(
                [
                    f"========== Round {round_id}/{max_retry} ==========",
                    f"mode={use_mode}",
                    f"source={source_abs}",
                    f"compile_entry={staged_compile_entry_path}",
                    f"code_output={code_output_path}",
                    f"compile_header={compile_header_path}",
                    raw_text,
                ]
            )
        )
        if compile_result["success"]:
            emit("[pipeline] 编译通过，流程结束。")
            break

    latest_content = (
        f"[timestamp] {datetime.now().isoformat(timespec='seconds')}\n"
        f"[success] {compile_result['success']}\n"
        f"[analyzer] {analysis.get('analyzer')}\n"
        f"[mode] {use_mode}\n\n"
        + "[runtime]\n"
        + "\n".join(runtime_lines)
        + "\n\n[details]\n"
        + "\n\n".join(logs)
        + "\n"
    )
    _write_text(latest_log, latest_content)
    history_log = os.path.join(out_reports, f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    _write_text(history_log, latest_content)

    return {
        "success": compile_result["success"],
        "mode": use_mode,
        "code_output": code_output_path,
        "header_written_to": compile_header_path,
        "compile_entry_used": staged_compile_entry_path,
        "report_log": latest_log,
        "history_log": history_log,
        "analysis": analysis,
    }


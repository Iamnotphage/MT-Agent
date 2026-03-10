#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import load_app_config  # noqa: E402
from core.pipeline import run_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="主入口：分析源码 -> 生成优化代码 -> 编译测试 -> 输出")
    p.add_argument("-i", "--input", required=True, help="输入源代码文件（kernel）")
    p.add_argument(
        "--compile-entry",
        default="output/code/compile-entry.dev.c",
        help="用于编译测试的入口 .dev.c 文件（默认 output/code/compile-entry.dev.c）",
    )
    p.add_argument("--mode", choices=["auto", "am", "sm"], default="auto", help="优化模式")
    p.add_argument("--output-dir", default="output", help="输出目录，默认 output")
    p.add_argument("--config", default="config.json", help="配置文件路径")
    p.add_argument("--keep-artifacts", action="store_true", help="保留 .dev.o/.dev.out")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_app_config(args.config)

    output_dir = args.output_dir or cfg.get("output_dir", "output")
    try:
        result = run_pipeline(
            source_path=args.input,
            compile_entry_path=args.compile_entry,
            mode=args.mode,
            output_dir=output_dir,
            app_config=cfg,
            keep_artifacts=args.keep_artifacts,
        )
    except Exception as e:
        print(f"[error] {e}")
        return 2

    print(f"[success] {result.get('success')}")
    print(f"[mode] {result.get('mode')}")
    print(f"[code] {result.get('code_output')}")
    if result.get("report_log"):
        print(f"[report] {result.get('report_log')}")
    if result.get("history_log"):
        print(f"[report-history] {result.get('history_log')}")
    if result.get("missing_tools"):
        print("[missing-tools]")
        for t in result["missing_tools"]:
            print(f"  - {t}")
        return 2
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.compiler import MT3000Compiler, load_mt3000_root  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="固定脚本：MT-3000 编译测试（不依赖 LLM API）")
    p.add_argument("-i", "--input", required=True, help="输入设备端 C 文件（通常 *.dev.c）")
    p.add_argument("--mt3000-root", default="", help="可选，显式指定 MT3000 编译环境根目录")
    p.add_argument("--keep-artifacts", action="store_true", help="保留中间文件（.dev.o/.dev.out）")
    p.add_argument(
        "--report",
        default="",
        help="报告输出路径（默认自动生成 output/reports/compile_test_YYYYMMDD_HHMMSS.log）",
    )
    return p.parse_args()


def summarize(outputs: List[Dict]) -> str:
    lines: List[str] = []
    for out in outputs:
        step = out.get("step", "unknown")
        ok = "OK" if out.get("success") else "FAIL"
        rc = out.get("returncode", -1)
        err = (out.get("stderr") or "").strip()
        if err:
            first = err.splitlines()[0]
            lines.append(f"- [{ok}] {step} (rc={rc}) {first}")
        else:
            lines.append(f"- [{ok}] {step} (rc={rc})")
    return "\n".join(lines)


def ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def format_raw_report(input_path: str, mt3000_root: str, outputs: List[Dict], success: bool) -> str:
    blocks: List[str] = []
    blocks.append(f"[timestamp] {datetime.now().isoformat(timespec='seconds')}")
    blocks.append(f"[input] {input_path}")
    blocks.append(f"[mt3000_root] {mt3000_root}")
    blocks.append(f"[success] {success}")
    blocks.append("")
    for out in outputs:
        blocks.append(f"===== {out.get('step', 'unknown')} (success={out.get('success')}, rc={out.get('returncode')}) =====")
        blocks.append("[stdout]")
        blocks.append((out.get("stdout") or "").rstrip())
        blocks.append("[stderr]")
        blocks.append((out.get("stderr") or "").rstrip())
        blocks.append("")
    return "\n".join(blocks)


def main() -> int:
    args = parse_args()
    input_path = os.path.abspath(args.input)

    mt3000_root = args.mt3000_root.strip() or load_mt3000_root(str(PROJECT_ROOT / "config.json"))
    compiler = MT3000Compiler(mt3000_root=mt3000_root)

    check = compiler.check_toolchain()
    if not check["ok"]:
        print("[错误] 编译工具链缺失：")
        for item in check["missing"]:
            print(f"  - {item}")
        print("请检查 mt3000_root 或环境变量 MT3000_ROOT。")
        return 2

    result = compiler.compile_device_file(
        input_path,
        keep_artifacts=args.keep_artifacts,
        extra_include_dirs=[str(PROJECT_ROOT), os.path.dirname(input_path)],
    )
    success = result["success"]
    outputs = result["outputs"]

    if args.report.strip():
        report_path = os.path.abspath(args.report)
    else:
        report_path = os.path.abspath("output/reports/compile_test_PLACEHOLDER.log")
    ensure_parent(report_path)
    report_dir = os.path.dirname(report_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_ts_path = os.path.join(report_dir, f"compile_test_{ts}.log")

    report_text = format_raw_report(input_path=input_path, mt3000_root=mt3000_root, outputs=outputs, success=success)
    final_report_path = report_path if args.report.strip() else report_ts_path
    with open(final_report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"[输入] {input_path}")
    print(f"[环境] {mt3000_root}")
    print("[结果]")
    print(summarize(outputs))
    print(f"[报告] {final_report_path}")

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())


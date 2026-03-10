#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DEFAULT_MT3000_ROOT = "/thfs3/software/programming_env/mt3000_programming_env"


def load_mt3000_root(config_path: str = "config.json") -> str:
    """
    只加载编译相关配置，不依赖任何 LLM API 字段。
    优先使用环境变量 MT3000_ROOT，其次读取 config.json，最后回退默认路径。
    """
    env_root = os.environ.get("MT3000_ROOT", "").strip()
    if env_root:
        return env_root

    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return str(cfg.get("mt3000_root", DEFAULT_MT3000_ROOT)).strip() or DEFAULT_MT3000_ROOT
        except (OSError, json.JSONDecodeError):
            return DEFAULT_MT3000_ROOT

    return DEFAULT_MT3000_ROOT


@dataclass
class StepResult:
    step: str
    success: bool
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "success": self.success,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class MT3000Compiler:
    def __init__(self, mt3000_root: Optional[str] = None):
        self.mt3000_root = mt3000_root or load_mt3000_root()
        self._setup_paths()
        self._setup_flags()
        self._setup_runtime_env()

    def _setup_paths(self) -> None:
        self.dev_cc_root = os.path.join(self.mt3000_root, "dsp_compiler")
        self.hthreads_root = os.path.join(self.mt3000_root, "hthreads")
        self.libvm_root = os.path.join(self.mt3000_root, "libvm")

        self.dev_cc_bin = os.path.join(self.dev_cc_root, "bin")
        self.dev_cc = os.path.join(self.dev_cc_bin, "MT-3000-gcc")
        self.dev_ld = os.path.join(self.dev_cc_bin, "MT-3000-ld")
        self.dev_makedat = os.path.join(self.dev_cc_bin, "MT-3000-makedat")

        self.dev_cc_include = os.path.join(self.dev_cc_root, "include")
        self.dev_cc_lib = os.path.join(self.dev_cc_root, "lib")
        self.hthreads_include = os.path.join(self.hthreads_root, "include")
        self.hthreads_lib = os.path.join(self.hthreads_root, "lib")
        self.libvm_include = os.path.join(self.libvm_root, "include")
        self.libvm_lib = os.path.join(self.libvm_root, "lib")

    def _setup_flags(self) -> None:
        self.dev_cflags = [
            "-Wall",
            "-Wno-attributes",
            "-Wno-unused-function",
            "-O2",
            "-fenable-m3000",
            "-ffunction-sections",
            "-flax-vector-conversions",
            f"-I{self.dev_cc_include}",
            f"-I{self.hthreads_include}",
            f"-I{self.libvm_include}",
        ]

        self.dev_ldflags = [
            f"-L{self.dev_cc_lib}",
            f"-L{self.hthreads_lib}",
            f"-L{self.libvm_lib}",
            "--gc-sections",
            f"-T{self.hthreads_lib}/dsp.lds",
            "-lhthread_device",
            "-lvm",
            f"{self.dev_cc_lib}/slib3000.a",
            f"{self.dev_cc_root}/lib/vlib3000.a",
        ]

    def _setup_runtime_env(self) -> None:
        third_party = os.path.join(self.mt3000_root, "third-party-lib")
        cur = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = f"{third_party}:{cur}" if cur else third_party

    def _run(self, step: str, cmd: List[str], timeout_sec: int = 300) -> StepResult:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
            return StepResult(
                step=step,
                success=(p.returncode == 0),
                returncode=p.returncode,
                stdout=p.stdout,
                stderr=p.stderr,
            )
        except subprocess.TimeoutExpired:
            return StepResult(step=step, success=False, returncode=-1, stdout="", stderr="Command timeout")
        except FileNotFoundError:
            return StepResult(step=step, success=False, returncode=-1, stdout="", stderr=f"Command not found: {cmd[0]}")

    def check_toolchain(self) -> Dict[str, Any]:
        tools = [self.dev_cc, self.dev_ld, self.dev_makedat]
        missing = [t for t in tools if not os.path.isfile(t)]
        return {"ok": len(missing) == 0, "missing": missing}

    def compile_device_file(
        self,
        dev_c_file: str,
        keep_artifacts: bool = False,
        extra_include_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not os.path.isfile(dev_c_file):
            return {
                "success": False,
                "outputs": [
                    StepResult(
                        step="file_check",
                        success=False,
                        returncode=-1,
                        stdout="",
                        stderr=f"File not found: {dev_c_file}",
                    ).to_dict()
                ],
            }

        base = dev_c_file[:-6] if dev_c_file.endswith(".dev.c") else os.path.splitext(dev_c_file)[0]
        dev_o = f"{base}.dev.o"
        dev_out = f"{base}.dev.out"

        outputs: List[StepResult] = []

        compile_cmd = [self.dev_cc, "-c", *self.dev_cflags]
        if extra_include_dirs:
            seen = set()
            for inc in extra_include_dirs:
                path = os.path.abspath(inc)
                if os.path.isdir(path) and path not in seen:
                    compile_cmd.append(f"-I{path}")
                    seen.add(path)
        compile_cmd.extend([dev_c_file, "-o", dev_o])
        compile_res = self._run("compile", compile_cmd)
        outputs.append(compile_res)
        if not compile_res.success:
            return {"success": False, "outputs": [o.to_dict() for o in outputs]}

        link_res = self._run("link", [self.dev_ld, dev_o, *self.dev_ldflags, "-o", dev_out])
        outputs.append(link_res)
        if not link_res.success:
            return {"success": False, "outputs": [o.to_dict() for o in outputs]}

        makedat_res = self._run("makedat", [self.dev_makedat, "-J", dev_out])
        outputs.append(makedat_res)

        if makedat_res.success and not keep_artifacts:
            for f in (dev_o, dev_out):
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError as e:
                        outputs.append(
                            StepResult(
                                step="cleanup",
                                success=False,
                                returncode=-1,
                                stdout="",
                                stderr=f"Failed removing {f}: {e}",
                            )
                        )

        return {"success": makedat_res.success, "outputs": [o.to_dict() for o in outputs]}


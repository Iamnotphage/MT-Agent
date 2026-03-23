"""ReadFile 工具 — 读取文件内容（支持行范围、自动截断）

仿 Gemini CLI read_file：路径安全校验 → 行切片 → 截断提示。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from tools.base import BaseTool, ToolResult, ToolRiskLevel

MAX_LINES = 500
MAX_CHARS = 50_000


class ReadFileArgs(BaseModel):
    file_path: str = Field(description="要读取的文件路径（相对于工作区）")
    start_line: Optional[int] = Field(None, ge=1, description="起始行号 (1-based)")
    end_line: Optional[int] = Field(None, ge=1, description="结束行号 (1-based, 含)")


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "读取指定文件的内容。支持通过 start_line / end_line 读取指定行范围。"
        "大文件会自动截断并提示如何继续读取。"
    )
    risk_level = ToolRiskLevel.LOW
    args_schema = ReadFileArgs

    def __init__(self, *, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or os.getcwd()).resolve()

    async def execute(
        self,
        *,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ToolResult:
        resolved = (self.workspace / file_path).resolve()

        if not str(resolved).startswith(str(self.workspace)):
            return ToolResult(output="", error=f"路径越界: {file_path} 不在工作区内")

        if not resolved.is_file():
            return ToolResult(output="", error=f"文件不存在: {file_path}")

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ToolResult(output="", error=f"读取失败: {e}")

        lines = text.splitlines(keepends=True)
        total = len(lines)

        lo = (start_line - 1) if start_line else 0
        hi = end_line if end_line else total
        lo, hi = max(0, min(lo, total)), max(0, min(hi, total))
        selected = lines[lo:hi]

        truncated = False
        if len(selected) > MAX_LINES:
            selected = selected[:MAX_LINES]
            truncated = True

        content = "".join(selected)
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS]
            truncated = True

        shown_lo = lo + 1
        shown_hi = lo + len(selected)

        header = f"File: {file_path}  (lines {shown_lo}–{shown_hi} of {total})"
        if truncated:
            header += (
                f"\n⚠ 内容已截断 (上限 {MAX_LINES} 行 / {MAX_CHARS} 字符)。"
                f" 使用 start_line={shown_hi + 1} 继续读取。"
            )

        return ToolResult(
            output=f"{header}\n\n{content}",
            display=f"{file_path} ({shown_hi - shown_lo + 1} lines)",
            metadata={"total_lines": total, "truncated": truncated},
        )

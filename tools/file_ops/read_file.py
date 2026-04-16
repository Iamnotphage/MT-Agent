"""ReadFile 工具 — 读取文件内容（支持行范围、自动截断）"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.tools.base import ToolException
from pydantic import BaseModel, Field

from tools.base import BaseTool, ToolRiskLevel

MAX_LINES = 500
MAX_CHARS = 50_000


class ReadFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to read (relative to workspace)")
    start_line: int | None = Field(None, ge=1, description="Start line number (1-based, inclusive)")
    end_line: int | None = Field(None, ge=1, description="End line number (1-based, inclusive)")


class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = (
        "Read file contents. Supports line range selection via start_line/end_line. "
        "Large files are automatically truncated with guidance on how to continue reading."
    )
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    response_format: str = "content_and_artifact"
    args_schema: type = ReadFileArgs
    workspace: Path = Field(default_factory=lambda: Path.cwd())

    def __init__(self, *, workspace: str | Path | None = None, **kwargs: Any) -> None:
        super().__init__(workspace=Path(workspace or os.getcwd()).resolve(), **kwargs)

    def _run(
        self,
        *,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> tuple[str, dict]:
        resolved = (self.workspace / file_path).resolve()

        if not str(resolved).startswith(str(self.workspace)):
            raise ToolException(f"路径越界: {file_path} 不在工作区内")

        if not resolved.is_file():
            raise ToolException(f"文件不存在: {file_path}")

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise ToolException(f"读取失败: {e}")

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
                f"\n⚠ Content truncated (limit: {MAX_LINES} lines / {MAX_CHARS} chars). "
                f"Use start_line={shown_hi + 1} to continue reading."
            )

        return (
            f"{header}\n\n{content}",
            {
                "display": f"{file_path} ({shown_hi - shown_lo + 1} lines)",
                "total_lines": total,
                "truncated": truncated,
            },
        )

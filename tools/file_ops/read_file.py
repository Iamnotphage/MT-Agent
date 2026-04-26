"""ReadFile 工具 — 读取文件内容（支持行范围、自动截断）"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.tools.base import ToolException
from pydantic import BaseModel, Field, PrivateAttr

from tools.base import BaseTool, ToolRiskLevel

MAX_LINES = 500
MAX_CHARS = 50_000


class ReadFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to read (relative to workspace)")
    offset: int | None = Field(
        None,
        ge=1,
        description="Start line number to read from (1-based, inclusive).",
    )
    limit: int | None = Field(
        None,
        ge=1,
        description="Maximum number of lines to read from the offset.",
    )


class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = (
        "Read file contents. Supports targeted reads via offset and limit. "
        "Returns line-numbered content for the model and structured file data for transcript recovery."
    )
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    response_format: str = "content_and_artifact"
    args_schema: type = ReadFileArgs
    workspace: Path = Field(default_factory=lambda: Path.cwd())
    _read_state: dict[tuple[str, int, int | None], float] = PrivateAttr(default_factory=dict)

    def __init__(self, *, workspace: str | Path | None = None, **kwargs: Any) -> None:
        super().__init__(workspace=Path(workspace or os.getcwd()).resolve(), **kwargs)

    def _run(
        self,
        *,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None,
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
        start_line = offset or 1
        lo = max(0, min(start_line - 1, total))
        requested_limit = limit
        hi = min(lo + requested_limit, total) if requested_limit is not None else total
        selected = lines[lo:hi]

        mtime = resolved.stat().st_mtime
        state_key = (file_path, start_line, requested_limit)
        if self._read_state.get(state_key) == mtime:
            shown_hi = start_line + max(len(selected) - 1, 0)
            return (
                "File unchanged since last read for the same range.",
                {
                    "display": f"{file_path} unchanged",
                    "toolUseResult": {
                        "type": "file_unchanged",
                        "input": {
                            "file_path": file_path,
                            "offset": start_line,
                            "limit": requested_limit,
                        },
                        "file": {
                            "filePath": file_path,
                            "startLine": start_line,
                            "numLines": len(selected),
                            "totalLines": total,
                            "endLine": shown_hi,
                        },
                    },
                },
            )

        truncated = False
        if len(selected) > MAX_LINES:
            selected = selected[:MAX_LINES]
            truncated = True

        content = "".join(selected)
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS]
            truncated = True

        shown_lo = start_line
        shown_hi = shown_lo + max(len(selected) - 1, 0)
        raw_content = content
        line_numbered = _add_line_numbers(raw_content, shown_lo)

        if raw_content:
            llm_content = line_numbered
            if truncated:
                llm_content += (
                    f"\n\n<system-reminder>\nContent truncated. "
                    f"Use offset={shown_hi + 1} limit={requested_limit or MAX_LINES} to continue reading.\n"
                    "</system-reminder>"
                )
        elif total == 0:
            llm_content = (
                "<system-reminder>\nWarning: the file exists but the contents are empty.\n"
                "</system-reminder>"
            )
        else:
            llm_content = (
                f"<system-reminder>\nWarning: the file exists but is shorter than the provided offset ({shown_lo}). "
                f"The file has {total} lines.\n</system-reminder>"
            )

        tool_use_result = {
            "type": "text",
            "input": {
                "file_path": file_path,
                "offset": shown_lo,
                "limit": requested_limit,
            },
            "file": {
                "filePath": file_path,
                "content": raw_content,
                "startLine": shown_lo,
                "numLines": len(selected),
                "totalLines": total,
                "truncated": truncated,
                "endLine": shown_hi,
            },
        }

        self._read_state[state_key] = mtime

        return (
            llm_content,
            {
                "display": f"{file_path} ({len(selected)} lines)",
                "total_lines": total,
                "truncated": truncated,
                "toolUseResult": tool_use_result,
            },
        )


def _add_line_numbers(content: str, start_line: int) -> str:
    if not content:
        return ""
    numbered_lines = []
    for index, line in enumerate(content.splitlines(), start=start_line):
        numbered_lines.append(f"{index}\t{line}")
    suffix = "\n" if content.endswith("\n") else ""
    return "\n".join(numbered_lines) + suffix

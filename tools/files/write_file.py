"""WriteFile 工具 — 写入/创建文件"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.tools.base import ToolException
from pydantic import BaseModel, Field

from core.utils.diff import generate_diff
from tools.base import BaseTool, ToolRiskLevel
from tools.workspace_paths import display_path, resolve_workspace_path


class WriteFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to write (relative to workspace)")
    content: str = Field(description="Complete file content to write")


class WriteFileTool(BaseTool):
    name: str = "write_file"
    description: str = (
        "Write content to a file. Creates the file and parent directories if they don't exist. "
        "If the file exists, it will be overwritten and a diff is returned for review. "
        "Must provide complete file content."
    )
    risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM
    response_format: str = "content_and_artifact"
    args_schema: type = WriteFileArgs
    workspace: Path = Field(default_factory=lambda: Path.cwd())

    def __init__(self, *, workspace: str | Path | None = None, **kwargs: Any) -> None:
        super().__init__(workspace=Path(workspace or os.getcwd()).resolve(), **kwargs)

    def _run(self, *, file_path: str, content: str) -> tuple[str, dict]:
        resolved = resolve_workspace_path(self.workspace, file_path)
        display = display_path(self.workspace, resolved)

        if resolved.exists() and resolved.is_dir():
            raise ToolException(f"Target is a directory, not a file: {file_path}")

        is_new = not resolved.exists()

        original = ""
        if not is_new:
            try:
                original = resolved.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                raise ToolException(f"Failed to read original file: {e}")

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except PermissionError:
            raise ToolException(f"Permission denied: {file_path}")
        except OSError as e:
            raise ToolException(f"Write failed: {e}")

        diff = generate_diff(display, original, content, is_new=is_new)

        action = "Created" if is_new else "Overwrote"
        total_lines = len(content.splitlines())
        llm_output = f"{action} file: {display} ({total_lines} lines, {diff.stat})"
        if diff.unified_diff:
            preview = diff.unified_diff[:2000]
            if len(diff.unified_diff) > 2000:
                preview += "\n... (diff truncated)"
            llm_output += f"\n\nDiff:\n{preview}"

        return (
            llm_output,
            {
                "display": f"{display} ({diff.stat})",
                "is_new": is_new,
                "lines": total_lines,
                "diff": diff,
            },
        )

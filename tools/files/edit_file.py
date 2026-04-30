"""Edit tool — replace text within files"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.tools.base import ToolException
from pydantic import BaseModel, Field

from core.utils.diff import generate_diff
from tools.base import BaseTool, ToolRiskLevel
from tools.workspace_paths import display_path, resolve_workspace_path


class EditFileArgs(BaseModel):
    file_path: str = Field(description="Path to the file to edit (relative to workspace)")
    old_string: str = Field(description="Exact literal text to find and replace")
    new_string: str = Field(description="Exact literal text to replace with")
    allow_multiple: bool = Field(
        default=False,
        description="If true, replace all occurrences. If false, only succeed if exactly one occurrence found.",
    )


class EditFileTool(BaseTool):
    name: str = "edit_file"
    description: str = (
        "Replace text within a file. By default, expects exactly one occurrence of old_string. "
        "Set allow_multiple=true to replace all occurrences. "
        "Returns a diff showing the changes made."
    )
    risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM
    response_format: str = "content_and_artifact"
    args_schema: type = EditFileArgs
    workspace: Path = Field(default_factory=lambda: Path.cwd())

    def __init__(self, *, workspace: str | Path | None = None, **kwargs: Any) -> None:
        super().__init__(workspace=Path(workspace or os.getcwd()).resolve(), **kwargs)

    def _run(
        self,
        *,
        file_path: str,
        old_string: str,
        new_string: str,
        allow_multiple: bool = False,
    ) -> tuple[str, dict]:
        resolved = resolve_workspace_path(self.workspace, file_path)
        display = display_path(self.workspace, resolved)

        if resolved.exists() and resolved.is_dir():
            raise ToolException(f"Target is a directory, not a file: {file_path}")

        is_new = not resolved.exists()

        if is_new and old_string != "":
            raise ToolException(f"File does not exist: {file_path}. Use empty old_string to create new file.")

        original = ""
        if not is_new:
            try:
                original = resolved.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                raise ToolException(f"Failed to read file: {e}")

        if is_new:
            new_content = new_string
            occurrences = 1
        else:
            if old_string == "":
                raise ToolException(f"File already exists: {file_path}. Cannot create with empty old_string.")

            if old_string == new_string:
                raise ToolException("old_string and new_string are identical. No changes to apply.")

            occurrences = original.count(old_string)

            if occurrences == 0:
                raise ToolException(f"Failed to find old_string in {file_path}. String not found.")

            if not allow_multiple and occurrences != 1:
                raise ToolException(
                    f"Expected 1 occurrence but found {occurrences}. Set allow_multiple=true to replace all.",
                )

            new_content = original.replace(old_string, new_string)

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(new_content, encoding="utf-8")
        except PermissionError:
            raise ToolException(f"Permission denied: {file_path}")
        except OSError as e:
            raise ToolException(f"Write failed: {e}")

        diff = generate_diff(display, original, new_content, is_new=is_new)

        action = "Created" if is_new else "Modified"
        total_lines = len(new_content.splitlines())
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
                "occurrences": occurrences,
                "diff": diff,
            },
        )

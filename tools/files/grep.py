"""Grep tool — search for regex patterns in files"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from langchain_core.tools.base import ToolException
from pydantic import BaseModel, Field

from tools.base import BaseTool, ToolRiskLevel
from tools.workspace_paths import resolve_workspace_path

_ALWAYS_IGNORE = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


class GrepArgs(BaseModel):
    pattern: str = Field(
        description="Regular expression pattern to search for (e.g., 'function\\s+\\w+')"
    )
    path: str | None = Field(
        default=None,
        description="Directory path to search within (relative to workspace). If omitted, searches workspace root.",
    )
    include: str | None = Field(
        default=None,
        description="Glob pattern to filter files (e.g., '*.py', 'src/**/*.ts')",
    )


class GrepTool(BaseTool):
    name: str = "grep"
    description: str = (
        "Search for a regular expression pattern within file contents. "
        "Returns matching lines with file paths and line numbers. "
        "Supports file filtering via glob patterns."
    )
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    response_format: str = "content_and_artifact"
    args_schema: type = GrepArgs
    workspace: Path = Field(default_factory=lambda: Path.cwd())

    def __init__(self, *, workspace: str | Path | None = None, **kwargs: Any) -> None:
        super().__init__(workspace=Path(workspace or os.getcwd()).resolve(), **kwargs)

    def _run(
        self,
        *,
        pattern: str,
        path: str | None = None,
        include: str | None = None,
    ) -> tuple[str, dict]:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise ToolException(f"Invalid regex pattern: {e}")

        resolved = resolve_workspace_path(self.workspace, path or ".")

        if not resolved.exists():
            raise ToolException(f"Directory does not exist: {path}")

        if not resolved.is_dir():
            raise ToolException(f"Path is not a directory: {path}")

        matches = []
        try:
            if include:
                files = list(resolved.glob(include))
            else:
                files = list(resolved.rglob("*"))

            for file_path in files:
                if not file_path.is_file():
                    continue

                parts = file_path.relative_to(self.workspace).parts
                if any(part in _ALWAYS_IGNORE for part in parts):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = str(file_path.relative_to(self.workspace))
                                matches.append((rel_path, line_num, line.rstrip()))
                except (OSError, IOError):
                    continue

        except Exception as e:
            raise ToolException(f"Search failed: {e}")

        if not matches:
            msg = f'Found 0 matches for pattern "{pattern}"'
            if path:
                msg += f' in "{path}"'
            if include:
                msg += f' (filter: "{include}")'
            return msg, {"display": msg}

        lines = []
        current_file = None
        for file_path, line_num, line_content in matches:
            if file_path != current_file:
                if current_file is not None:
                    lines.append("---")
                lines.append(f"File: {file_path}")
                current_file = file_path
            lines.append(f"L{line_num}: {line_content}")

        listing = "\n".join(lines)
        llm_output = f'Found {len(matches)} match(es) for pattern "{pattern}"'
        if path:
            llm_output += f' in "{path}"'
        if include:
            llm_output += f' (filter: "{include}")'
        llm_output += f":\n---\n{listing}"

        display = f'"{pattern}" — {len(matches)} match(es)'
        if include:
            display += f' in {include}'

        return llm_output, {"display": display}

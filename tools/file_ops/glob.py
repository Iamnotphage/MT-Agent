"""Glob 工具 — 查找匹配特定 glob 模式的文件"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.tools.base import ToolException
from pydantic import BaseModel, Field

from tools.base import BaseTool, ToolRiskLevel

_ALWAYS_IGNORE = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


class GlobArgs(BaseModel):
    pattern: str = Field(
        description="The glob pattern to match against (e.g., '*.py', 'src/**/*.js')"
    )
    path: str | None = Field(
        default=None,
        description="The absolute path to the directory to search within. If omitted, searches the tool's root directory.",
    )
    case_sensitive: bool = Field(
        default=False,
        description="Whether the search should be case-sensitive.",
    )
    respect_git_ignore: bool = Field(
        default=True,
        description="Whether to respect .gitignore patterns when finding files.",
    )


class GlobTool(BaseTool):
    name: str = "glob"
    description: str = (
        "Finds files matching specific glob patterns across the workspace. "
        "Returns a list of absolute paths sorted by modification time (newest first). "
        "Ignores common nuisance directories like node_modules and .git by default."
    )
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    response_format: str = "content_and_artifact"
    args_schema: type = GlobArgs
    workspace: Path = Field(default_factory=lambda: Path.cwd())

    def __init__(self, *, workspace: str | Path | None = None, **kwargs: Any) -> None:
        super().__init__(workspace=Path(workspace or os.getcwd()).resolve(), **kwargs)

    def _run(
        self,
        *,
        pattern: str,
        path: str | None = None,
        case_sensitive: bool = False,
        respect_git_ignore: bool = True,
    ) -> tuple[str, dict]:
        search_dir = self.workspace / (path or ".")
        resolved = search_dir.resolve()

        if not str(resolved).startswith(str(self.workspace)):
            raise ToolException(f"Path out of bounds: {path} is not within workspace")

        if not resolved.exists():
            raise ToolException(f"Directory does not exist: {path}")

        if not resolved.is_dir():
            raise ToolException(f"Path is not a directory: {path}")

        try:
            matches = list(resolved.glob(pattern))
        except (ValueError, OSError) as e:
            raise ToolException(f"Glob pattern error: {e}")

        filtered = []
        for match in matches:
            if not str(match).startswith(str(self.workspace)):
                continue

            parts = match.relative_to(self.workspace).parts
            if any(part in _ALWAYS_IGNORE for part in parts):
                continue

            filtered.append(match)

        if not filtered:
            msg = f'Found 0 file(s) matching "{pattern}" within {path or "."}'
            return msg, {"display": msg}

        filtered.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        rel_paths = [str(p.relative_to(self.workspace)) for p in filtered]
        listing = "\n".join(rel_paths)
        llm_output = f'Found {len(filtered)} file(s) matching "{pattern}" within {path or "."}, sorted by modification time (newest first):\n{listing}'
        display = f'{path or "."} — {len(filtered)} file(s) matching "{pattern}"'

        return llm_output, {"display": display}

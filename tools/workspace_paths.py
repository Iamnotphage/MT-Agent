from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools.base import ToolException


def _real(p: Path) -> Path:
    """Resolve symlinks and normalize — unlike Path.resolve(), this follows
    symlinks on macOS (e.g. /tmp → /private/tmp)."""
    return Path(os.path.realpath(p))


def ensure_within_workspace(workspace: Path, candidate: Path, *, original_path: str | None = None) -> Path:
    workspace_resolved = _real(workspace)
    candidate_resolved = _real(candidate)
    try:
        candidate_resolved.relative_to(workspace_resolved)
    except ValueError as exc:
        bad_path = original_path if original_path is not None else str(candidate)
        raise ToolException(f"路径越界: {bad_path} 不在工作区内") from exc
    return candidate_resolved


def resolve_workspace_path(workspace: Path, user_path: str) -> Path:
    workspace_resolved = _real(workspace)
    raw = Path(user_path).expanduser()
    candidate = raw if raw.is_absolute() else workspace_resolved / raw
    return ensure_within_workspace(workspace_resolved, candidate, original_path=user_path)


def display_path(workspace: Path, resolved: Path) -> str:
    """Return a human-friendly path string for tool output.

    Paths inside *workspace* are shown as relative paths; paths outside are
    left as absolute paths.
    """
    workspace_resolved = _real(workspace)
    resolved_real = _real(resolved)
    try:
        return str(resolved_real.relative_to(workspace_resolved))
    except ValueError:
        return str(resolved_real)

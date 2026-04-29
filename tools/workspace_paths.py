from __future__ import annotations

from pathlib import Path

from langchain_core.tools.base import ToolException


def ensure_within_workspace(workspace: Path, candidate: Path, *, original_path: str | None = None) -> Path:
    workspace_resolved = Path(workspace).resolve()
    candidate_resolved = Path(candidate).resolve()
    try:
        candidate_resolved.relative_to(workspace_resolved)
    except ValueError as exc:
        bad_path = original_path if original_path is not None else str(candidate)
        raise ToolException(f"路径越界: {bad_path} 不在工作区内") from exc
    return candidate_resolved


def resolve_workspace_path(workspace: Path, user_path: str) -> Path:
    workspace_resolved = Path(workspace).resolve()
    raw = Path(user_path).expanduser()
    candidate = raw if raw.is_absolute() else workspace_resolved / raw
    return ensure_within_workspace(workspace_resolved, candidate, original_path=user_path)

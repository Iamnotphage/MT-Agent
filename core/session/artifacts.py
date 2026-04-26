"""Session artifact path and storage helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
TOOL_RESULTS_SUBDIR = "tool-results"
SESSION_MEMORY_SUBDIR = "session-memory"


def _project_hash(working_directory: str) -> str:
    return hashlib.md5(str(Path(working_directory).resolve()).encode()).hexdigest()[:10]


def get_history_dir(working_directory: str, config: dict[str, Any]) -> Path:
    global_dir = Path(config.get("global_dir", "~/.mtagent")).expanduser()
    return global_dir / "history" / _project_hash(working_directory)


def get_artifacts_root(working_directory: str, config: dict[str, Any]) -> Path:
    return get_history_dir(working_directory, config) / "artifacts"


def get_session_artifact_dir(
    working_directory: str,
    config: dict[str, Any],
    session_id: str,
) -> Path:
    return get_artifacts_root(working_directory, config) / session_id


def get_tool_results_dir(
    working_directory: str,
    config: dict[str, Any],
    session_id: str,
) -> Path:
    return get_session_artifact_dir(working_directory, config, session_id) / TOOL_RESULTS_SUBDIR


def get_session_memory_dir(
    working_directory: str,
    config: dict[str, Any],
    session_id: str,
) -> Path:
    return get_session_artifact_dir(working_directory, config, session_id) / SESSION_MEMORY_SUBDIR


def get_tool_result_path(
    working_directory: str,
    config: dict[str, Any],
    session_id: str,
    tool_call_id: str,
    suffix: str = ".txt",
) -> Path:
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    return get_tool_results_dir(working_directory, config, session_id) / f"{tool_call_id}{ext}"


def ensure_session_artifact_dirs(
    working_directory: str,
    config: dict[str, Any],
    session_id: str,
) -> None:
    get_tool_results_dir(working_directory, config, session_id).mkdir(parents=True, exist_ok=True)
    get_session_memory_dir(working_directory, config, session_id).mkdir(parents=True, exist_ok=True)


def write_text_artifact(
    path: Path,
    content: str,
    *,
    session_artifact_dir: Path,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> dict[str, Any]:
    encoded = content.encode("utf-8")
    truncated = len(encoded) > max_bytes
    if truncated:
        encoded = encoded[:max_bytes]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return {
        "relative_path": path.relative_to(session_artifact_dir).as_posix(),
        "size_bytes": len(encoded),
        "truncated": truncated,
    }


def read_text_artifact(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def resolve_session_relative_artifact(
    working_directory: str,
    config: dict[str, Any],
    session_id: str,
    relative_path: str,
) -> Path:
    return get_session_artifact_dir(working_directory, config, session_id) / relative_path

"""Tool result budgeting and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage

from core.session.artifacts import write_text_artifact

DEFAULT_MAX_RESULT_SIZE_CHARS = 50_000
MAX_TOOL_RESULTS_PER_MESSAGE_CHARS = 200_000
MAX_TOOL_RESULT_BYTES = 64 * 1024 * 1024
PREVIEW_MAX_CHARS = 2_000
PERSISTED_OUTPUT_OPEN = "<persisted-output>"
PERSISTED_OUTPUT_CLOSE = "</persisted-output>"

SPECIAL_TOOL_NAMES = {"read_file"}
TOOL_THRESHOLDS = {
    "grep": 20_000,
    "bash": 30_000,
    "shell": 30_000,
    "powershell": 30_000,
}


@dataclass
class ToolResultDecision:
    tool_name: str
    tool_call_id: str
    original_chars: int
    content: str
    tool_use_result: dict[str, Any]
    artifact_meta: dict[str, Any] | None
    persisted: bool
    reason: str | None


@dataclass
class ToolResultCandidate:
    tool_name: str
    tool_call_id: str
    content: str
    tool_message: ToolMessage
    display: str
    artifact: dict[str, Any]
    eligible_for_persistence: bool
    already_persisted: bool = False
    original_chars: int = 0


def build_generic_tool_use_result(
    *,
    tool_name: str,
    input_args: dict[str, Any] | None,
    raw_content: str,
) -> dict[str, Any]:
    return {
        "type": tool_name,
        "input": dict(input_args or {}),
        "result": {
            "rawText": raw_content,
        },
    }


def get_tool_result_threshold(tool_name: str) -> int | float:
    if tool_name in SPECIAL_TOOL_NAMES:
        return float("inf")
    return TOOL_THRESHOLDS.get(tool_name, DEFAULT_MAX_RESULT_SIZE_CHARS)


def is_special_tool(tool_name: str) -> bool:
    return tool_name in SPECIAL_TOOL_NAMES


def stringify_tool_result_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def estimate_result_chars(content: Any) -> int:
    return len(stringify_tool_result_content(content))


def generate_preview(content: str, max_chars: int = PREVIEW_MAX_CHARS) -> tuple[str, bool]:
    if len(content) <= max_chars:
        return content, False
    truncated = content[:max_chars]
    last_newline = truncated.rfind("\n")
    if last_newline > max_chars // 2:
        return truncated[:last_newline], True
    return truncated, True


def build_persisted_output_message(
    *,
    tool_name: str,
    relative_path: str,
    original_chars: int,
    preview: str,
) -> str:
    return (
        f'{PERSISTED_OUTPUT_OPEN} tool="{tool_name}" path="{relative_path}" '
        f'original_chars="{original_chars}">\n'
        "Output too large. Full output saved to session artifact.\n\n"
        "Preview:\n"
        f"{preview}\n"
        f"{PERSISTED_OUTPUT_CLOSE}"
    )


def is_persisted_output_message(content: str) -> bool:
    return content.startswith(PERSISTED_OUTPUT_OPEN)


def build_tool_use_result_metadata(
    *,
    tool_name: str,
    original_chars: int,
    preview_chars: int,
    truncated: bool,
    artifact_path: str | None,
    persistence_reason: str | None,
) -> dict[str, Any]:
    return {
        "kind": "text",
        "tool_name": tool_name,
        "artifact": artifact_path,
        "original_chars": original_chars,
        "preview_chars": preview_chars,
        "truncated": truncated,
        "persistence_reason": persistence_reason,
    }


def merge_budget_metadata(
    tool_use_result: dict[str, Any] | None,
    *,
    tool_name: str,
    input_args: dict[str, Any] | None,
    raw_content: str,
    artifact_path: str | None,
    original_chars: int,
    preview_chars: int,
    truncated: bool,
    persistence_reason: str | None,
) -> dict[str, Any]:
    merged = dict(
        tool_use_result
        or build_generic_tool_use_result(
            tool_name=tool_name,
            input_args=input_args,
            raw_content=raw_content,
        )
    )
    if artifact_path:
        result = dict(merged.get("result") or {})
        raw_text = result.get("rawText")
        if isinstance(raw_text, str):
            preview, _ = generate_preview(raw_text, preview_chars)
            result.pop("rawText", None)
            result["preview"] = preview
            merged["result"] = result
    merged["budget"] = build_tool_use_result_metadata(
        tool_name=tool_name,
        original_chars=original_chars,
        preview_chars=preview_chars,
        truncated=truncated,
        artifact_path=artifact_path,
        persistence_reason=persistence_reason,
    )
    return merged


def extract_tool_use_result(tool_message: ToolMessage) -> dict[str, Any] | None:
    artifact = dict(tool_message.artifact or {})
    tool_use_result = artifact.get("toolUseResult")
    return dict(tool_use_result) if isinstance(tool_use_result, dict) else None


def apply_transcript_metadata(
    tool_message: ToolMessage,
    *,
    display: str,
    tool_use_result: dict[str, Any],
    artifact_meta: dict[str, Any] | None,
) -> None:
    artifact = dict(tool_message.artifact or {})
    artifact["display"] = display
    artifact["toolUseResult"] = tool_use_result
    artifact["artifact_meta"] = artifact_meta
    tool_message.artifact = artifact


def maybe_persist_tool_result(
    *,
    tool_name: str,
    tool_call_id: str,
    content: str,
    display: str,
    artifact_dir: Path,
    artifact_path: Path,
    threshold: int | float,
    reason: str,
) -> ToolResultDecision:
    original_chars = len(content)
    if original_chars <= threshold or not content or is_persisted_output_message(content):
        tool_use_result = build_tool_use_result_metadata(
            tool_name=tool_name,
            original_chars=original_chars,
            preview_chars=original_chars,
            truncated=False,
            artifact_path=None,
            persistence_reason=None,
        )
        return ToolResultDecision(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            original_chars=original_chars,
            content=content,
            tool_use_result=tool_use_result,
            artifact_meta=None,
            persisted=False,
            reason=None,
        )

    artifact_result = write_text_artifact(
        artifact_path,
        content,
        session_artifact_dir=artifact_dir,
        max_bytes=MAX_TOOL_RESULT_BYTES,
    )
    preview, _ = generate_preview(content)
    relative_path = artifact_result["relative_path"]
    llm_content = build_persisted_output_message(
        tool_name=tool_name,
        relative_path=relative_path,
        original_chars=original_chars,
        preview=preview,
    )
    tool_use_result = build_tool_use_result_metadata(
        tool_name=tool_name,
        original_chars=original_chars,
        preview_chars=len(preview),
        truncated=True,
        artifact_path=relative_path,
        persistence_reason=reason,
    )
    artifact_meta = {
        "path": relative_path,
        "kind": "text",
        "size_bytes": artifact_result["size_bytes"],
        "truncated": artifact_result["truncated"],
    }
    return ToolResultDecision(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        original_chars=original_chars,
        content=llm_content,
        tool_use_result=tool_use_result,
        artifact_meta=artifact_meta,
        persisted=True,
        reason=reason,
    )


def candidate_from_tool_message(
    *,
    tool_name: str,
    tool_call_id: str,
    tool_message: ToolMessage,
) -> ToolResultCandidate:
    artifact = dict(tool_message.artifact or {})
    content = stringify_tool_result_content(tool_message.content)
    return ToolResultCandidate(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        content=content,
        tool_message=tool_message,
        display=str(artifact.get("display", "")),
        artifact=artifact,
        eligible_for_persistence=not is_special_tool(tool_name),
        already_persisted=is_persisted_output_message(content),
        original_chars=len(content),
    )


def apply_aggregate_budget(
    candidates: list[ToolResultCandidate],
    *,
    artifact_dir: Path,
    artifact_path_for_call: callable,
    aggregate_limit: int = MAX_TOOL_RESULTS_PER_MESSAGE_CHARS,
) -> list[ToolResultDecision]:
    total_chars = sum(len(candidate.content) for candidate in candidates)
    if total_chars <= aggregate_limit:
        return []

    decisions: list[ToolResultDecision] = []
    sortable = sorted(
        (
            candidate for candidate in candidates
            if candidate.eligible_for_persistence and not candidate.already_persisted
        ),
        key=lambda candidate: (-candidate.original_chars, candidate.tool_call_id),
    )
    remaining = total_chars
    for candidate in sortable:
        if remaining <= aggregate_limit:
            break
        decision = maybe_persist_tool_result(
            tool_name=candidate.tool_name,
            tool_call_id=candidate.tool_call_id,
            content=candidate.content,
            display=candidate.display,
            artifact_dir=artifact_dir,
            artifact_path=artifact_path_for_call(candidate.tool_call_id),
            threshold=0,
            reason="aggregate-limit",
        )
        decisions.append(decision)
        remaining = remaining - candidate.original_chars + len(decision.content)
    return decisions

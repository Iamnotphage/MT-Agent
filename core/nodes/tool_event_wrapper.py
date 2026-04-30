"""ToolNode EventBus 集成 — 在工具执行前后发送事件"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from langchain_core.messages import ToolMessage

from tools.tool_results import (
    MAX_TOOL_RESULTS_PER_MESSAGE_CHARS,
    ToolResultCandidate,
    apply_aggregate_budget,
    apply_transcript_metadata,
    candidate_from_tool_message,
    extract_tool_use_result,
    get_tool_result_threshold,
    merge_budget_metadata,
    maybe_persist_tool_result,
)
from core.event_bus import AgentEvent, EventBus, EventType

logger = logging.getLogger(__name__)


def create_event_bus_wrapper(event_bus: EventBus, session=None) -> Callable:
    """创建 ToolNode wrap_tool_call，在工具执行前后发送 EventBus 事件

    利用 response_format="content_and_artifact" 机制：
    ToolMessage.artifact 中包含 display 和 metadata（如 diff），
    无需通过实例属性传递，线程安全。
    """

    batch_lock = threading.Lock()
    batch_candidates: dict[str, ToolResultCandidate] = {}
    active_count = 0

    def wrapper(request, execute):
        nonlocal active_count
        tc = request.tool_call
        tool_name = tc["name"]
        call_id = tc["id"]
        input_args = tc.get("args") or {}

        # ── executing ──
        start_time = time.time()
        logger.info(f"[{tool_name}] 开始执行")

        event_bus.emit(AgentEvent(
            type=EventType.TOOL_STATE_UPDATE,
            data={"call_id": call_id, "tool_name": tool_name, "status": "executing"},
        ))

        with batch_lock:
            active_count += 1

        result = execute(request)

        elapsed = time.time() - start_time
        logger.info(f"[{tool_name}] 完成，耗时 {elapsed:.3f}s")

        # ── 从 ToolMessage 提取结果信息 ──
        status = "success"
        display = ""
        error_msg = ""
        transcript_payload: dict | None = None
        persisted_event: dict | None = None
        pending_batch_events: list[tuple[str, dict]] = []

        if isinstance(result, ToolMessage):
            if result.status == "error":
                status = "error"
                error_msg = str(result.content)[:200] if result.content else ""
            elif result.artifact and isinstance(result.artifact, dict):
                display = result.artifact.get("display", "")
                diff = result.artifact.get("diff")
                if diff is not None:
                    event_bus.emit(AgentEvent(
                        type=EventType.TOOL_LIVE_OUTPUT,
                        data={
                            "call_id": call_id,
                            "tool_name": tool_name,
                            "kind": "diff",
                            "diff": diff,
                        },
                    ))

            if session is not None:
                content = str(result.content or "")
                threshold = get_tool_result_threshold(tool_name)
                existing_tool_use_result = extract_tool_use_result(result)
                decision = maybe_persist_tool_result(
                    tool_name=tool_name,
                    tool_call_id=call_id,
                    content=content,
                    display=display,
                    artifact_dir=session.get_artifact_dir(),
                    artifact_path=session.get_tool_result_artifact_path(call_id),
                    threshold=threshold,
                    reason="per-tool-limit",
                )
                result.content = decision.content
                merged_tool_use_result = merge_budget_metadata(
                    existing_tool_use_result,
                    tool_name=tool_name,
                    input_args=input_args,
                    raw_content=content,
                    artifact_path=decision.artifact_meta["path"] if decision.artifact_meta else None,
                    original_chars=decision.original_chars,
                    preview_chars=decision.tool_use_result["preview_chars"],
                    truncated=decision.tool_use_result["truncated"],
                    persistence_reason=decision.reason,
                )
                apply_transcript_metadata(
                    result,
                    display=display,
                    tool_use_result=merged_tool_use_result,
                    artifact_meta=decision.artifact_meta,
                )
                if decision.persisted:
                    persisted_event = {
                        "call_id": call_id,
                        "tool_name": tool_name,
                        "path": decision.artifact_meta["path"],
                        "original_chars": decision.original_chars,
                        "preview_chars": decision.tool_use_result["preview_chars"],
                        "reason": decision.reason,
                    }

                candidate = candidate_from_tool_message(
                    tool_name=tool_name,
                    tool_call_id=call_id,
                    tool_message=result,
                )
                with batch_lock:
                    batch_candidates[call_id] = candidate
                    active_count -= 1
                    if active_count == 0 and batch_candidates:
                        aggregate_decisions = apply_aggregate_budget(
                            list(batch_candidates.values()),
                            artifact_dir=session.get_artifact_dir(),
                            artifact_path_for_call=session.get_tool_result_artifact_path,
                            aggregate_limit=MAX_TOOL_RESULTS_PER_MESSAGE_CHARS,
                        )
                        for aggregate_decision in aggregate_decisions:
                            aggregate_candidate = batch_candidates[aggregate_decision.tool_call_id]
                            aggregate_candidate.tool_message.content = aggregate_decision.content
                            existing_tool_use_result = extract_tool_use_result(
                                aggregate_candidate.tool_message
                            )
                            merged_tool_use_result = merge_budget_metadata(
                                existing_tool_use_result,
                                tool_name=aggregate_decision.tool_name,
                                input_args=(existing_tool_use_result or {}).get("input"),
                                raw_content=aggregate_candidate.content,
                                artifact_path=aggregate_decision.artifact_meta["path"] if aggregate_decision.artifact_meta else None,
                                original_chars=aggregate_decision.original_chars,
                                preview_chars=aggregate_decision.tool_use_result["preview_chars"],
                                truncated=aggregate_decision.tool_use_result["truncated"],
                                persistence_reason=aggregate_decision.reason,
                            )
                            apply_transcript_metadata(
                                aggregate_candidate.tool_message,
                                display=aggregate_candidate.display,
                                tool_use_result=merged_tool_use_result,
                                artifact_meta=aggregate_decision.artifact_meta,
                            )
                            pending_batch_events.append((
                                "persisted",
                                {
                                    "call_id": aggregate_decision.tool_call_id,
                                    "tool_name": aggregate_decision.tool_name,
                                    "path": aggregate_decision.artifact_meta["path"],
                                    "original_chars": aggregate_decision.original_chars,
                                    "preview_chars": aggregate_decision.tool_use_result["preview_chars"],
                                    "reason": aggregate_decision.reason,
                                },
                            ))
                        for candidate in batch_candidates.values():
                            artifact = dict(candidate.tool_message.artifact or {})
                            pending_batch_events.append((
                                "transcript",
                                {
                                    "role": "tool",
                                    "content": str(candidate.tool_message.content or ""),
                                    "tool_call_id": candidate.tool_call_id,
                                    "name": candidate.tool_name,
                                    "toolUseResult": artifact.get("toolUseResult"),
                                    "artifact": artifact.get("artifact_meta"),
                                },
                            ))
                        batch_candidates.clear()
            else:
                with batch_lock:
                    active_count -= 1
        else:
            with batch_lock:
                active_count -= 1

        # ── complete ──
        event_bus.emit(AgentEvent(
            type=EventType.TOOL_CALL_COMPLETE,
            data={
                "call_id": call_id,
                "tool_name": tool_name,
                "status": status,
                "display": display,
                "error_msg": error_msg,
            },
        ))

        if persisted_event is not None:
            event_bus.emit(AgentEvent(
                type=EventType.TOOL_RESULT_PERSISTED,
                data=persisted_event,
            ))
        for event_kind, payload in pending_batch_events:
            if event_kind == "persisted":
                event_bus.emit(AgentEvent(
                    type=EventType.TOOL_RESULT_PERSISTED,
                    data=payload,
                ))
            elif event_kind == "transcript":
                event_bus.emit(AgentEvent(
                    type=EventType.TRANSCRIPT_MESSAGE,
                    data=payload,
                ))

        return result

    return wrapper

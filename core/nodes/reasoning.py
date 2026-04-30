"""
推理节点 — ReAct 循环中的 LLM 推理步骤

对应 gemini-cli 的 Turn.run():
  1. 组装系统提示词 (system prompt + 工具描述 + MT-3000 上下文)
  2. 调用 LLM (流式), 通过 EventBus 发送 CONTENT/THOUGHT 事件
  3. 解析 LLM 返回的 tool_calls → 写入 state.pending_tool_calls
  4. turn_count += 1
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage

from config.settings import CONTEXT as CONTEXT_CONFIG
from core.context.auto_compact import AutoCompactDecision, AutoCompactPolicy, QuerySource
from core.context.microcompact import maybe_time_based_microcompact
from core.context.budget import budget_snapshot, estimate_message_tokens
from core.context.session_memory import (
    SessionMemoryStatus,
    is_session_memory_summary_message,
    should_extract_memory,
)
from core.context.session_memory import SessionMemoryManager
from core.context.session_memory_worker import SessionMemoryExtractWorker
from core.event_bus import AgentEvent, EventBus, EventType
from core.context.message_invariants import (
    is_compact_boundary_message,
    is_compact_summary_message,
)
from core.state import AgentState, ToolCallInfo
from core.utils.tokens import estimate_tokens
from prompts.system_prompt import build_system_prompt

logger = logging.getLogger(__name__)

# 类型引用，避免硬依赖
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.context.compressor import CompressResult
    from core.context import ContextManager
    from core.session import SessionStats
    from tools.base import BaseTool as ProjectBaseTool

from core.context.compressor import ContextCompressor


def create_reasoning_node(
    llm: BaseChatModel,
    event_bus: EventBus,
    tools: list[ProjectBaseTool] | None = None,
    context_manager: ContextManager | None = None,
    session_stats: SessionStats | None = None,
    compressor: ContextCompressor | None = None,
    auto_compact_policy: AutoCompactPolicy | None = None,
    session_memory_manager: SessionMemoryManager | None = None,
    session_memory_worker: SessionMemoryExtractWorker | None = None,
) -> Callable[[AgentState], dict]:
    """
    创建 reasoning 节点函数

    Args:
        llm: LangChain ChatModel (如 ChatOpenAI)
        event_bus: 事件总线, 用于向 CLI 层推送流式事件
        tools: 工具实例列表 (langchain BaseTool)
        context_manager: Context & Memory 管理器 (可选)
        session_stats: 会话统计 (可选，用于记录 token usage)
        compressor: 上下文压缩器 (可选，当 token 超阈值时自动压缩)

    Returns:
        LangGraph 节点函数 ``(AgentState) -> dict``
    """
    bound_llm = llm.bind_tools(tools) if tools else llm
    auto_compact_policy = auto_compact_policy or AutoCompactPolicy()

    def reasoning_node(state: AgentState) -> dict:
        turn = state.get("turn_count", 0)
        query_source = state.get("query_source", "interactive")

        # 1) system prompt — 每轮动态生成, 含全局上下文 (Tier 1)
        global_context = ""
        if context_manager is not None:
            global_context = context_manager.build_system_context()

        system_msg = SystemMessage(
            content=build_system_prompt(state, tools, global_context=global_context)
        )

        # 2) 构建 messages: system + session_context (Tier 2, 仅首轮) + 历史
        messages = [system_msg]

        if turn == 0 and context_manager is not None:
            session_ctx = context_manager.build_session_context()
            if session_ctx:
                from langchain_core.messages import HumanMessage
                messages.append(HumanMessage(content=session_ctx))

        # 3) 准备历史消息并估算 token
        prepared_history = _prepare_history_for_model(
            list(state.get("messages", [])),
            list(state.get("assistant_reasoning_fallbacks", [])),
        )
        prepared_history = _apply_time_based_microcompact_if_needed(
            prepared_history,
            query_source=query_source,
        )
        messages.extend(prepared_history)

        if session_stats is not None:
            total = _update_context_budget_stats(messages, session_stats)
            logger.info("Estimated input tokens: %d (threshold: %d)", total, session_stats.last_auto_compact_threshold)

        # 4) 压缩检查
        compress_result = None
        if compressor is not None and session_stats is not None:
            decision = _build_auto_compact_decision(
                auto_compact_policy=auto_compact_policy,
                session_stats=session_stats,
                query_source=query_source,
            )
            _emit_auto_compact_checked(event_bus, decision, turn, auto_compact_policy.max_consecutive_failures)

            compress_result = _maybe_auto_compact(
                compressor, event_bus, session_stats, state, decision, turn, query_source, session_memory_manager
            )

            if compress_result is not None:
                # 重建 messages：system + session_context + 压缩后的历史
                messages = [system_msg]
                if turn == 0 and context_manager is not None:
                    session_ctx = context_manager.build_session_context()
                    if session_ctx:
                        messages.append(HumanMessage(content=session_ctx))

                prepared_compressed = _prepare_history_for_model(
                    compress_result.compressed_messages,
                    list(state.get("assistant_reasoning_fallbacks", [])),
                )
                messages.extend(prepared_compressed)

                if session_stats is not None:
                    total = _update_context_budget_stats(messages, session_stats)
                    logger.info("Tokens after compression: %d", total)

        # 5) 流式调用 LLM
        collected = _stream_with_events(
            bound_llm, messages, event_bus, turn,
            compressor=compressor,
            session_stats=session_stats,
            state=state,
            auto_compact_policy=auto_compact_policy,
        )

        # 6) 收集 token usage
        if session_stats is not None:
            _record_token_usage(collected, session_stats)
            _update_context_budget_stats_from_count(session_stats.last_input_tokens, session_stats)

        # 7) 构造 AIMessage
        collected_additional = dict(collected.additional_kwargs or {})
        reasoning_content = _extract_reasoning_content(collected)
        ai_message = AIMessage(
            content=collected.content or "",
            tool_calls=collected.tool_calls or [],
            additional_kwargs={"reasoning_content": reasoning_content} if "reasoning_content" in collected_additional else {},
            response_metadata={"timestamp_ms": int(time.time() * 1000)},
        )
        event_bus.emit(AgentEvent(
            type=EventType.TRANSCRIPT_MESSAGE,
            data={
                "role": "assistant",
                "content": ai_message.content,
                "tool_calls": ai_message.tool_calls or [],
                "reasoning_content": reasoning_content,
            },
            turn=turn,
        ))

        # 8) 提取 tool_calls
        pending = _extract_tool_calls(collected, event_bus, turn)

        # 9) TURN_START 事件
        event_bus.emit(AgentEvent(
            type=EventType.TURN_START,
            data={"turn": turn + 1, "has_tool_calls": bool(pending), "tool_count": len(pending)},
            turn=turn + 1,
        ))

        logger.info("reasoning turn=%d content_len=%d tool_calls=%d", turn + 1, len(ai_message.content), len(pending))

        result = {
            "messages": [ai_message],
            "turn_count": turn + 1,
            "pending_tool_calls": pending,
        }

        # 保存 reasoning_content fallback
        if pending and "reasoning_content" in collected_additional:
            existing_fallbacks = list(state.get("assistant_reasoning_fallbacks", []))
            tool_call_ids = [tc["id"] for tc in ai_message.tool_calls or [] if tc.get("id")]
            if tool_call_ids:
                existing_fallbacks = [e for e in existing_fallbacks if e.get("tool_call_ids") != tool_call_ids]
                existing_fallbacks.append({"tool_call_ids": tool_call_ids, "reasoning_content": reasoning_content})
                result["assistant_reasoning_fallbacks"] = existing_fallbacks

        session_memory_updates = _maybe_schedule_session_memory_extract(
            session_memory_manager=session_memory_manager,
            session_memory_worker=session_memory_worker,
            event_bus=event_bus,
            state=state,
            ai_message=ai_message,
            pending_tool_calls=pending,
            turn=turn + 1,
        )
        result.update(session_memory_updates)

        # 合并压缩操作
        if compress_result is not None:
            result["messages"] = _build_compression_message_ops(compress_result) + result["messages"]

        return result

    return reasoning_node



def should_use_tools(state: AgentState) -> str:
    """
    reasoning 之后的条件路由

    Usage::

        graph.add_conditional_edges("reasoning", should_use_tools, {
            "use_tools": "tool_routing",
            "final_answer": END,
        })
    """
    if state.get("pending_tool_calls"):
        return "use_tools"
    return "final_answer"



def _stream_with_events(
    llm: BaseChatModel,
    messages: list,
    event_bus: EventBus,
    turn: int,
    compressor: ContextCompressor | None = None,
    session_stats: SessionStats | None = None,
    state: AgentState | None = None,
    auto_compact_policy: AutoCompactPolicy | None = None,
) -> AIMessageChunk:
    """流式调用 LLM, 每个 chunk 通过 EventBus 推送事件。

    如果遇到 400 context length 错误，触发强制压缩并重试。
    """

    collected: AIMessageChunk | None = None
    reasoning_parts: list[str] = []

    try:
        for chunk in llm.stream(messages):
            collected = chunk if collected is None else collected + chunk

            # 文本内容 → CONTENT
            if chunk.content:
                event_bus.emit(AgentEvent(
                    type=EventType.CONTENT,
                    data={"text": chunk.content},
                    turn=turn,
                ))

            # 思考过程 → THOUGHT (DeepSeek-R1 等模型的 reasoning_content)
            reasoning = (chunk.additional_kwargs or {}).get("reasoning_content")
            if "reasoning_content" in (chunk.additional_kwargs or {}):
                reasoning_parts.append(reasoning)
                event_bus.emit(AgentEvent(
                    type=EventType.THOUGHT,
                    data={"text": reasoning},
                    turn=turn,
                ))

    except Exception as e:
        # 捕获 400 context length 错误
        from openai import BadRequestError
        if isinstance(e, BadRequestError) and ("context_length_exceeded" in str(e) or "maximum context length" in str(e)):
            logger.warning("Context length exceeded (400), attempting forced compression")

            # 尝试从错误信息解析实际 token 数
            error_msg = str(e)
            actual_tokens = None
            if session_stats is not None:
                import re
                # 匹配 "you requested X tokens"
                match = re.search(r"you requested (\d+) tokens", error_msg)
                if match:
                    actual_tokens = int(match.group(1))
                    session_stats.last_input_tokens = actual_tokens
                    logger.info("Parsed actual token count from error: %d", actual_tokens)

            # 强制压缩并重试
            if compressor is not None and state is not None:
                history = list(state.get("messages", []))
                if len(history) >= 4:
                    # 使用更激进的压缩策略（只保留最后 10% 的消息）
                    aggressive_result = compressor.compress(history)
                    if aggressive_result is not None:
                        # 如果压缩后仍然太大，进一步压缩
                        if actual_tokens and actual_tokens > 100000:
                            # 只保留最后 2 条消息
                            keep_count = min(2, len(history))
                            from core.context.compressor import CompressResult
                            boundary_msg = compressor.build_compact_boundary_message(
                                pre_tokens=actual_tokens or 0,
                                post_tokens=0,
                                reason="reactive_retry",
                            )
                            aggressive_result = CompressResult(
                                remove_message_ids=[msg.id for msg in history[:-keep_count] if msg.id],
                                boundary_message=boundary_msg,
                                summary_message=compressor.build_summary_message("Previous conversation context has been compressed due to length limits."),
                                summary_text="Previous conversation context has been compressed due to length limits.",
                                compressed_messages=[
                                    boundary_msg,
                                    compressor.build_summary_message("Previous conversation context has been compressed due to length limits."),
                                    *history[-keep_count:],
                                ],
                                removed_count=len(history) - keep_count,
                                kept_count=keep_count,
                                split_index=len(history) - keep_count,
                                pre_tokens=actual_tokens or 0,
                                post_tokens=0,
                                reason="reactive_retry",
                            )

                        logger.info("Forced compression: removed=%d kept=%d", aggressive_result.removed_count, aggressive_result.kept_count)

                        # 发送压缩事件
                        event_bus.emit(AgentEvent(
                            type=EventType.CONTEXT_COMPRESSED,
                            data={
                                "summary": aggressive_result.summary_text,
                                "removed_count": aggressive_result.removed_count,
                                "kept_count": aggressive_result.kept_count,
                                "trigger_reason": "reactive_retry",
                                "pre_tokens": aggressive_result.pre_tokens,
                                "post_tokens": aggressive_result.post_tokens,
                            },
                        ))
                        event_bus.emit(AgentEvent(
                            type=EventType.COMPACT_BOUNDARY,
                            data={
                                "reason": aggressive_result.reason,
                                "pre_tokens": aggressive_result.pre_tokens,
                                "post_tokens": aggressive_result.post_tokens,
                            },
                            turn=turn,
                        ))

                        # 重建 messages（保留 system prompt，替换历史为压缩后的）
                        system_msg = messages[0] if messages and isinstance(messages[0], SystemMessage) else None
                        new_messages = []
                        if system_msg:
                            new_messages.append(system_msg)
                        new_messages.extend(aggressive_result.compressed_messages)

                        # 重试 LLM 调用（不传递 compressor 避免无限递归）
                        logger.info("Retrying LLM call with compressed context")
                        if session_stats is not None:
                            session_stats.compression_failure_count = 0
                        return _stream_with_events(llm, new_messages, event_bus, turn)

        logger.error("LLM streaming error: %s", e)
        event_bus.emit(AgentEvent(
            type=EventType.ERROR,
            data={"error": str(e), "source": "reasoning_node"},
            turn=turn,
        ))
        raise

    if collected is None:
        err = RuntimeError("LLM returned no response")
        event_bus.emit(AgentEvent(
            type=EventType.ERROR,
            data={"error": str(err), "source": "reasoning_node"},
            turn=turn,
        ))
        raise err

    if reasoning_parts or "reasoning_content" in (collected.additional_kwargs or {}):
        merged_reasoning = "".join(reasoning_parts)
        additional_kwargs = dict(collected.additional_kwargs or {})
        additional_kwargs["reasoning_content"] = merged_reasoning
        collected = AIMessageChunk(
            content=collected.content,
            additional_kwargs=additional_kwargs,
            tool_call_chunks=getattr(collected, "tool_call_chunks", None),
            tool_calls=getattr(collected, "tool_calls", None),
            response_metadata=getattr(collected, "response_metadata", None),
            usage_metadata=getattr(collected, "usage_metadata", None),
        )

    return collected


def _prepare_history_for_model(
    messages: list[BaseMessage],
    reasoning_fallbacks: list[dict[str, Any]] | None = None,
) -> list[BaseMessage]:
    """Keep reasoning_content only for assistant messages between two user messages that involve tool calls."""
    if not messages:
        return []

    fallback_by_tool_ids: dict[tuple[str, ...], str] = {}
    for entry in reasoning_fallbacks or []:
        tool_call_ids = tuple(str(item) for item in entry.get("tool_call_ids") or [])
        reasoning_content = entry.get("reasoning_content")
        if tool_call_ids and isinstance(reasoning_content, str) and reasoning_content:
            fallback_by_tool_ids[tool_call_ids] = reasoning_content

    # 找到所有 HumanMessage 的索引，划分 segment
    human_indices = [idx for idx, msg in enumerate(messages) if isinstance(msg, HumanMessage)]
    segments: list[tuple[int, int]] = []
    if not human_indices:
        segments.append((0, len(messages)))
    else:
        if human_indices[0] > 0:
            segments.append((0, human_indices[0]))
        for pos, start_idx in enumerate(human_indices):
            end_idx = human_indices[pos + 1] if pos + 1 < len(human_indices) else len(messages)
            segments.append((start_idx, end_idx))

    # 判断每个 segment 是否有工具调用
    preserve_reasoning_segments: set[int] = set()
    for seg_idx, (start_idx, end_idx) in enumerate(segments):
        segment = messages[start_idx:end_idx]
        has_tool_calls = any(
            (isinstance(msg, AIMessage) and bool(msg.tool_calls))
            or isinstance(msg, ToolMessage)
            for msg in segment
        )
        has_compaction_marker = any(
            is_compact_boundary_message(msg) or is_compact_summary_message(msg) or is_session_memory_summary_message(msg)
            for msg in segment
        )
        if has_tool_calls or has_compaction_marker:
            preserve_reasoning_segments.add(seg_idx)

    prepared: list[BaseMessage] = []
    for idx, message in enumerate(messages):
        if isinstance(message, AIMessage):
            # 找到这个消息属于哪个 segment
            seg_idx = 0
            for i, (start, end) in enumerate(segments):
                if start <= idx < end:
                    seg_idx = i
                    break

            should_preserve = seg_idx in preserve_reasoning_segments
            additional_kwargs = dict(message.additional_kwargs or {})
            has_reasoning_content = "reasoning_content" in additional_kwargs
            reasoning_content = additional_kwargs.get("reasoning_content")

            # 从 fallback 恢复
            if not has_reasoning_content and message.tool_calls:
                tool_call_ids = tuple(str(tc.get("id")) for tc in message.tool_calls if tc.get("id"))
                fallback_reasoning = fallback_by_tool_ids.get(tool_call_ids)
                if fallback_reasoning:
                    additional_kwargs["reasoning_content"] = fallback_reasoning
                    message = AIMessage(
                        content=message.content,
                        tool_calls=message.tool_calls or [],
                        additional_kwargs=additional_kwargs,
                        id=message.id,
                        response_metadata=getattr(message, "response_metadata", None) or {},
                    )
                    reasoning_content = fallback_reasoning
                    has_reasoning_content = True

            # 移除不需要保留的 reasoning_content
            if has_reasoning_content and not should_preserve:
                additional_kwargs.pop("reasoning_content", None)
                message = AIMessage(
                    content=message.content,
                    tool_calls=message.tool_calls or [],
                    additional_kwargs=additional_kwargs,
                    id=message.id,
                    response_metadata=getattr(message, "response_metadata", None) or {},
                )

        prepared.append(message)
    return prepared


def _extract_reasoning_content(response: AIMessageChunk) -> str | None:
    if "reasoning_content" not in (response.additional_kwargs or {}):
        return None
    reasoning_content = (response.additional_kwargs or {}).get("reasoning_content")
    if isinstance(reasoning_content, str):
        return reasoning_content
    return None



def _extract_tool_calls(
    response: AIMessageChunk,
    event_bus: EventBus,
    turn: int,
) -> list[ToolCallInfo]:
    """从 LLM 响应中提取 tool_calls → ToolCallInfo, 并发送 TOOL_CALL_REQUEST"""

    pending: list[ToolCallInfo] = []

    for tc in response.tool_calls or []:
        info = ToolCallInfo(
            call_id=tc["id"],
            tool_name=tc["name"],
            arguments=tc["args"],
            status="pending",
            result=None,
            error_msg=None,
        )
        pending.append(info)

        event_bus.emit(AgentEvent(
            type=EventType.TOOL_CALL_REQUEST,
            data={
                "call_id": tc["id"],
                "tool_name": tc["name"],
                "arguments": tc["args"],
            },
            turn=turn,
        ))

    return pending


def _record_token_usage(
    response: AIMessageChunk,
    session_stats: SessionStats,
) -> None:
    """从 LLM 响应中提取 token usage 并记录到 SessionStats。"""
    usage = getattr(response, "usage_metadata", None)
    if usage and isinstance(usage, dict):
        session_stats.record_llm_usage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
        return

    # 回退: response_metadata.usage (OpenAI 兼容)
    resp_meta = getattr(response, "response_metadata", None) or {}
    usage = resp_meta.get("usage") or resp_meta.get("token_usage") or {}
    if usage:
        session_stats.record_llm_usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
        return

    estimated_input_tokens = max(session_stats.last_input_tokens, 0)
    estimated_output_tokens = estimate_tokens(str(response.content or ""))
    if getattr(response, "tool_calls", None):
        estimated_output_tokens += estimate_tokens(str(response.tool_calls))
    if estimated_input_tokens > 0 or estimated_output_tokens > 0:
        logger.warning(
            "LLM usage metadata missing; falling back to estimates input=%d output=%d",
            estimated_input_tokens,
            estimated_output_tokens,
        )
        session_stats.record_llm_usage(
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens,
        )


def _update_context_budget_stats(
    messages: list,
    session_stats: SessionStats,
) -> int:
    """Recompute current context budget stats from the message list."""
    snapshot = budget_snapshot(
        messages,
        token_limit=CONTEXT_CONFIG["token_limit"],
        reserved_summary_tokens=CONTEXT_CONFIG["summary_reserved_tokens"],
        buffer_tokens=CONTEXT_CONFIG["autocompact_buffer_tokens"],
    )
    _apply_budget_snapshot(snapshot, session_stats)
    return snapshot["raw_input_tokens"]


def _update_context_budget_stats_from_count(
    raw_input_tokens: int,
    session_stats: SessionStats,
) -> None:
    """Refresh derived budget stats using an already known token count."""
    compact_threshold = budget_snapshot(
        [],
        token_limit=CONTEXT_CONFIG["token_limit"],
        reserved_summary_tokens=CONTEXT_CONFIG["summary_reserved_tokens"],
        buffer_tokens=CONTEXT_CONFIG["autocompact_buffer_tokens"],
    )
    session_stats.last_input_tokens = raw_input_tokens
    session_stats.last_effective_context_limit = compact_threshold["effective_context_limit"]
    session_stats.last_auto_compact_threshold = compact_threshold["auto_compact_threshold"]
    session_stats.last_tokens_until_compact = max(
        compact_threshold["auto_compact_threshold"] - raw_input_tokens,
        0,
    )


def _apply_budget_snapshot(
    snapshot: dict[str, int],
    session_stats: SessionStats,
) -> None:
    """Apply a computed budget snapshot to session stats."""
    session_stats.last_input_tokens = snapshot["raw_input_tokens"]
    session_stats.last_effective_context_limit = snapshot["effective_context_limit"]
    session_stats.last_auto_compact_threshold = snapshot["auto_compact_threshold"]
    session_stats.last_tokens_until_compact = snapshot["tokens_until_compact"]


def _build_auto_compact_decision(
    *,
    auto_compact_policy: AutoCompactPolicy,
    session_stats: SessionStats,
    query_source: QuerySource | str,
) -> AutoCompactDecision:
    return auto_compact_policy.evaluate(
        raw_input_tokens=session_stats.last_input_tokens,
        token_limit=CONTEXT_CONFIG["token_limit"],
        reserved_summary_tokens=CONTEXT_CONFIG["summary_reserved_tokens"],
        buffer_tokens=CONTEXT_CONFIG["autocompact_buffer_tokens"],
        query_source=query_source if isinstance(query_source, str) else "interactive",
        consecutive_failures=session_stats.compression_failure_count,
    )


def _emit_auto_compact_checked(
    event_bus: EventBus,
    decision: AutoCompactDecision,
    turn: int,
    max_failures: int,
) -> None:
    event_bus.emit(AgentEvent(
        type=EventType.AUTO_COMPACT_CHECKED,
        data={
            "raw_input_tokens": decision.raw_input_tokens,
            "effective_context_limit": decision.effective_context_limit,
            "auto_compact_threshold": decision.auto_compact_threshold,
            "tokens_until_compact": decision.tokens_until_compact,
            "should_compact": decision.should_compact,
            "skip_reason": decision.skip_reason,
            "blocked_by_circuit_breaker": decision.blocked_by_circuit_breaker,
            "query_source": decision.query_source,
        },
        turn=turn,
    ))

    if decision.blocked_by_circuit_breaker:
        event_bus.emit(AgentEvent(
            type=EventType.AUTO_COMPACT_DISABLED,
            data={
                "consecutive_failures": decision.consecutive_failures,
                "max_failures": max_failures,
                "query_source": decision.query_source,
            },
            turn=turn,
        ))


def _maybe_auto_compact(
    compressor: ContextCompressor,
    event_bus: EventBus,
    session_stats: SessionStats,
    state: AgentState,
    decision: AutoCompactDecision,
    turn: int,
    query_source: QuerySource | str,
    session_memory_manager: SessionMemoryManager | None = None,
) -> CompressResult | None:
    """检查是否需要压缩，若需要则执行并返回 state 更新。"""
    if not decision.should_compact:
        return None

    history = list(state.get("messages", []))
    if not history:
        return None

    logger.info(
        "Context compression triggered: last_input_tokens=%d",
        session_stats.last_input_tokens,
    )
    pre_tokens = session_stats.last_input_tokens

    if session_memory_manager is not None:
        session_memory_status = _session_memory_status_from_sources(session_memory_manager, state)
        session_memory_result = session_memory_manager.try_session_memory_compact(
            messages=history,
            status=session_memory_status,
            threshold_tokens=session_stats.last_auto_compact_threshold,
            min_keep_tokens=CONTEXT_CONFIG["compression_preserve_min_tokens"],
            max_keep_tokens=CONTEXT_CONFIG["compression_preserve_max_tokens"],
        )
        if session_memory_result is not None:
            logger.info(
                "Session memory compact applied: turn=%d start_index=%d post_tokens=%d threshold=%d",
                turn,
                session_memory_result.start_index,
                session_memory_result.post_tokens,
                session_stats.last_auto_compact_threshold,
            )
            session_stats.compression_failure_count = 0
            event_bus.emit(AgentEvent(
                type=EventType.CONTEXT_COMPRESSED,
                data={
                    "summary": str(session_memory_result.summary_message.content),
                    "removed_count": session_memory_result.start_index,
                    "kept_count": len(history) - session_memory_result.start_index,
                    "trigger_reason": "session_memory",
                    "pre_tokens": pre_tokens,
                    "post_tokens": session_memory_result.post_tokens,
                },
                turn=turn,
            ))
            event_bus.emit(AgentEvent(
                type=EventType.COMPACT_BOUNDARY,
                data={
                    "reason": "session_memory",
                    "pre_tokens": pre_tokens,
                    "post_tokens": session_memory_result.post_tokens,
                },
                turn=turn,
            ))
            return _session_memory_result_to_compress_result(
                session_memory_result,
                history,
            )
        logger.info(
            "Session memory compact unavailable, falling back to full compact: turn=%d threshold=%d",
            turn,
            session_stats.last_auto_compact_threshold,
        )

    try:
        result = compressor.compress(history, reason=str(decision.trigger_reason or "auto"))
    except Exception as exc:
        session_stats.compression_failure_count += 1
        event_bus.emit(AgentEvent(
            type=EventType.AUTO_COMPACT_FAILED,
            data={
                "error": str(exc),
                "consecutive_failures": session_stats.compression_failure_count,
                "query_source": query_source,
                "trigger_reason": decision.trigger_reason,
            },
            turn=turn,
        ))
        logger.warning("Auto compact failed: %s", exc)
        return None

    if result is None:
        session_stats.compression_failure_count += 1
        event_bus.emit(AgentEvent(
            type=EventType.AUTO_COMPACT_FAILED,
            data={
                "error": "compressor returned no result",
                "consecutive_failures": session_stats.compression_failure_count,
                "query_source": query_source,
                "trigger_reason": decision.trigger_reason,
            },
            turn=turn,
        ))
        return None

    session_stats.compression_failure_count = 0
    post_tokens = estimate_tokens(str(result.summary_message.content))
    event_bus.emit(AgentEvent(
        type=EventType.CONTEXT_COMPRESSED,
        data={
            "summary": result.summary_text,
            "removed_count": result.removed_count,
            "kept_count": result.kept_count,
            "trigger_reason": decision.trigger_reason,
            "pre_tokens": result.pre_tokens,
            "post_tokens": result.post_tokens,
        },
        turn=turn,
    ))
    event_bus.emit(AgentEvent(
        type=EventType.COMPACT_BOUNDARY,
        data={
            "reason": result.reason,
            "pre_tokens": result.pre_tokens,
            "post_tokens": result.post_tokens,
        },
        turn=turn,
    ))
    event_bus.emit(AgentEvent(
        type=EventType.TRANSCRIPT_MESSAGE,
        data={
            "role": "system",
            "content": str(result.summary_message.content),
            "name": "compact_summary",
        },
        turn=turn,
    ))

    logger.info(
        "Compression complete: removed=%d kept=%d",
        result.removed_count, result.kept_count,
    )

    return result


def _session_memory_result_to_compress_result(
    session_memory_result,
    history: list[BaseMessage],
):
    from core.context.compressor import CompressResult

    remove_ids = [msg.id for msg in history[:session_memory_result.start_index] if msg.id]
    return CompressResult(
        remove_message_ids=remove_ids,
        boundary_message=session_memory_result.boundary_message,
        summary_message=session_memory_result.summary_message,
        summary_text=str(session_memory_result.summary_message.content),
        compressed_messages=session_memory_result.compacted_messages,
        removed_count=session_memory_result.start_index,
        kept_count=len(history) - session_memory_result.start_index,
        split_index=session_memory_result.start_index,
        pre_tokens=estimate_message_tokens(history[:session_memory_result.start_index]),
        post_tokens=session_memory_result.post_tokens,
        reason="session_memory",
    )


def _session_memory_status_from_sources(
    session_memory_manager: SessionMemoryManager,
    state: AgentState,
) -> SessionMemoryStatus:
    manager_status = session_memory_manager.get_status()
    state_status = SessionMemoryStatus(
        summary_path=state.get("session_memory_summary_path"),
        last_summarized_message_id=state.get("session_memory_last_summarized_message_id"),
        tokens_at_last_extraction=state.get("session_memory_tokens_at_last_extraction", 0),
        tool_calls_since_last_update=state.get("session_memory_tool_calls_since_update", 0),
        last_update_turn=state.get("session_memory_last_update_turn", 0),
    )
    return SessionMemoryStatus(
        summary_path=manager_status.summary_path or state_status.summary_path,
        last_summarized_message_id=manager_status.last_summarized_message_id or state_status.last_summarized_message_id,
        tokens_at_last_extraction=manager_status.tokens_at_last_extraction or state_status.tokens_at_last_extraction,
        tool_calls_since_last_update=max(manager_status.tool_calls_since_last_update, state_status.tool_calls_since_last_update),
        last_update_turn=max(manager_status.last_update_turn, state_status.last_update_turn),
    )


def _session_memory_state_payload(status: SessionMemoryStatus) -> dict[str, Any]:
    return {
        "session_memory_summary_path": status.summary_path,
        "session_memory_last_summarized_message_id": status.last_summarized_message_id,
        "session_memory_tokens_at_last_extraction": status.tokens_at_last_extraction,
        "session_memory_tool_calls_since_update": status.tool_calls_since_last_update,
        "session_memory_last_update_turn": status.last_update_turn,
    }


def _maybe_schedule_session_memory_extract(
    *,
    session_memory_manager: SessionMemoryManager | None,
    session_memory_worker: SessionMemoryExtractWorker | None,
    event_bus: EventBus,
    state: AgentState,
    ai_message: AIMessage,
    pending_tool_calls: list[ToolCallInfo],
    turn: int,
) -> dict[str, Any]:
    if session_memory_manager is None:
        return {
            "session_memory_tool_calls_since_update": state.get("session_memory_tool_calls_since_update", 0) + len(pending_tool_calls),
        }

    current_status = _session_memory_status_from_sources(session_memory_manager, state)
    history = list(state.get("messages", [])) + [ai_message]
    current_tokens = estimate_message_tokens(history)
    tool_calls_since_update = current_status.tool_calls_since_last_update + len(pending_tool_calls)
    last_turn_has_tool_calls = bool(pending_tool_calls)

    if session_memory_worker is not None:
        logger.info(
            "Session memory extract candidate queued: turn=%d current_tokens=%d tool_calls_since_last_update=%d last_turn_has_tool_calls=%s",
            turn,
            current_tokens,
            tool_calls_since_update,
            last_turn_has_tool_calls,
        )
        session_memory_worker.schedule_extract(
            messages=history,
            current_tokens=current_tokens,
            tool_calls_since_last_update=tool_calls_since_update,
            last_turn_has_tool_calls=last_turn_has_tool_calls,
            turn=turn,
        )
        current_status.tool_calls_since_last_update = tool_calls_since_update
        session_memory_manager.set_status(current_status)
        return _session_memory_state_payload(current_status)

    if not should_extract_memory(
        current_tokens=current_tokens,
        tokens_at_last_extraction=current_status.tokens_at_last_extraction,
        tool_calls_since_last_update=tool_calls_since_update,
        last_turn_has_tool_calls=last_turn_has_tool_calls,
    ):
        logger.info(
            "Session memory extract skipped: turn=%d current_tokens=%d tokens_at_last_extraction=%d tool_calls_since_last_update=%d last_turn_has_tool_calls=%s",
            turn,
            current_tokens,
            current_status.tokens_at_last_extraction,
            tool_calls_since_update,
            last_turn_has_tool_calls,
        )
        current_status.tool_calls_since_last_update = tool_calls_since_update
        session_memory_manager.set_status(current_status)
        return _session_memory_state_payload(current_status)

    logger.info(
        "Session memory extract requested but no worker configured: turn=%d current_tokens=%d",
        turn,
        current_tokens,
    )
    return _session_memory_state_payload(current_status)


def _build_compression_message_ops(result: CompressResult) -> list:
    """构造 LangGraph message 更新操作。"""
    message_ops: list = [RemoveMessage(id=msg_id) for msg_id in result.remove_message_ids]
    message_ops.append(result.boundary_message)
    message_ops.append(result.summary_message)
    return message_ops


def _apply_time_based_microcompact_if_needed(
    history: list[BaseMessage],
    *,
    query_source: str,
) -> list[BaseMessage]:
    if query_source not in {"interactive", "resume"}:
        return history

    result = maybe_time_based_microcompact(
        history,
        now_ts_ms=int(time.time() * 1000),
    )
    if result.triggered:
        logger.info(
            "Time-based microcompact applied: cleared=%d query_source=%s",
            result.cleared_count,
            query_source,
        )
    return result.messages

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
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, RemoveMessage, SystemMessage

from config.settings import CONTEXT as CONTEXT_CONFIG
from core.context.budget import budget_snapshot
from core.event_bus import AgentEvent, EventBus, EventType
from core.state import AgentState, ToolCallInfo
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

    def reasoning_node(state: AgentState) -> dict:
        turn = state.get("turn_count", 0)

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

        history = list(state.get("messages", []))
        messages.extend(history)

        # 3) 估算当前 messages 的 token 数并更新统计，让压缩检查基于当前轮
        if session_stats is not None:
            total = _update_context_budget_stats(messages, session_stats)
            logger.debug("Estimated input tokens: %d", total)

        # 4) 压缩检查 — 基于刚估算的 token 数决定是否压缩
        compress_result = None
        if compressor is not None and session_stats is not None:
            compress_result = _maybe_compress(
                compressor, event_bus, session_stats, state,
            )
            # 如果压缩了，重新构建 messages
            if compress_result is not None:
                messages = [system_msg]
                if turn == 0 and context_manager is not None:
                    session_ctx = context_manager.build_session_context()
                    if session_ctx:
                        from langchain_core.messages import HumanMessage
                        messages.append(HumanMessage(content=session_ctx))
                messages.extend(compress_result.compressed_messages)
                # 重新估算压缩后的 token 数
                total = _update_context_budget_stats(messages, session_stats)
                logger.debug("Estimated tokens after compression: %d", total)

        # 5) 流式调用 LLM, 逐 chunk 发送 EventBus 事件
        collected = _stream_with_events(
            bound_llm, messages, event_bus, turn,
            compressor=compressor,
            session_stats=session_stats,
            state=state,
        )

        # 6) 收集 token usage → SessionStats
        if session_stats is not None:
            _record_token_usage(collected, session_stats)
            _update_context_budget_stats_from_count(
                session_stats.last_input_tokens,
                session_stats,
            )

        # 7) 构造 AIMessage 写入 state.messages 历史
        ai_message = AIMessage(
            content=collected.content or "",
            tool_calls=collected.tool_calls or [],
        )
        event_bus.emit(AgentEvent(
            type=EventType.TRANSCRIPT_MESSAGE,
            data={
                "role": "assistant",
                "content": ai_message.content,
                "tool_calls": ai_message.tool_calls or [],
            },
            turn=turn,
        ))

        # 8) tool_calls → pending_tool_calls (供 tool_routing 审批)
        pending = _extract_tool_calls(collected, event_bus, turn)

        # 9) TURN_START 事件
        event_bus.emit(AgentEvent(
            type=EventType.TURN_START,
            data={
                "turn": turn + 1,
                "has_tool_calls": bool(pending),
                "tool_count": len(pending),
            },
            turn=turn + 1,
        ))

        logger.info(
            "reasoning turn=%d content_len=%d tool_calls=%d",
            turn + 1, len(ai_message.content), len(pending),
        )

        result = {
            "messages": [ai_message],
            "turn_count": turn + 1,
            "pending_tool_calls": pending,
        }

        # 合并压缩操作 — RemoveMessage + summary_message 需要和 ai_message 一起写入 state
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
) -> AIMessageChunk:
    """流式调用 LLM, 每个 chunk 通过 EventBus 推送事件。

    如果遇到 400 context length 错误，触发强制压缩并重试。
    """

    collected: AIMessageChunk | None = None

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
            if reasoning:
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
                            aggressive_result = CompressResult(
                                remove_message_ids=[msg.id for msg in history[:-keep_count] if msg.id],
                                summary_message=compressor.build_summary_message("Previous conversation context has been compressed due to length limits."),
                                summary_text="Previous conversation context has been compressed due to length limits.",
                                compressed_messages=[compressor.build_summary_message("Previous conversation context has been compressed due to length limits."), *history[-keep_count:]],
                                removed_count=len(history) - keep_count,
                                kept_count=keep_count,
                            )

                        logger.info("Forced compression: removed=%d kept=%d", aggressive_result.removed_count, aggressive_result.kept_count)

                        # 发送压缩事件
                        event_bus.emit(AgentEvent(
                            type=EventType.CONTEXT_COMPRESSED,
                            data={
                                "summary": aggressive_result.summary_text,
                                "removed_count": aggressive_result.removed_count,
                                "kept_count": aggressive_result.kept_count,
                            },
                        ))

                        # 重建 messages（保留 system prompt，替换历史为压缩后的）
                        system_msg = messages[0] if messages and isinstance(messages[0], SystemMessage) else None
                        new_messages = []
                        if system_msg:
                            new_messages.append(system_msg)
                        new_messages.extend(aggressive_result.compressed_messages)

                        # 重试 LLM 调用（不传递 compressor 避免无限递归）
                        logger.info("Retrying LLM call with compressed context")
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

    return collected



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


def _maybe_compress(
    compressor: ContextCompressor,
    event_bus: EventBus,
    session_stats: SessionStats,
    state: AgentState,
) -> CompressResult | None:
    """检查是否需要压缩，若需要则执行并返回 state 更新。"""
    if not compressor.should_compress(session_stats.last_input_tokens):
        return None

    history = list(state.get("messages", []))
    if not history:
        return None

    logger.info(
        "Context compression triggered: last_input_tokens=%d",
        session_stats.last_input_tokens,
    )

    result = compressor.compress(history)
    if result is None:
        return None

    # 发送事件通知 CLI
    event_bus.emit(AgentEvent(
        type=EventType.CONTEXT_COMPRESSED,
        data={
            "summary": result.summary_text,
            "removed_count": result.removed_count,
            "kept_count": result.kept_count,
        },
    ))

    logger.info(
        "Compression complete: removed=%d kept=%d",
        result.removed_count, result.kept_count,
    )

    return result


def _build_compression_message_ops(result: CompressResult) -> list:
    """构造 LangGraph message 更新操作。"""
    message_ops: list = [RemoveMessage(id=msg_id) for msg_id in result.remove_message_ids]
    message_ops.append(result.summary_message)
    return message_ops

"""
人工审批节点 — 高风险工具调用的用户确认

对应 gemini-cli confirmation-bus:
  1. 通过 LangGraph interrupt 暂停图执行
  2. 将审批请求返回给 CLI 层
  3. CLI 层渲染确认对话框, 用户选择 (允许/拒绝)
  4. 图恢复后根据用户决策更新工具调用状态
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.types import interrupt

from core.event_bus import AgentEvent, EventBus, EventType
from core.state import AgentState, ToolCallInfo

logger = logging.getLogger(__name__)


def create_human_approval_node(
    event_bus: EventBus,
) -> Callable[[AgentState], dict]:
    """
    创建 human_approval 节点函数

    Args:
        event_bus: 事件总线

    Returns:
        LangGraph 节点函数 ``(AgentState) -> dict``

    interrupt 返回值格式 (由 CLI 层提供, 逐条决策)::

        {"call_1": True, "call_2": False}
    """

    def human_approval_node(state: AgentState) -> dict:
        approval_requests = state.get("approval_requests", [])
        if not approval_requests:
            return {}

        # ── 暂停图执行, 等待用户决策 ──
        response = interrupt(value=approval_requests)

        # ── 解析用户决策 ──
        decisions = _parse_response(response, approval_requests)

        # ── 根据决策更新 pending_tool_calls 状态 ──
        pending = state.get("pending_tool_calls", [])
        updated_calls: list[ToolCallInfo] = []
        for tc in pending:
            if tc["status"] != "awaiting_approval":
                updated_calls.append(tc)
                continue

            approved = decisions.get(tc["call_id"], False)
            if approved:
                updated_calls.append({**tc, "status": "pending"})
            else:
                updated_calls.append({**tc, "status": "cancelled"})

        # ── 发送 APPROVAL_RESPONSE 事件 ──
        event_bus.emit(AgentEvent(
            type=EventType.APPROVAL_RESPONSE,
            data={"decisions": decisions},
            turn=state.get("turn_count", 0),
        ))

        logger.info(
            "human_approval: %d approved, %d denied",
            sum(1 for v in decisions.values() if v),
            sum(1 for v in decisions.values() if not v),
        )

        approved_call_ids = {
            tc["call_id"]
            for tc in updated_calls
            if tc.get("status") == "pending"
        }

        result: dict[str, Any] = {
            "pending_tool_calls": updated_calls,
            "needs_human_approval": False,
            "approval_requests": [],
        }
        messages_update = _rewrite_latest_tool_call_message(
            list(state.get("messages", [])),
            decisions=decisions,
            approved_call_ids=approved_call_ids,
        )
        if messages_update is not None:
            result["messages"] = [messages_update]
        return result

    return human_approval_node


def post_approval_route(state: AgentState) -> str:
    """审批后决定后续路径：有已批准工具则进 tools，否则回 reasoning。"""
    pending = state.get("pending_tool_calls", [])
    if any(tc.get("status") == "pending" for tc in pending):
        return "tools"
    return "reasoning"


def _parse_response(
    response: Any,
    approval_requests: list[dict],
) -> dict[str, bool]:
    """
    解析用户响应为 {call_id: bool} 映射

    期望格式: {call_id: True/False, ...}  (逐条决策, 对齐 gemini-cli)
    非法输入兜底: 全部拒绝
    """
    if isinstance(response, dict):
        return {str(k): bool(v) for k, v in response.items()}

    # 兜底: 视为全部拒绝
    return {req["call_id"]: False for req in approval_requests}


def _rewrite_latest_tool_call_message(
    messages: list[BaseMessage],
    *,
    decisions: dict[str, bool],
    approved_call_ids: set[str],
) -> AIMessage | None:
    """按审批结果重写最近一条 assistant tool_calls 消息。"""
    if not decisions:
        return None

    decision_ids = set(decisions)
    for message in reversed(messages):
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue

        tool_call_ids = {
            str(tc.get("id"))
            for tc in message.tool_calls
            if tc.get("id")
        }
        if not (tool_call_ids & decision_ids):
            continue

        filtered_tool_calls = [
            tc for tc in message.tool_calls
            if tc.get("id") in approved_call_ids
        ]
        content = message.content
        if not filtered_tool_calls and not content:
            content = "[用户拒绝了工具调用]"

        return AIMessage(
            content=content,
            tool_calls=filtered_tool_calls,
            additional_kwargs=dict(message.additional_kwargs or {}),
            id=message.id,
            response_metadata=getattr(message, "response_metadata", None) or {},
        )

    return None

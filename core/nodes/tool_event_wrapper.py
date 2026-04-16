"""ToolNode EventBus 集成 — 在工具执行前后发送事件"""

from __future__ import annotations

import logging
from typing import Callable

from langchain_core.messages import ToolMessage

from core.event_bus import AgentEvent, EventBus, EventType

logger = logging.getLogger(__name__)


def create_event_bus_wrapper(event_bus: EventBus) -> Callable:
    """创建 ToolNode wrap_tool_call，在工具执行前后发送 EventBus 事件

    利用 response_format="content_and_artifact" 机制：
    ToolMessage.artifact 中包含 display 和 metadata（如 diff），
    无需通过实例属性传递，线程安全。
    """

    def wrapper(request, execute):
        tc = request.tool_call
        tool_name = tc["name"]
        call_id = tc["id"]

        # ── executing ──
        event_bus.emit(AgentEvent(
            type=EventType.TOOL_STATE_UPDATE,
            data={"call_id": call_id, "tool_name": tool_name, "status": "executing"},
        ))

        result = execute(request)

        # ── 从 ToolMessage 提取结果信息 ──
        status = "success"
        display = ""
        error_msg = ""

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

        return result

    return wrapper

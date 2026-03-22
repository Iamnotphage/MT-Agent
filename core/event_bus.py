from dataclasses import dataclass
from enum import Enum
from typing import Any

class EventType(Enum):
    """事件类型"""
    # 流式输出
    CONTENT = "content"
    THOUGHT = "thought"
    TOOL_CALL_REQUEST = "tool_call_request"

    # 工具执行
    TOOL_STATE_UPDATE = "tool_state_update"
    TOOL_LIVE_OUTPUT = "tool_live_output"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    ALL_TOOLS_COMPLETE = "all_tools_complete"

    # 权限确认
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"

    # 会话控制
    TURN_STATE = "turn_state"
    TURN_END = "turn_end"
    SESSION_END = "session_end"
    ERROR = "error"
    CONTEXT_COMPRESSED = "context_compressed"

@dataclass
class AgentEvent:
    type: EventType
    data: Any
    turn: int = 0
    timestamp: float = 0.0
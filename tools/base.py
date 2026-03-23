"""工具基类 — 定义工具接口、风险等级、执行结果"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel


class ToolRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ToolResult:
    """工具执行结果 — 同时面向 LLM (output) 和用户 (display)"""

    output: str
    display: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None


class BaseTool(ABC):
    """所有工具的抽象基类

    子类需设置类属性 name / description / args_schema，
    并实现 execute()。ToolRegistry 据此自动生成 LLM function-calling schema。
    """

    name: str
    description: str
    risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM
    args_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具，kwargs 对应 args_schema 的字段"""
        ...

    @property
    def schema(self) -> dict[str, Any]:
        """OpenAI function-calling schema（bind_tools 直接可用）"""
        json_schema = self.args_schema.model_json_schema()
        json_schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": json_schema,
            },
        }

"""save_memory — 让 Agent 能够持久化记忆"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.tools.base import ToolException
from pydantic import BaseModel, ConfigDict, Field

from tools.base import BaseTool, ToolRiskLevel


class SaveMemoryArgs(BaseModel):
    fact: str = Field(
        description="A clear, self-contained statement in natural language.",
    )


class SaveMemoryTool(BaseTool):
    """持久化 Agent 记忆"""

    name: str = "save_memory"
    description: str = (
        "Save an important fact to persistent memory so it can be reused across sessions. "
        "Use this when the user explicitly asks you to remember something, or when you "
        "discover stable project knowledge that will likely be useful later."
    )
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    response_format: str = "content_and_artifact"
    args_schema: type = SaveMemoryArgs
    save_fn: Callable = Field(exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, save_fn: Callable[[str], str | None], **kwargs: Any) -> None:
        super().__init__(save_fn=save_fn, **kwargs)

    def _run(self, **kwargs: Any) -> tuple[str, dict]:
        fact: str = kwargs["fact"]
        if not fact.strip():
            raise ToolException("记忆内容不能为空")

        try:
            self.save_fn(fact)
            return f"已保存记忆: {fact}", {"display": f"💾 已记住: {fact}"}
        except Exception as e:
            raise ToolException(f"保存记忆失败: {e}")

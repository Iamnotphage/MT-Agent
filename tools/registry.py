"""工具注册中心 — 注册 / 查找 / schema 收集 / 执行分发"""

from __future__ import annotations

import logging
from typing import Any

from tools.base import BaseTool, ToolResult, ToolRiskLevel

logger = logging.getLogger(__name__)


class ToolRegistry:

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ── 注册 ─────────────────────────────────────────────────────
    def register(self, *tools: BaseTool) -> None:
        for tool in tools:
            if tool.name in self._tools:
                logger.warning("工具 %s 已注册，覆盖旧实例", tool.name)
            self._tools[tool.name] = tool
            logger.debug("注册工具: %s [%s]", tool.name, tool.risk_level.value)

    # ── 查找 ─────────────────────────────────────────────────────
    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """所有工具的 function-calling schema，直接传给 llm.bind_tools()"""
        return [t.schema for t in self._tools.values()]

    # ── 执行 ─────────────────────────────────────────────────────
    async def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(output="", error=f"未知工具: {name}")
        try:
            validated = tool.args_schema(**args)
            return await tool.execute(**validated.model_dump())
        except Exception as e:
            logger.exception("工具 %s 执行出错", name)
            return ToolResult(output="", error=str(e))

    # ── 权限 ─────────────────────────────────────────────────────
    def needs_confirmation(self, name: str) -> bool:
        tool = self._tools.get(name)
        if tool is None:
            return True
        return tool.risk_level in (ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

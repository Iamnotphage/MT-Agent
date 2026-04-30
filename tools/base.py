"""工具基础模块 — ToolRiskLevel 枚举 + 从 langchain_core 重导出 BaseTool"""

from __future__ import annotations

from enum import Enum

from langchain_core.tools import BaseTool
from langchain_core.tools.base import ToolException


class ToolRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

from tools.base import BaseTool, ToolRiskLevel
from tools.files.read_file import ReadFileTool
from tools.files.write_file import WriteFileTool
from tools.files.ls import LsTool
from tools.files.glob import GlobTool
from tools.files.grep import GrepTool
from tools.files.edit_file import EditFileTool
from tools.agent.memory import SaveMemoryTool

__all__ = [
    # Base
    "ToolRiskLevel",
    # File System
    "ReadFileTool", "WriteFileTool", "LsTool", "GlobTool", "GrepTool", "EditFileTool",
    # Agent Ops
    "SaveMemoryTool",
    "create_default_tools",
]


def create_default_tools(*, workspace: str, save_memory_fn=None) -> list[BaseTool]:
    """集中创建所有内置工具，新增工具只需改这里"""
    tools: list[BaseTool] = [
        ReadFileTool(workspace=workspace),
        WriteFileTool(workspace=workspace),
        LsTool(workspace=workspace),
        GlobTool(workspace=workspace),
        GrepTool(workspace=workspace),
        EditFileTool(workspace=workspace),
    ]
    if save_memory_fn is not None:
        tools.append(SaveMemoryTool(save_fn=save_memory_fn))
    return tools

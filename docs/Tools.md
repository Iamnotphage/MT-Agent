# Tools

此文档说明 Tool 模块的设计与调用链路，帮助理解现有工具实现和新增工具的步骤。

## 目录结构

```
tools/
├── __init__.py              # 导出 + create_default_tools() 集中注册
├── base.py                  # 重导出 langchain BaseTool + ToolRiskLevel
├── policy.py                # 风险等级映射表（供 tool_routing 查表）
├── agent_ops/
│   ├── __init__.py
│   └── memory.py            # SaveMemoryTool
└── file_ops/
    ├── __init__.py
    ├── read_file.py         # ReadFileTool  (LOW)
    ├── write_file.py        # WriteFileTool (MEDIUM)
    ├── edit_file.py         # EditFileTool  (MEDIUM)
    ├── ls.py                # LsTool        (LOW)
    ├── glob.py              # GlobTool      (LOW)
    └── grep.py              # GrepTool      (LOW)
```

## 核心概念

### BaseTool

项目工具现在直接基于 `langchain_core.tools.BaseTool`：

- `tools.base.BaseTool` 是对 LangChain `BaseTool` 的重导出，工具实现天然兼容 `llm.bind_tools()` 和 `langgraph.prebuilt.ToolNode`
- `ToolRiskLevel` 是项目侧补充的风险等级声明，用于 `tool_routing` 判断是否需要人工审批
- 工具通过 `response_format="content_and_artifact"` 返回双通道结果：`content` 给 LLM/ToolMessage，`artifact` 给 CLI/EventBus 展示富数据

子类直接实现 LangChain 标准的 `_run()` 方法：
- 成功时返回 `(content, artifact)` 元组，其中 `content` 是 LLM 看到的文本，`artifact` 是结构化展示数据
- 失败时抛出 `ToolException`，`ToolNode(handle_tool_errors=True)` 会把异常转换为 error `ToolMessage`
- `artifact` 会进入 `ToolMessage.artifact`，再由 `ToolNode` wrapper 读取并发送 EventBus 事件

```python
from pathlib import Path
from pydantic import BaseModel, Field

from langchain_core.tools.base import ToolException
from tools.base import BaseTool, ToolRiskLevel


class MyToolArgs(BaseModel):
    file_path: str = Field(description="目标文件路径（相对于工作区）")


class MyTool(BaseTool):
    name: str = "my_tool"
    description: str = "..."
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    response_format: str = "content_and_artifact"
    args_schema: type = MyToolArgs
    workspace: Path = Field(default_factory=lambda: Path.cwd())

    def _run(self, *, file_path: str) -> tuple[str, dict]:
        ...
        return (
            "LLM 看到的工具结果文本",
            {"display": "CLI 展示摘要", "metadata_key": "结构化富数据"},
        )
```

### ToolRiskLevel — 风险等级

决定工具调用是否需要用户确认：

| 等级 | 行为 | 典型场景 |
|------|------|----------|
| `LOW` | 自动执行，无需确认 | 读文件、列目录 |
| `MEDIUM` | 需要用户确认 | 写文件、编辑文件 |
| `HIGH` | 需要用户确认 + 高亮警告 | Shell 命令、远程操作 |

风险等级有两个来源，**工具自身声明**（`BaseTool.risk_level` 属性）和 **全局策略表**（`policy.py` 中的 `DEFAULT_TOOL_RISK`）。`tool_routing` 节点在路由时查表决定走自动执行还是人工审批。

### Tool 输出格式

当前工具统一使用 LangChain 的 `content_and_artifact` 输出格式，面向两个消费方：

```python
def _run(...) -> tuple[str, dict]:
    return (
        "content: 写入 ToolMessage.content，LLM 下一轮可以看到",
        {
            "display": "CLI 展示摘要",
            "diff": diff,  # 可选：EventBus wrapper 会作为 TOOL_LIVE_OUTPUT 推送
        },
    )
```

`content` 应该足够自解释，适合模型继续推理；`artifact` 则用于用户界面和结构化数据，不应成为模型理解任务结果的唯一来源。

## 调用链路

从 LLM 决定调用工具到结果回写消息历史的完整路径：

```
reasoning_node
  │  LLM 返回 tool_calls: [{name: "write_file", args: {...}}]
  │  → 写入 state.pending_tool_calls
  ▼
tool_routing_node
  │  查 policy.py 风险表 → 标记 status
  │  LOW → 保持 "pending"（直接放行）
  │  MEDIUM/HIGH → 标记 "awaiting_approval"
  ▼
human_approval_node（仅 MEDIUM/HIGH 走此节点）
  │  LangGraph interrupt → CLI 渲染确认对话框
  │  用户批准 → 放行  /  用户拒绝 → 生成 rejection ToolMessage
  ▼
tools 节点 (langgraph.prebuilt.ToolNode)
  │  自动并行执行所有工具调用
  │  tool._run(**args) → 生成 ToolMessage 并回写 state.messages
  │  EventBus wrapper 在执行前后发送状态事件
  ▼
reasoning_node（下一轮，LLM 看到 ToolMessage 决定继续或结束）
```

新版链路里已经没有独立的 `tool_execution` 和 `observation` 节点：
- 旧 `tool_execution` 的“查找工具、执行工具、并行调度、错误转 ToolMessage”职责由 `ToolNode` 接管
- 旧 `observation` 的“把结果追加为 ToolMessage”职责也由 `ToolNode` 接管
- `pending_tool_calls` 仍然保留，但只作为 `tool_routing` / `human_approval` 的审批元数据，不再承载工具执行结果

## 新增工具

### Step 1: 定义参数 Schema

继承 `BaseModel`，字段的 `description` 会被自动提取到 LLM function-calling schema：

```python
from pydantic import BaseModel, Field

class MyToolArgs(BaseModel):
    file_path: str = Field(description="目标文件路径（相对于工作区）")
    verbose: bool = Field(default=False, description="是否输出详细信息")
```

### Step 2: 实现工具类

继承 `BaseTool`，设置类属性，实现 `_run()` 方法：

```python
import os
from pathlib import Path
from typing import Any

from langchain_core.tools.base import ToolException
from pydantic import Field

from tools.base import BaseTool, ToolRiskLevel

class MyTool(BaseTool):
    name: str = "my_tool"
    description: str = "这段描述会被 LLM 看到，直接影响 LLM 何时选择此工具"
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    response_format: str = "content_and_artifact"
    args_schema: type = MyToolArgs
    workspace: Path = Field(default_factory=lambda: Path.cwd())

    def __init__(self, *, workspace: str | Path | None = None, **kwargs: Any) -> None:
        super().__init__(workspace=Path(workspace or os.getcwd()).resolve(), **kwargs)

    def _run(self, *, file_path: str, verbose: bool = False) -> tuple[str, dict]:
        # 实现逻辑...
        return (
            "LLM 看到的执行结果文本",
            {
                "display": "CLI 展示的简短摘要",
                "key": "可选的结构化数据",
            },
        )
```

**关键点**：
- `description` 直接决定 LLM 的工具选择行为，需精心编写
- `_run` 参数名必须与 `args_schema` 的字段名一致
- 设置 `response_format="content_and_artifact"` 后，`_run` 必须返回 `(content, artifact)`
- 涉及文件路径的工具必须做 workspace 边界校验（防路径越界）
- 失败时抛出 `ToolException("错误描述")`，不要返回错误字符串伪装成功

### Step 3: 注册

在 `tools/__init__.py` 的 `create_default_tools` 中添加一行：

```python
def create_default_tools(*, workspace: str, save_memory_fn=None) -> list[BaseTool]:
    tools: list[BaseTool] = [
        ReadFileTool(workspace=workspace),
        WriteFileTool(workspace=workspace),
        LsTool(workspace=workspace),
        MyTool(workspace=workspace),  # ← 新增
    ]
    if save_memory_fn is not None:
        tools.append(SaveMemoryTool(save_fn=save_memory_fn))
    return tools
```

### Step 4: 配置风险等级（可选）

如果工具的 `risk_level` 与 `policy.py` 中的全局策略表不一致，或该工具不在表中，在 `policy.py` 中补充：

```python
DEFAULT_TOOL_RISK: dict[str, str] = {
    # ...
    "my_tool": "low",  # ← 新增
}
```

未在表中的工具默认风险为 `DEFAULT_UNKNOWN_RISK = "medium"`。

## 已实现工具一览

**当前默认注册并可被 Agent 调用** 的工具

### File System

| 工具 | 风险 | 说明 |
|------|------|------|
| `read_file` | LOW | 读取文件内容，支持行范围、自动截断 |
| `write_file` | MEDIUM | 写入/创建文件，返回 diff 供 CLI 渲染 |
| `edit_file` | MEDIUM | 替换文件中的文本，支持精确/灵活/正则匹配，返回 diff |
| `ls` | LOW | 列出目录内容，自动跳过 `.git` 等无关目录 |
| `glob` | LOW | 查找匹配 glob 模式的文件 |
| `grep` | LOW | 搜索文件内容中的正则表达式，返回匹配行和行号 |

### Agent Operations

| 工具 | 风险 | 说明 |
|------|------|------|
| `save_memory` | LOW | 将重要事实写入全局 `CONTEXT.md` 的 `## Agent Memories` 区域，跨会话可用 |

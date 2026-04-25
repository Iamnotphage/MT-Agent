from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode

from core.event_bus import EventBus
from core.state import AgentState
from core.nodes.reasoning import create_reasoning_node, should_use_tools
from core.nodes.tool_routing import create_tool_routing_node, needs_approval
from core.nodes.human_approval import create_human_approval_node

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.context import ContextManager
    from core.session import SessionStats
    from core.context.compressor import ContextCompressor
    from tools.base import BaseTool


def build_agent_graph(
    llm: BaseChatModel,
    event_bus: EventBus,
    tools: list[BaseTool],
    checkpointer=None,
    context_manager: ContextManager | None = None,
    session_stats: SessionStats | None = None,
    compressor: ContextCompressor | None = None,
) -> StateGraph:
    """
    工厂模式创建结点，构建 ReAct 循环的 LangGraph 状态图

    Args:
        llm: LangChain ChatModel (如 ChatOpenAI)
        event_bus: 事件总线, 用于向 CLI 层推送流式事件
        tools: 工具实例列表 (继承 langchain BaseTool)
        checkpointer: LangGraph 检查点存储, 用于 interrupt/resume 和多轮对话

    Returns:
        编译后的 StateGraph runnable
    """

    # 工厂模式创建结点函数
    reasoning_node = create_reasoning_node(llm, event_bus, tools, context_manager, session_stats, compressor)
    tool_routing_node = create_tool_routing_node(event_bus)
    human_approval_node = create_human_approval_node(event_bus)

    # ToolNode — 自带并行执行 + ToolMessage 生成
    from core.nodes.tool_event_wrapper import create_event_bus_wrapper
    tool_node = ToolNode(
        tools,
        handle_tool_errors=True,
        wrap_tool_call=create_event_bus_wrapper(event_bus),
    )

    graph = StateGraph(AgentState)

    # add nodes
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("tool_routing", tool_routing_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("tools", tool_node)

    # 入口
    graph.add_edge(START, "reasoning")

    # reasoning -> 条件路由
    graph.add_conditional_edges(
        "reasoning",
        should_use_tools,
        {
            "use_tools": "tool_routing",
            "final_answer": END,
        }
    )

    # tool_routing -> 条件路由
    graph.add_conditional_edges(
        "tool_routing",
        needs_approval,
        {
            "needs_approval": "human_approval",
            "approved": "tools",
        }
    )

    # human_approval -> tools
    graph.add_edge("human_approval", "tools")

    # tools -> reasoning (ToolNode 直接输出 ToolMessage，不需要 observation)
    graph.add_edge("tools", "reasoning")

    return graph.compile(checkpointer=checkpointer)

"""
Agent 运行时 — 组装 LLM + EventBus + Tools + Graph

将 Agent 的构建逻辑与 CLI 层解耦，CLI / 测试 / API 均可复用。
"""

from __future__ import annotations

import os
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from config import load_llm_config
from config.settings import CONTEXT as CONTEXT_CONFIG
from core.context.compressor import ContextCompressor
from core.context.session_memory import SessionMemoryManager
from core.context.session_memory_worker import SessionMemoryExtractWorker
from core.context import ContextManager
from core.memory import MemoryManager
from core.session import SessionRecorder
from core.event_bus import EventBus
from core.graph import build_agent_graph
from core.llm import create_chat_model
from tools import BaseTool, create_default_tools


@dataclass
class AgentRuntime:
    """封装完整的 Agent 运行时组件，供 CLI / 测试 / API 复用"""

    graph: Any
    event_bus: EventBus
    tools: list[BaseTool]
    workspace: str
    context_manager: ContextManager
    memory_manager: MemoryManager
    session: SessionRecorder
    compressor: ContextCompressor | None = None
    session_memory_manager: SessionMemoryManager | None = None
    session_memory_worker: SessionMemoryExtractWorker | None = None
    checkpoint_manager: AbstractContextManager[Any] | None = None


def create_agent_runtime(
    *,
    workspace: str | None = None,
) -> AgentRuntime:
    """一行组装完整 Agent

    Usage::

        runtime = create_agent_runtime(workspace="/path/to/project")
        result = runtime.graph.invoke(state, config)
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    llm_cfg = load_llm_config()

    llm = create_chat_model(llm_cfg)

    event_bus = EventBus()

    # Context & Memory — 必须在工具注册之前初始化，因为 save_memory tool 需要回调
    ws = workspace or os.getcwd()
    ctx_manager = ContextManager(working_directory=ws, config=CONTEXT_CONFIG)
    memory_manager = MemoryManager(
        ctx_manager.global_context_path,
        on_update=ctx_manager.refresh_global_context,
    )
    ctx_manager.load()

    session = SessionRecorder(working_directory=ws, config=CONTEXT_CONFIG)
    session.stats.model = llm_cfg["model"]

    tools = create_default_tools(
        workspace=ws,
        save_memory_fn=memory_manager.save_memory,
    )

    # 为压缩器创建独立的 LLM 实例（不带 thinking mode）
    compressor_llm = create_chat_model(
        llm_cfg,
        streaming=False,
        temperature=0.0,
    )

    # 上下文压缩器
    compressor = ContextCompressor(
        llm=compressor_llm,
        token_limit=CONTEXT_CONFIG.get("token_limit", 65536),
        threshold=CONTEXT_CONFIG.get("compression_threshold", 0.50),
        preserve_ratio=CONTEXT_CONFIG.get("compression_preserve_ratio", 0.30),
        preserve_min_tokens=CONTEXT_CONFIG.get("compression_preserve_min_tokens", 10000),
        preserve_max_tokens=CONTEXT_CONFIG.get("compression_preserve_max_tokens", 40000),
    )
    session_memory_manager: SessionMemoryManager | None = None
    session_memory_worker: SessionMemoryExtractWorker | None = None

    if CONTEXT_CONFIG.get("enable_session_memory_compact", False):
        session_memory_manager = SessionMemoryManager(
            working_directory=ws,
            config=CONTEXT_CONFIG,
            session_id=session.stats.session_id,
            llm=compressor_llm,
        )
        session_memory_worker = SessionMemoryExtractWorker(session_memory_manager, event_bus)

    checkpoint_path = session.get_checkpoint_path()
    checkpoint_manager = SqliteSaver.from_conn_string(str(checkpoint_path))
    checkpointer = checkpoint_manager.__enter__()

    graph = build_agent_graph(
        llm=llm,
        event_bus=event_bus,
        tools=tools,
        session=session,
        checkpointer=checkpointer,
        context_manager=ctx_manager,
        session_stats=session.stats,
        compressor=compressor,
        session_memory_manager=session_memory_manager,
        session_memory_worker=session_memory_worker,
    )

    return AgentRuntime(
        graph=graph,
        event_bus=event_bus,
        tools=tools,
        workspace=ws,
        context_manager=ctx_manager,
        memory_manager=memory_manager,
        session=session,
        compressor=compressor,
        session_memory_manager=session_memory_manager,
        session_memory_worker=session_memory_worker,
        checkpoint_manager=checkpoint_manager,
    )

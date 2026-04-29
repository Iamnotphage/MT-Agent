from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from config.settings import CONTEXT as CONTEXT_CONFIG
from core.event_bus import EventType
from core.context.compressor import ContextCompressor
from core.context.session_memory import SessionMemoryCompactResult, SessionMemoryManager, build_session_memory_summary_message
from core.context.session_memory_worker import SessionMemoryExtractWorker
from core.session import SessionStats
from core.nodes.reasoning import _record_token_usage, create_reasoning_node, should_use_tools


class TestReasoningNode:
    """reasoning 节点测试"""

    def test_pure_text_response(self, event_bus, mock_llm_text):
        """LLM 返回纯文本 → pending_tool_calls 为空"""
        node = create_reasoning_node(mock_llm_text, event_bus)
        state = {
            "messages": [HumanMessage(content="你好")],
            "turn_count": 0,
        }

        result = node(state)

        assert result["turn_count"] == 1
        assert result["pending_tool_calls"] == []
        assert "你好" in result["messages"][0].content

    def test_tool_call_response(self, event_bus, mock_llm_tool_call):
        """LLM 返回 tool_calls → pending_tool_calls 非空"""
        node = create_reasoning_node(mock_llm_tool_call, event_bus)
        state = {
            "messages": [HumanMessage(content="读取 test.c")],
            "turn_count": 0,
        }

        result = node(state)

        assert result["turn_count"] == 1
        assert len(result["pending_tool_calls"]) == 1
        assert result["pending_tool_calls"][0]["tool_name"] == "read_file"
        assert result["pending_tool_calls"][0]["status"] == "pending"

    def test_turn_count_increments(self, event_bus, mock_llm_text):
        """turn_count 从任意值递增"""
        node = create_reasoning_node(mock_llm_text, event_bus)
        state = {"messages": [HumanMessage(content="hi")], "turn_count": 5}

        result = node(state)
        assert result["turn_count"] == 6

    def test_content_events_emitted(self, event_bus, mock_llm_text):
        """流式过程中发送了 CONTENT 事件"""
        received = []
        event_bus.subscribe_all(lambda e: received.append(e))

        node = create_reasoning_node(mock_llm_text, event_bus)
        state = {"messages": [HumanMessage(content="hi")], "turn_count": 0}
        node(state)

        content_events = [e for e in received if e.type == EventType.CONTENT]
        assert len(content_events) == 2
        assert content_events[0].data["text"] == "你好"
        assert content_events[1].data["text"] == "，我是 Agent"

    def test_tool_call_request_event(self, event_bus, mock_llm_tool_call):
        """tool_calls 触发 TOOL_CALL_REQUEST 事件"""
        received = []
        event_bus.subscribe(EventType.TOOL_CALL_REQUEST, lambda e: received.append(e))

        node = create_reasoning_node(mock_llm_tool_call, event_bus)
        state = {"messages": [HumanMessage(content="hi")], "turn_count": 0}
        node(state)

        assert len(received) == 1
        assert received[0].data["tool_name"] == "read_file"
        assert received[0].data["call_id"] == "call_123"

    def test_turn_start_event(self, event_bus, mock_llm_text):
        """每轮结束后发送 TURN_START 事件"""
        received = []
        event_bus.subscribe(EventType.TURN_START, lambda e: received.append(e))

        node = create_reasoning_node(mock_llm_text, event_bus)
        state = {"messages": [HumanMessage(content="hi")], "turn_count": 0}
        node(state)

        assert len(received) == 1
        assert received[0].data["turn"] == 1

    def test_assistant_transcript_event_emitted(self, event_bus, mock_llm_tool_call):
        """reasoning 完成后发送 canonical assistant transcript。"""
        received = []
        event_bus.subscribe(EventType.TRANSCRIPT_MESSAGE, lambda e: received.append(e))

        node = create_reasoning_node(mock_llm_tool_call, event_bus)
        state = {"messages": [HumanMessage(content="hi")], "turn_count": 0}
        node(state)

        assert len(received) == 1
        assert received[0].data["role"] == "assistant"
        assert received[0].data["tool_calls"][0]["name"] == "read_file"

    def test_llm_error_raises(self, event_bus):
        """LLM 调用失败 → 抛异常，不写入假消息"""
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        llm.stream.side_effect = Exception("API timeout")

        node = create_reasoning_node(llm, event_bus)
        state = {"messages": [HumanMessage(content="hi")], "turn_count": 0}

        with pytest.raises(Exception, match="API timeout"):
            node(state)

    def test_error_event_on_failure(self, event_bus):
        """LLM 失败时发送 ERROR 事件"""
        received = []
        event_bus.subscribe(EventType.ERROR, lambda e: received.append(e))

        llm = MagicMock()
        llm.bind_tools.return_value = llm
        llm.stream.side_effect = RuntimeError("connection refused")

        node = create_reasoning_node(llm, event_bus)
        state = {"messages": [HumanMessage(content="hi")], "turn_count": 0}
        with pytest.raises(RuntimeError, match="connection refused"):
            node(state)

        assert len(received) == 1
        assert "connection refused" in received[0].data["error"]

    def test_no_tools_skips_bind(self, event_bus):
        """tools=None 时不调用 bind_tools"""
        llm = MagicMock()
        llm.stream.return_value = iter([AIMessageChunk(content="ok")])

        create_reasoning_node(llm, event_bus, tools=None)

        llm.bind_tools.assert_not_called()

    def test_with_tools_calls_bind(self, event_bus):
        """传入 tools 时调用 bind_tools"""
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        from tools.file_ops.read_file import ReadFileTool
        tool_list = [ReadFileTool(workspace="/tmp")]

        create_reasoning_node(llm, event_bus, tools=tool_list)

        llm.bind_tools.assert_called_once_with(tool_list)

    def test_compression_applies_on_current_turn(self, event_bus):
        """触发压缩时，当轮发送给 LLM 的消息应使用摘要后的历史。"""
        old_limit = CONTEXT_CONFIG["token_limit"]
        old_reserved = CONTEXT_CONFIG["summary_reserved_tokens"]
        old_buffer = CONTEXT_CONFIG["autocompact_buffer_tokens"]
        CONTEXT_CONFIG["token_limit"] = 50
        CONTEXT_CONFIG["summary_reserved_tokens"] = 20
        CONTEXT_CONFIG["autocompact_buffer_tokens"] = 20
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        llm.stream.return_value = iter([AIMessageChunk(content="ok")])

        compressor_llm = MagicMock()
        compressor_llm.invoke.return_value = MagicMock(content="summary text")
        compressor = ContextCompressor(
            compressor_llm,
            token_limit=100,
            threshold=0.5,
            preserve_ratio=0.3,
            preserve_min_tokens=1,
            preserve_max_tokens=1000,
        )
        stats = SessionStats(last_input_tokens=80)

        try:
            node = create_reasoning_node(
                llm,
                event_bus,
                session_stats=stats,
                compressor=compressor,
            )
            state = {
                "messages": [
                    HumanMessage(content="u1", id="m1"),
                    HumanMessage(content="u2", id="m2"),
                    HumanMessage(content="u3", id="m3"),
                    HumanMessage(content="u4", id="m4"),
                ],
                "turn_count": 1,
            }

            result = node(state)

            streamed_messages = llm.stream.call_args.args[0]
            assert streamed_messages[1].content.startswith("<compact_boundary ")
            assert "conversation_history_summary" in streamed_messages[2].content
            assert streamed_messages[-1].content == "u4"
            assert result["messages"][0].id == "m1"
            assert result["messages"][1].id in {"m2", "m3"}
            assert result["messages"][-3].content.startswith("<compact_boundary ")
            assert "conversation_history_summary" in result["messages"][-2].content
        finally:
            CONTEXT_CONFIG["token_limit"] = old_limit
            CONTEXT_CONFIG["summary_reserved_tokens"] = old_reserved
            CONTEXT_CONFIG["autocompact_buffer_tokens"] = old_buffer

    def test_context_budget_stats_updated(self, event_bus, mock_llm_text):
        """reasoning 会更新当前上下文预算统计。"""
        stats = SessionStats()
        node = create_reasoning_node(
            mock_llm_text,
            event_bus,
            session_stats=stats,
        )
        state = {"messages": [HumanMessage(content="hello")], "turn_count": 0}

        node(state)

        assert stats.last_input_tokens > 0
        assert stats.last_effective_context_limit > 0
        assert stats.last_auto_compact_threshold > 0
        assert stats.last_tokens_until_compact >= 0

    def test_auto_compact_checked_event_emitted(self, event_bus, mock_llm_text):
        received = []
        event_bus.subscribe(EventType.AUTO_COMPACT_CHECKED, lambda e: received.append(e))
        stats = SessionStats()

        node = create_reasoning_node(
            mock_llm_text,
            event_bus,
            session_stats=stats,
            compressor=ContextCompressor(MagicMock()),
        )
        state = {"messages": [HumanMessage(content="hello")], "turn_count": 0}
        node(state)

        assert len(received) == 1
        assert "auto_compact_threshold" in received[0].data
        assert "should_compact" in received[0].data

    def test_auto_compact_failure_increments_counter(self, event_bus, mock_llm_text):
        old_limit = CONTEXT_CONFIG["token_limit"]
        old_reserved = CONTEXT_CONFIG["summary_reserved_tokens"]
        old_buffer = CONTEXT_CONFIG["autocompact_buffer_tokens"]
        CONTEXT_CONFIG["token_limit"] = 50
        CONTEXT_CONFIG["summary_reserved_tokens"] = 20
        CONTEXT_CONFIG["autocompact_buffer_tokens"] = 20
        stats = SessionStats()
        received = []
        event_bus.subscribe(EventType.AUTO_COMPACT_FAILED, lambda e: received.append(e))
        compressor = MagicMock()
        compressor.compress.side_effect = RuntimeError("compact blew up")

        try:
            node = create_reasoning_node(
                mock_llm_text,
                event_bus,
                session_stats=stats,
                compressor=compressor,
            )
            state = {
                "messages": [HumanMessage(content="u1"), HumanMessage(content="u2"), HumanMessage(content="u3"), HumanMessage(content="u4")],
                "turn_count": 1,
            }
            node(state)
        finally:
            CONTEXT_CONFIG["token_limit"] = old_limit
            CONTEXT_CONFIG["summary_reserved_tokens"] = old_reserved
            CONTEXT_CONFIG["autocompact_buffer_tokens"] = old_buffer

        assert stats.compression_failure_count == 1
        assert len(received) == 1
        assert "compact blew up" in received[0].data["error"]

    def test_auto_compact_circuit_breaker_skips_compress(self, event_bus, mock_llm_text):
        old_limit = CONTEXT_CONFIG["token_limit"]
        old_reserved = CONTEXT_CONFIG["summary_reserved_tokens"]
        old_buffer = CONTEXT_CONFIG["autocompact_buffer_tokens"]
        CONTEXT_CONFIG["token_limit"] = 50
        CONTEXT_CONFIG["summary_reserved_tokens"] = 20
        CONTEXT_CONFIG["autocompact_buffer_tokens"] = 20
        stats = SessionStats(compression_failure_count=3)
        received = []
        event_bus.subscribe(EventType.AUTO_COMPACT_DISABLED, lambda e: received.append(e))
        compressor = MagicMock()

        try:
            node = create_reasoning_node(
                mock_llm_text,
                event_bus,
                session_stats=stats,
                compressor=compressor,
            )
            state = {
                "messages": [HumanMessage(content="u1"), HumanMessage(content="u2"), HumanMessage(content="u3"), HumanMessage(content="u4")],
                "turn_count": 1,
            }
            node(state)
        finally:
            CONTEXT_CONFIG["token_limit"] = old_limit
            CONTEXT_CONFIG["summary_reserved_tokens"] = old_reserved
            CONTEXT_CONFIG["autocompact_buffer_tokens"] = old_buffer

        compressor.compress.assert_not_called()
        assert len(received) == 1
        assert received[0].data["consecutive_failures"] == 3

    def test_reasoning_content_is_preserved_for_tool_loop(self, event_bus):
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        llm.stream.return_value = iter([
            AIMessageChunk(
                content="",
                additional_kwargs={"reasoning_content": "need more tool work"},
                tool_call_chunks=[{
                    "name": "read_file",
                    "args": '{"path": "a.py"}',
                    "id": "call_123",
                    "index": 0,
                }],
            )
        ])

        node = create_reasoning_node(llm, event_bus)
        state = {"messages": [HumanMessage(content="inspect file")], "turn_count": 0}
        result = node(state)

        assistant = result["messages"][0]
        assert assistant.additional_kwargs["reasoning_content"] == "need more tool work"

    def test_multichunk_reasoning_content_is_accumulated_for_tool_loop(self, event_bus):
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        llm.stream.return_value = iter([
            AIMessageChunk(
                content="",
                additional_kwargs={"reasoning_content": "Let me "},
            ),
            AIMessageChunk(
                content="",
                additional_kwargs={"reasoning_content": "inspect files."},
                tool_call_chunks=[{
                    "name": "read_file",
                    "args": '{"path": "a.py"}',
                    "id": "call_123",
                    "index": 0,
                }],
            ),
        ])

        node = create_reasoning_node(llm, event_bus)
        state = {"messages": [HumanMessage(content="inspect file")], "turn_count": 0}
        result = node(state)

        assistant = result["messages"][0]
        assert assistant.additional_kwargs["reasoning_content"] == "Let me inspect files."

    def test_empty_reasoning_content_is_preserved_for_tool_loop(self, event_bus):
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        llm.stream.return_value = iter([
            AIMessageChunk(
                content="",
                additional_kwargs={"reasoning_content": ""},
                tool_call_chunks=[{
                    "name": "read_file",
                    "args": '{"path": "a.py"}',
                    "id": "call_123",
                    "index": 0,
                }],
            )
        ])

        node = create_reasoning_node(llm, event_bus)
        state = {"messages": [HumanMessage(content="inspect file")], "turn_count": 0}
        result = node(state)

        assistant = result["messages"][0]
        assert "reasoning_content" in assistant.additional_kwargs
        assert assistant.additional_kwargs["reasoning_content"] == ""

    def test_old_reasoning_content_is_cleared_when_prior_turn_had_no_tools(self, event_bus, mock_llm_text):
        node = create_reasoning_node(mock_llm_text, event_bus)
        history = [
            HumanMessage(content="question 1"),
            AIMessage(
                content="plain answer",
                additional_kwargs={"reasoning_content": "old chain"},
            ),
            HumanMessage(content="question 2"),
        ]
        state = {"messages": history, "turn_count": 1}

        node(state)

        streamed_messages = mock_llm_text.stream.call_args.args[0]
        assistant_history = streamed_messages[-2]
        assert isinstance(assistant_history, AIMessage)
        assert "reasoning_content" not in (assistant_history.additional_kwargs or {})

    def test_old_reasoning_content_is_preserved_after_tool_turn(self, event_bus, mock_llm_text):
        node = create_reasoning_node(mock_llm_text, event_bus)
        history = [
            HumanMessage(content="question 1"),
            AIMessage(
                content="let me inspect files",
                tool_calls=[{"name": "glob", "args": {}, "id": "call_1", "type": "tool_call"}],
                additional_kwargs={"reasoning_content": "tool turn thinking"},
            ),
            AIMessage(
                content="I found the files.",
                additional_kwargs={"reasoning_content": "final tool-turn reasoning"},
            ),
            HumanMessage(content="question 2"),
        ]
        state = {"messages": history, "turn_count": 1}

        node(state)

        streamed_messages = mock_llm_text.stream.call_args.args[0]
        first_assistant = streamed_messages[-3]
        second_assistant = streamed_messages[-2]
        assert isinstance(first_assistant, AIMessage)
        assert isinstance(second_assistant, AIMessage)
        assert first_assistant.additional_kwargs["reasoning_content"] == "tool turn thinking"
        assert second_assistant.additional_kwargs["reasoning_content"] == "final tool-turn reasoning"

    def test_reasoning_fallback_restores_missing_tool_turn_reasoning(self, event_bus, mock_llm_text):
        node = create_reasoning_node(mock_llm_text, event_bus)
        history = [
            HumanMessage(content="question 1"),
            AIMessage(
                content="let me inspect files",
                tool_calls=[{"name": "glob", "args": {}, "id": "call_1", "type": "tool_call"}],
            ),
            ToolMessage(content="result", tool_call_id="call_1", name="glob"),
            HumanMessage(content="question 2"),
        ]
        state = {
            "messages": history,
            "assistant_reasoning_fallbacks": [{
                "tool_call_ids": ["call_1"],
                "reasoning_content": "fallback thinking",
            }],
            "turn_count": 1,
        }

        node(state)

        streamed_messages = mock_llm_text.stream.call_args.args[0]
        first_assistant = streamed_messages[-3]
        assert isinstance(first_assistant, AIMessage)
        assert first_assistant.additional_kwargs["reasoning_content"] == "fallback thinking"

    def test_compacted_history_preserves_reasoning_content(self, event_bus, mock_llm_text):
        node = create_reasoning_node(mock_llm_text, event_bus)
        history = [
            HumanMessage(content='<compact_boundary pre_tokens="100" post_tokens="20" reason="threshold_exceeded" />'),
            HumanMessage(content="<conversation_history_summary>\nsummary\n</conversation_history_summary>"),
            AIMessage(
                content="20 files read",
                additional_kwargs={"reasoning_content": "tool-backed turn reasoning"},
            ),
            HumanMessage(content="继续读30个文件"),
        ]
        state = {"messages": history, "turn_count": 1}

        node(state)

        streamed_messages = mock_llm_text.stream.call_args.args[0]
        compacted_assistant = streamed_messages[-2]
        assert isinstance(compacted_assistant, AIMessage)
        assert compacted_assistant.additional_kwargs["reasoning_content"] == "tool-backed turn reasoning"

    def test_session_memory_extract_is_scheduled_and_completes_in_background(self, event_bus, tmp_path, mock_llm_text):
        received = []
        event_bus.subscribe(EventType.SESSION_MEMORY_UPDATED, lambda e: received.append(e))
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="# Session Title\nUpdated")
        session_memory_manager = SessionMemoryManager(
            working_directory=str(tmp_path),
            config={"global_dir": str(tmp_path / "global")},
            session_id="sid",
            llm=llm,
        )
        worker = SessionMemoryExtractWorker(session_memory_manager, event_bus)

        node = create_reasoning_node(
            mock_llm_text,
            event_bus,
            session_memory_manager=session_memory_manager,
            session_memory_worker=worker,
        )
        state = {
            "messages": [HumanMessage(content="x" * 50000, id="u1")],
            "turn_count": 0,
            "session_memory_tokens_at_last_extraction": 0,
            "session_memory_tool_calls_since_update": 0,
        }

        result = node(state)
        assert worker.wait_for_idle(2.0) is True

        assert len(received) == 1
        assert result["session_memory_summary_path"] == "session-memory/summary.md"
        assert result["session_memory_tokens_at_last_extraction"] == 0
        status = session_memory_manager.get_status()
        assert status.tokens_at_last_extraction > 0

    def test_auto_compact_prefers_session_memory_before_full_compact(self, event_bus, tmp_path, mock_llm_text):
        old_limit = CONTEXT_CONFIG["token_limit"]
        old_reserved = CONTEXT_CONFIG["summary_reserved_tokens"]
        old_buffer = CONTEXT_CONFIG["autocompact_buffer_tokens"]
        CONTEXT_CONFIG["token_limit"] = 220
        CONTEXT_CONFIG["summary_reserved_tokens"] = 20
        CONTEXT_CONFIG["autocompact_buffer_tokens"] = 20
        stats = SessionStats()
        compressor = MagicMock()
        session_memory_manager = SessionMemoryManager(
            working_directory=str(tmp_path),
            config={"global_dir": str(tmp_path / "global")},
            session_id="sid",
        )
        session_memory_manager.try_session_memory_compact = MagicMock(return_value=SessionMemoryCompactResult(
            boundary_message=ContextCompressor.build_compact_boundary_message(
                pre_tokens=100,
                post_tokens=30,
                reason="session_memory",
            ),
            summary_message=build_session_memory_summary_message(
                "# Session Title\nSaved memory",
                summary_path="session-memory/summary.md",
            ),
            compacted_messages=[
                ContextCompressor.build_compact_boundary_message(
                    pre_tokens=100,
                    post_tokens=30,
                    reason="session_memory",
                ),
                build_session_memory_summary_message(
                    "# Session Title\nSaved memory",
                    summary_path="session-memory/summary.md",
                ),
                AIMessage(content="a2", id="m4"),
            ],
            last_summarized_message_id="m3",
            start_index=3,
            kept_tokens=10,
            post_tokens=30,
        ))
        received = []
        event_bus.subscribe(EventType.CONTEXT_COMPRESSED, lambda e: received.append(e))

        try:
            node = create_reasoning_node(
                mock_llm_text,
                event_bus,
                session_stats=stats,
                compressor=compressor,
                session_memory_manager=session_memory_manager,
            )
            state = {
                "messages": [
                    HumanMessage(content="u1" * 200, id="m1"),
                    AIMessage(content="a1" * 200, id="m2"),
                    HumanMessage(content="u2", id="m3"),
                    AIMessage(content="a2", id="m4"),
                ],
                "turn_count": 1,
                "session_memory_summary_path": "session-memory/summary.md",
            }
            result = node(state)
        finally:
            CONTEXT_CONFIG["token_limit"] = old_limit
            CONTEXT_CONFIG["summary_reserved_tokens"] = old_reserved
            CONTEXT_CONFIG["autocompact_buffer_tokens"] = old_buffer

        compressor.compress.assert_not_called()
        assert any(getattr(msg, "content", "").startswith("<compact_boundary ") for msg in result["messages"] if hasattr(msg, "content"))
        assert any("session_memory_summary" in getattr(msg, "content", "") for msg in result["messages"] if hasattr(msg, "content"))
        assert received[0].data["trigger_reason"] == "session_memory"


class TestShouldUseTools:
    """条件路由函数测试"""

    def test_has_tools(self):
        state = {"pending_tool_calls": [{"tool_name": "read_file"}]}
        assert should_use_tools(state) == "use_tools"

    def test_empty_tools(self):
        assert should_use_tools({"pending_tool_calls": []}) == "final_answer"

    def test_missing_key(self):
        assert should_use_tools({}) == "final_answer"


class TestTokenUsageFallback:

    def test_fallback_to_estimated_tokens_when_usage_missing(self):
        stats = SessionStats(last_input_tokens=123)
        response = AIMessageChunk(content="hello world")

        _record_token_usage(response, stats)

        assert stats.turn_count == 1
        assert stats.total_input_tokens == 123
        assert stats.total_output_tokens > 0


class TestTimeBasedMicrocompact:

    def test_reasoning_uses_microcompacted_view_after_long_pause(self, event_bus, mock_llm_text):
        from core.context.microcompact import MICROCOMPACT_PLACEHOLDER

        old_messages = [
            AIMessage(content="prior assistant reply", response_metadata={"timestamp_ms": 100}),
            ToolMessage(content="old grep 1", tool_call_id="call_1", name="grep"),
            ToolMessage(content="old grep 2", tool_call_id="call_2", name="grep"),
            ToolMessage(content="old shell 1", tool_call_id="call_3", name="shell"),
            ToolMessage(content="old shell 2", tool_call_id="call_4", name="shell"),
            ToolMessage(content="old glob 1", tool_call_id="call_5", name="glob"),
            ToolMessage(content="old glob 2", tool_call_id="call_6", name="glob"),
            ToolMessage(content="recent read_file output", tool_call_id="call_7", name="read_file"),
        ]
        state = {
            "messages": old_messages,
            "turn_count": 1,
            "query_source": "interactive",
        }

        node = create_reasoning_node(mock_llm_text, event_bus)
        node(state)

        streamed_messages = mock_llm_text.stream.call_args.args[0]
        placeholder_count = sum(
            1 for msg in streamed_messages
            if getattr(msg, "content", "") == MICROCOMPACT_PLACEHOLDER
        )
        assert placeholder_count > 0

    def test_reasoning_microcompact_does_not_modify_state_messages(self, event_bus, mock_llm_text):
        original_content = "old grep output"
        old_messages = [
            AIMessage(content="prior reply", response_metadata={"timestamp_ms": 100}),
            ToolMessage(content=original_content, tool_call_id="call_1", name="grep"),
            ToolMessage(content="old shell", tool_call_id="call_2", name="shell"),
            ToolMessage(content="old glob", tool_call_id="call_3", name="glob"),
            ToolMessage(content="old ls", tool_call_id="call_4", name="ls"),
            ToolMessage(content="old write", tool_call_id="call_5", name="write_file"),
            ToolMessage(content="old edit", tool_call_id="call_6", name="edit_file"),
            ToolMessage(content="recent output", tool_call_id="call_7", name="read_file"),
        ]
        state = {
            "messages": old_messages,
            "turn_count": 1,
            "query_source": "interactive",
        }

        node = create_reasoning_node(mock_llm_text, event_bus)
        node(state)

        assert state["messages"][1].content == original_content

    def test_reasoning_microcompact_does_not_trigger_for_compact_source(self, event_bus, mock_llm_text):
        from core.context.microcompact import MICROCOMPACT_PLACEHOLDER

        old_messages = [
            AIMessage(content="prior reply", response_metadata={"timestamp_ms": 100}),
            ToolMessage(content="old grep output", tool_call_id="call_1", name="grep"),
        ]
        state = {
            "messages": old_messages,
            "turn_count": 1,
            "query_source": "compact",
        }

        node = create_reasoning_node(mock_llm_text, event_bus)
        node(state)

        streamed_messages = mock_llm_text.stream.call_args.args[0]
        assert not any(
            getattr(msg, "content", "") == MICROCOMPACT_PLACEHOLDER
            for msg in streamed_messages
        )

    def test_reasoning_microcompact_does_not_emit_transcript_rewrite(self, event_bus, mock_llm_text):
        from core.context.microcompact import MICROCOMPACT_PLACEHOLDER

        seen = []
        event_bus.subscribe(EventType.TRANSCRIPT_MESSAGE, lambda e: seen.append(e))

        old_messages = [
            AIMessage(content="prior reply", response_metadata={"timestamp_ms": 100}),
            ToolMessage(content="old grep", tool_call_id="call_1", name="grep"),
            ToolMessage(content="old shell", tool_call_id="call_2", name="shell"),
            ToolMessage(content="old glob", tool_call_id="call_3", name="glob"),
            ToolMessage(content="old ls", tool_call_id="call_4", name="ls"),
            ToolMessage(content="old write", tool_call_id="call_5", name="write_file"),
            ToolMessage(content="old edit", tool_call_id="call_6", name="edit_file"),
            ToolMessage(content="recent output", tool_call_id="call_7", name="read_file"),
        ]
        state = {
            "messages": old_messages,
            "turn_count": 1,
            "query_source": "interactive",
        }

        node = create_reasoning_node(mock_llm_text, event_bus)
        node(state)

        assert not any(
            e.data.get("content") == MICROCOMPACT_PLACEHOLDER
            and e.data.get("role") == "tool"
            for e in seen
        )

    def test_reasoning_emits_aimessage_with_timestamp(self, event_bus, mock_llm_text):
        node = create_reasoning_node(mock_llm_text, event_bus)
        state = {"messages": [HumanMessage(content="hi")], "turn_count": 0}

        result = node(state)

        ai_msg = result["messages"][0]
        ts = getattr(ai_msg, "response_metadata", {}).get("timestamp_ms")
        assert isinstance(ts, int)
        assert ts > 0

from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from core.context.compressor import ContextCompressor


def test_compress_includes_boundary_and_summary():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="<analysis>scratch</analysis>\n<summary>summary text</summary>")
    compressor = ContextCompressor(
        llm,
        preserve_min_tokens=1,
        preserve_max_tokens=1000,
    )

    result = compressor.compress([
        HumanMessage(content="u1", id="m1"),
        HumanMessage(content="u2", id="m2"),
        HumanMessage(content="u3", id="m3"),
        HumanMessage(content="u4", id="m4"),
    ])

    assert result is not None
    assert result.boundary_message.content.startswith("<compact_boundary ")
    assert "conversation_history_summary" in result.summary_message.content
    assert "<analysis>" not in result.summary_message.content
    assert "summary text" in result.summary_message.content
    assert result.compressed_messages[0].content.startswith("<compact_boundary ")
    assert "conversation_history_summary" in result.compressed_messages[1].content
    # full compact: compressed_messages 只包含 boundary + summary
    assert len(result.compressed_messages) == 2
    assert result.compressed_messages[0] is result.boundary_message
    assert result.compressed_messages[1] is result.summary_message


def test_compress_includes_manual_compact_instructions():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="<analysis>ok</analysis>\n<summary>done</summary>")
    compressor = ContextCompressor(
        llm,
        preserve_min_tokens=1,
        preserve_max_tokens=1000,
    )

    messages = [
        HumanMessage(content="u1", id="m1"),
        HumanMessage(content="u2", id="m2"),
        HumanMessage(content="u3", id="m3"),
        HumanMessage(content="u4", id="m4"),
    ]
    compressor.compress(
        messages,
        reason="manual",
        custom_instructions="Focus on test failures and Python file edits.",
    )

    invoke_messages = llm.invoke.call_args[0][0]
    system_prompt = invoke_messages[0].content
    assert "Compact Instructions" in system_prompt
    assert "Focus on test failures and Python file edits." in system_prompt


def test_compress_without_custom_instructions_omits_compact_section():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="<analysis>ok</analysis>\n<summary>done</summary>")
    compressor = ContextCompressor(
        llm,
        preserve_min_tokens=1,
        preserve_max_tokens=1000,
    )

    messages = [
        HumanMessage(content="u1", id="m1"),
        HumanMessage(content="u2", id="m2"),
        HumanMessage(content="u3", id="m3"),
        HumanMessage(content="u4", id="m4"),
    ]
    compressor.compress(messages)

    invoke_messages = llm.invoke.call_args[0][0]
    system_prompt = invoke_messages[0].content
    # The base prompt template contains "Compact Instructions" in its examples section,
    # but the actual custom instructions section should not be present
    assert "## Compact Instructions\n" not in system_prompt.split("</example>")[-1]

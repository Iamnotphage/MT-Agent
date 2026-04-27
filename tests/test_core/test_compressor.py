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

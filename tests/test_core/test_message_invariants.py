from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from core.context.message_invariants import (
    adjust_index_to_preserve_tool_pairs,
    find_last_compact_boundary,
    find_safe_split_index,
    is_compact_boundary_message,
)


def test_find_last_compact_boundary():
    messages = [
        HumanMessage(content="u1"),
        HumanMessage(content='<compact_boundary pre_tokens="10" post_tokens="5" reason="auto" />'),
        HumanMessage(content="u2"),
    ]

    assert find_last_compact_boundary(messages) == 1
    assert is_compact_boundary_message(messages[1]) is True


def test_adjust_index_to_preserve_tool_pairs_moves_to_ai_tool_call():
    messages = [
        HumanMessage(content="u1"),
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "call_1", "type": "tool_call"}]),
        ToolMessage(content="tool output", tool_call_id="call_1", name="read_file"),
        HumanMessage(content="u2"),
    ]

    assert adjust_index_to_preserve_tool_pairs(messages, 2) == 1


def test_find_safe_split_index_does_not_cross_boundary_or_tool_pair():
    messages = [
        HumanMessage(content="old1"),
        HumanMessage(content='<compact_boundary pre_tokens="10" post_tokens="5" reason="auto" />'),
        HumanMessage(content="keep1"),
        AIMessage(content="", tool_calls=[{"name": "glob", "args": {}, "id": "call_1", "type": "tool_call"}]),
        ToolMessage(content="glob result", tool_call_id="call_1", name="glob"),
        HumanMessage(content="keep2"),
        AIMessage(content="final answer"),
    ]

    split_idx = find_safe_split_index(
        messages,
        min_keep_tokens=1,
        max_keep_tokens=10_000,
    )

    assert split_idx is not None
    assert split_idx >= 2
    assert split_idx != 4

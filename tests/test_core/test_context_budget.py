from langchain_core.messages import AIMessage, HumanMessage

from core.context.budget import (
    auto_compact_threshold,
    budget_snapshot,
    effective_context_limit,
    estimate_message_tokens,
)


class TestEstimateMessageTokens:
    def test_empty_messages(self):
        assert estimate_message_tokens([]) == 0

    def test_simple_messages(self):
        messages = [
            HumanMessage(content="hello"),
            AIMessage(content="world"),
        ]
        assert estimate_message_tokens(messages) > 0

    def test_list_content_is_supported(self):
        msg = AIMessage(content=[{"type": "text", "text": "hello"}])
        assert estimate_message_tokens([msg]) > 0


class TestContextLimits:
    def test_effective_context_limit_default(self):
        assert effective_context_limit(131072) == 111072

    def test_effective_context_limit_has_lower_bound(self):
        assert effective_context_limit(1000, reserved_summary_tokens=1000) == 1

    def test_auto_compact_threshold_default_large_model(self):
        assert auto_compact_threshold(131072) == 98072

    def test_auto_compact_threshold_default_medium_model(self):
        assert auto_compact_threshold(65536) == 32536

    def test_auto_compact_threshold_has_lower_bound(self):
        assert auto_compact_threshold(1000, reserved_summary_tokens=999, buffer_tokens=999) == 1


class TestBudgetSnapshot:
    def test_snapshot_contains_expected_fields(self):
        snapshot = budget_snapshot([HumanMessage(content="hello")], token_limit=131072)
        assert set(snapshot) == {
            "raw_input_tokens",
            "effective_context_limit",
            "auto_compact_threshold",
            "tokens_until_compact",
        }

    def test_tokens_until_compact_is_clamped(self):
        snapshot = budget_snapshot(
            [HumanMessage(content="x" * 50000)],
            token_limit=1000,
            reserved_summary_tokens=100,
            buffer_tokens=50,
        )
        assert snapshot["tokens_until_compact"] == 0

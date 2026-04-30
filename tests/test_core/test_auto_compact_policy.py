from core.context.auto_compact import AutoCompactPolicy


class TestAutoCompactPolicy:

    def test_below_threshold_does_not_trigger(self):
        policy = AutoCompactPolicy()

        decision = policy.evaluate(
            raw_input_tokens=20_000,
            token_limit=131072,
            reserved_summary_tokens=20_000,
            buffer_tokens=13_000,
            query_source="interactive",
            consecutive_failures=0,
        )

        assert decision.should_compact is False
        assert decision.skip_reason == "below_threshold"

    def test_threshold_exceeded_triggers(self):
        policy = AutoCompactPolicy()

        decision = policy.evaluate(
            raw_input_tokens=98_072,
            token_limit=131072,
            reserved_summary_tokens=20_000,
            buffer_tokens=13_000,
            query_source="interactive",
            consecutive_failures=0,
        )

        assert decision.should_compact is True
        assert decision.trigger_reason == "threshold_exceeded"

    def test_session_memory_source_is_skipped(self):
        policy = AutoCompactPolicy()

        decision = policy.evaluate(
            raw_input_tokens=200_000,
            token_limit=131072,
            reserved_summary_tokens=20_000,
            buffer_tokens=13_000,
            query_source="session_memory",
            consecutive_failures=0,
        )

        assert decision.should_compact is False
        assert decision.skip_reason == "query_source:session_memory"

    def test_compact_source_is_skipped(self):
        policy = AutoCompactPolicy()

        decision = policy.evaluate(
            raw_input_tokens=200_000,
            token_limit=131072,
            reserved_summary_tokens=20_000,
            buffer_tokens=13_000,
            query_source="compact",
            consecutive_failures=0,
        )

        assert decision.should_compact is False
        assert decision.skip_reason == "query_source:compact"

    def test_circuit_breaker_blocks_proactive_compact(self):
        policy = AutoCompactPolicy()

        decision = policy.evaluate(
            raw_input_tokens=200_000,
            token_limit=131072,
            reserved_summary_tokens=20_000,
            buffer_tokens=13_000,
            query_source="interactive",
            consecutive_failures=3,
        )

        assert decision.should_compact is False
        assert decision.blocked_by_circuit_breaker is True
        assert decision.skip_reason == "circuit_breaker_open"

    def test_force_compact_bypasses_skip_and_circuit_breaker(self):
        policy = AutoCompactPolicy()

        decision = policy.evaluate(
            raw_input_tokens=1,
            token_limit=131072,
            reserved_summary_tokens=20_000,
            buffer_tokens=13_000,
            query_source="compact",
            consecutive_failures=99,
            force_compact=True,
        )

        assert decision.should_compact is True
        assert decision.force_compact is True
        assert decision.trigger_reason == "reactive_retry"

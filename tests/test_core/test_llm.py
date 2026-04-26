from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from core.llm import create_chat_model
from core.llm_openai_compat import OpenAICompatChatModel

MOCK_CLS = "core.llm_openai_compat.OpenAI"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for suffix in ("API_KEY", "BASE_URL", "MODEL_NAME"):
        monkeypatch.delenv(f"LLM_{suffix}", raising=False)


class TestCreateChatModel:

    @patch(MOCK_CLS)
    def test_from_config_dict(self, mock_cls):
        cfg = {"api_key": "sk-test", "base_url": "https://example.com", "model": "gpt-4"}
        model = create_chat_model(cfg)

        assert isinstance(model, OpenAICompatChatModel)
        assert model.api_key == "sk-test"
        assert model.base_url == "https://example.com"
        assert model.model == "gpt-4"
        mock_cls.assert_called_once()

    @patch(MOCK_CLS)
    def test_base_url_empty_becomes_none(self, mock_cls):
        cfg = {"api_key": "sk-x", "model": "m"}
        model = create_chat_model(cfg)

        assert model.base_url is None
        mock_cls.assert_called_once()

    @patch(MOCK_CLS)
    def test_custom_temperature_and_streaming(self, mock_cls):
        cfg = {"api_key": "sk-x", "model": "m"}
        model = create_chat_model(cfg, streaming=False, temperature=0.7)

        assert model.streaming is False
        assert model.temperature == 0.7
        mock_cls.assert_called_once()

    @patch(MOCK_CLS)
    def test_kwargs_passthrough(self, mock_cls):
        cfg = {"api_key": "sk-x", "model": "m"}
        model = create_chat_model(cfg, max_tokens=4096, timeout=30)

        assert model.max_tokens == 4096
        assert model.timeout == 30
        mock_cls.assert_called_once()


class TestValidation:

    def test_missing_api_key_raises(self):
        with pytest.raises(ValueError, match="API Key"):
            create_chat_model({"model": "m"})

    def test_missing_model_raises(self):
        with pytest.raises(ValueError, match="model"):
            create_chat_model({"api_key": "sk-x"})

    def test_none_config_and_no_env_raises(self):
        with pytest.raises(ValueError):
            create_chat_model()


class TestPayloadSerialization:

    def test_assistant_reasoning_content_is_included(self):
        payload = OpenAICompatChatModel._message_to_dict(
            AIMessage(
                content="working",
                additional_kwargs={"reasoning_content": "need one more tool step"},
            )
        )

        assert payload["role"] == "assistant"
        assert payload["reasoning_content"] == "need one more tool step"

    def test_assistant_tool_calls_are_included(self):
        payload = OpenAICompatChatModel._message_to_dict(
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"path": "a.py"},
                    "id": "call_1",
                    "type": "tool_call",
                }],
            )
        )

        assert payload["content"] is None
        assert payload["tool_calls"][0]["function"]["name"] == "read_file"
        assert payload["tool_calls"][0]["function"]["arguments"] == '{"path": "a.py"}'

    def test_tool_message_is_serialized(self):
        payload = OpenAICompatChatModel._message_to_dict(
            ToolMessage(content="done", tool_call_id="call_1")
        )

        assert payload == {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "done",
        }

    def test_bind_tools_returns_bound_model(self):
        model = OpenAICompatChatModel(
            api_key="sk-test",
            base_url="https://example.com",
            model="deepseek-v4-pro",
        )

        def sample_tool(path: str) -> str:
            return path

        bound = model.bind_tools([sample_tool], tool_choice="any", parallel_tool_calls=False)

        assert bound is not model
        assert len(bound.bound_tools) == 1
        assert bound.bound_tool_choice == "required"
        assert bound.bound_parallel_tool_calls is False

    def test_payload_merges_runtime_thinking_into_extra_body(self):
        model = OpenAICompatChatModel(
            api_key="sk-test",
            base_url="https://example.com",
            model="deepseek-v4-pro",
            extra_body={"foo": "bar"},
        )

        payload = model._build_payload(
            [HumanMessage(content="hi")],
            stream=True,
            thinking={"type": "enabled"},
        )

        assert payload["extra_body"] == {
            "foo": "bar",
            "thinking": {"type": "enabled"},
        }

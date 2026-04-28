"""OpenAI SDK-backed chat model compatible with LangChain BaseChatModel."""

from __future__ import annotations

import json
from typing import Any, Callable, Iterator, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import OpenAI
from pydantic import Field, PrivateAttr


class OpenAICompatChatModel(BaseChatModel):
    """Use the OpenAI Python SDK while keeping LangChain/LangGraph interfaces."""

    api_key: str = Field(repr=False)
    base_url: str | None = None
    model: str
    streaming: bool = True
    temperature: float | None = 0.0
    max_tokens: int | None = None
    timeout: float | None = None
    reasoning_effort: str | None = None
    model_kwargs: dict[str, Any] = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)
    bound_tools: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    bound_tool_choice: dict[str, Any] | str | None = Field(default=None, exclude=True)
    bound_parallel_tool_calls: bool | None = Field(default=None, exclude=True)

    _client: OpenAI = PrivateAttr()

    def model_post_init(self, __context: Any) -> None:
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url or None,
            timeout=self.timeout,
        )

    @property
    def _llm_type(self) -> str:
        return "openai-sdk-compat"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "streaming": self.streaming,
            "reasoning_effort": self.reasoning_effort,
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        *,
        tool_choice: dict[str, Any] | str | bool | None = None,
        parallel_tool_calls: bool | None = None,
        **kwargs: Any,
    ) -> "OpenAICompatChatModel":
        formatted_tools = [convert_to_openai_tool(tool) for tool in tools]

        normalized_tool_choice: dict[str, Any] | str | None
        if tool_choice in {None, False}:
            normalized_tool_choice = None
        elif tool_choice in {True, "any"}:
            normalized_tool_choice = "required"
        else:
            normalized_tool_choice = tool_choice

        next_kwargs = dict(self.model_kwargs)
        next_kwargs.update(kwargs)

        return self.model_copy(
            update={
                "bound_tools": formatted_tools,
                "bound_tool_choice": normalized_tool_choice,
                "bound_parallel_tool_calls": parallel_tool_calls,
                "model_kwargs": next_kwargs,
            }
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = self._build_payload(messages, stop=stop, stream=False, **kwargs)
        response = self._client.chat.completions.create(**payload)

        choice = response.choices[0]
        message = self._message_from_response(choice.message)
        llm_output = self._usage_to_dict(getattr(response, "usage", None))

        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output=llm_output,
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        payload = self._build_payload(messages, stop=stop, stream=True, **kwargs)
        response = self._client.chat.completions.create(**payload)

        for chunk in response:
            usage = self._usage_to_dict(getattr(chunk, "usage", None))
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None and usage is None:
                continue

            additional_kwargs = {}
            tool_call_chunks = []
            content = ""

            if delta is not None:
                content = delta.content or ""
                reasoning_content = _maybe_get_attr(delta, "reasoning_content")
                tool_call_chunks = self._tool_call_chunks_from_delta(delta)
                if _has_attr(delta, "reasoning_content"):
                    additional_kwargs["reasoning_content"] = reasoning_content or ""

            if not content and not additional_kwargs and not tool_call_chunks and usage is None:
                continue

            usage_metadata = _usage_to_langchain_usage(usage) if usage else None
            response_metadata = {"usage": usage} if usage else {}

            message = AIMessageChunk(
                content=content,
                additional_kwargs=additional_kwargs,
                tool_call_chunks=tool_call_chunks,
                usage_metadata=usage_metadata,
                response_metadata=response_metadata,
            )
            yield ChatGenerationChunk(message=message)

    def _build_payload(
        self,
        messages: list[BaseMessage],
        *,
        stop: list[str] | None = None,
        stream: bool,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._message_to_dict(message) for message in messages],
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}

        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if stop:
            payload["stop"] = stop
        if self.bound_tools:
            payload["tools"] = self.bound_tools
        if self.bound_tool_choice is not None:
            payload["tool_choice"] = self.bound_tool_choice
        if self.bound_parallel_tool_calls is not None:
            payload["parallel_tool_calls"] = self.bound_parallel_tool_calls

        extra_body = dict(self.extra_body)
        runtime_extra_body = kwargs.pop("extra_body", None)
        if isinstance(runtime_extra_body, dict):
            extra_body.update(runtime_extra_body)

        thinking = kwargs.pop("thinking", None)
        if thinking is not None:
            extra_body["thinking"] = thinking

        reasoning_effort = kwargs.pop("reasoning_effort", None)
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort

        payload.update(self.model_kwargs)
        payload.update(kwargs)
        if extra_body:
            payload["extra_body"] = extra_body

        return payload

    @staticmethod
    def _message_to_dict(message: BaseMessage) -> dict[str, Any]:
        if isinstance(message, SystemMessage):
            return {"role": "system", "content": message.content}
        if isinstance(message, HumanMessage):
            return {"role": "user", "content": message.content}
        if isinstance(message, ToolMessage):
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content,
            }
        if isinstance(message, AIMessage):
            data: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or None,
            }
            if "reasoning_content" in (message.additional_kwargs or {}):
                data["reasoning_content"] = (message.additional_kwargs or {}).get("reasoning_content", "")
            tool_calls = OpenAICompatChatModel._tool_calls_to_openai(message.tool_calls)
            if tool_calls:
                data["tool_calls"] = tool_calls
                if not message.content:
                    data["content"] = None
            return data
        if isinstance(message, ChatMessage):
            return {"role": message.role, "content": message.content}
        raise TypeError(f"Unsupported message type: {type(message)!r}")

    @staticmethod
    def _tool_calls_to_openai(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for tool_call in tool_calls or []:
            args = tool_call.get("args", {})
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            converted.append({
                "id": tool_call.get("id"),
                "type": "function",
                "function": {
                    "name": tool_call.get("name"),
                    "arguments": args,
                },
            })
        return converted

    @staticmethod
    def _tool_calls_from_message(tool_calls: Any) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for tool_call in tool_calls or []:
            args_raw = tool_call.function.arguments if tool_call.function else "{}"
            try:
                args = json.loads(args_raw)
            except Exception:
                args = args_raw
            converted.append({
                "name": tool_call.function.name if tool_call.function else "",
                "args": args,
                "id": tool_call.id,
                "type": "tool_call",
            })
        return converted

    @staticmethod
    def _tool_call_chunks_from_delta(delta: Any) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for tool_call in getattr(delta, "tool_calls", None) or []:
            chunk: dict[str, Any] = {
                "index": getattr(tool_call, "index", 0) or 0,
            }
            if getattr(tool_call, "id", None):
                chunk["id"] = tool_call.id
            function = getattr(tool_call, "function", None)
            if function is not None:
                if getattr(function, "name", None):
                    chunk["name"] = function.name
                if getattr(function, "arguments", None):
                    chunk["args"] = function.arguments
            chunks.append(chunk)
        return chunks

    @staticmethod
    def _message_from_response(message: Any) -> AIMessage:
        reasoning_content = _maybe_get_attr(message, "reasoning_content")
        additional_kwargs = {}
        if _has_attr(message, "reasoning_content"):
            additional_kwargs["reasoning_content"] = reasoning_content or ""

        return AIMessage(
            content=message.content or "",
            tool_calls=OpenAICompatChatModel._tool_calls_from_message(getattr(message, "tool_calls", None)),
            additional_kwargs=additional_kwargs,
        )

    @staticmethod
    def _usage_to_dict(usage: Any) -> dict[str, Any] | None:
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        if isinstance(usage, dict):
            return usage
        return None


def _maybe_get_attr(obj: Any, name: str) -> Any:
    value = getattr(obj, name, None)
    if value is not None:
        return value
    extra = getattr(obj, "model_extra", None)
    if isinstance(extra, dict):
        return extra.get(name)
    return None


def _has_attr(obj: Any, name: str) -> bool:
    if hasattr(obj, name):
        return True
    extra = getattr(obj, "model_extra", None)
    return isinstance(extra, dict) and name in extra


def _usage_to_langchain_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "output_tokens": int(usage.get("completion_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }

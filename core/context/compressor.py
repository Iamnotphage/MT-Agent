"""
上下文压缩器 — 在 auto compact policy 触发后生成结构化摘要。

触发判断已经由外部 policy 层负责，这里只保留：
  1. 找到分割点
  2. 将旧消息总结为摘要
  3. 返回可写回 state 的压缩结果
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from core.context.budget import estimate_message_tokens
from core.context.message_invariants import find_compaction_working_start, find_safe_split_index
from prompts.compression_prompt import COMPACT_SYSTEM_PROMPT

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


class ContextCompressor:
    """上下文压缩器。"""

    def __init__(
        self,
        llm: BaseChatModel,
        *,
        token_limit: int = 65536,
        threshold: float = 0.50,
        preserve_ratio: float = 0.30,
        preserve_min_tokens: int = 10_000,
        preserve_max_tokens: int = 40_000,
    ) -> None:
        self._llm = llm
        self._token_limit = token_limit
        self._threshold = threshold
        self._preserve_ratio = preserve_ratio
        self._preserve_min_tokens = preserve_min_tokens
        self._preserve_max_tokens = preserve_max_tokens

    def should_compress(self, last_input_tokens: int) -> bool:
        """兼容旧调用方的比例阈值判断。"""
        if last_input_tokens <= 0:
            return False
        return last_input_tokens >= self._token_limit * self._threshold

    def compress(self, messages: list[BaseMessage], *, reason: str = "auto") -> CompressResult | None:
        """执行压缩。"""
        if len(messages) < 4:
            return None

        split_idx = self._find_split_point(messages)
        if split_idx <= 0:
            return None

        working_start = find_compaction_working_start(messages)
        if split_idx <= working_start:
            return None

        preserved_prefix = messages[:working_start]
        old_messages = messages[working_start:split_idx]
        logger.info(
            "Compressing %d/%d messages (split at index %d)",
            len(old_messages), len(messages), split_idx,
        )

        summary_text = self._generate_summary(old_messages)
        if not summary_text:
            logger.warning("Compression LLM returned empty summary, skipping")
            return None

        remove_ids = [msg.id for msg in old_messages if msg.id]
        pre_tokens = estimate_message_tokens(old_messages)
        summary_msg = self.build_summary_message(summary_text)
        boundary_msg = self.build_compact_boundary_message(
            pre_tokens=pre_tokens,
            post_tokens=0,
            reason=reason,
        )
        compressed_messages = [*preserved_prefix, boundary_msg, summary_msg, *messages[split_idx:]]
        post_tokens = estimate_message_tokens(compressed_messages)
        boundary_msg = self.build_compact_boundary_message(
            pre_tokens=pre_tokens,
            post_tokens=post_tokens,
            reason=reason,
        )
        compressed_messages = [*preserved_prefix, boundary_msg, summary_msg, *messages[split_idx:]]

        return CompressResult(
            remove_message_ids=remove_ids,
            boundary_message=boundary_msg,
            summary_message=summary_msg,
            summary_text=summary_text,
            compressed_messages=compressed_messages,
            removed_count=len(old_messages),
            kept_count=len(messages) - split_idx + len(preserved_prefix),
            split_index=split_idx,
            pre_tokens=pre_tokens,
            post_tokens=post_tokens,
            reason=reason,
        )

    @staticmethod
    def build_summary_message(summary_text: str) -> HumanMessage:
        """将压缩摘要包装成注入历史的 HumanMessage。"""
        return HumanMessage(
            content=(
                "<conversation_history_summary>\n"
                f"{summary_text}\n"
                "</conversation_history_summary>"
            ),
        )

    @staticmethod
    def build_compact_boundary_message(
        *,
        pre_tokens: int,
        post_tokens: int,
        reason: str,
    ) -> HumanMessage:
        return HumanMessage(
            content=(
                f'<compact_boundary pre_tokens="{pre_tokens}" '
                f'post_tokens="{post_tokens}" reason="{reason}" />'
            ),
        )

    def _find_split_point(self, messages: list[BaseMessage]) -> int:
        split_idx = find_safe_split_index(
            messages,
            min_keep_tokens=self._preserve_min_tokens,
            max_keep_tokens=self._preserve_max_tokens,
        )
        return split_idx or 0

    def _generate_summary(self, old_messages: list[BaseMessage]) -> str:
        conversation_text = self._serialize_messages(old_messages)

        # 限制输入大小，避免压缩本身超限
        from core.utils.tokens import estimate_tokens
        input_tokens = estimate_tokens(conversation_text)

        # 如果输入太大（超过 20k tokens），使用简单摘要而不是调用 LLM
        if input_tokens > 20000:
            logger.warning(
                "Conversation text too large (%d tokens), using simple summary instead of LLM compression",
                input_tokens
            )
            return (
                f"Previous conversation history ({len(old_messages)} messages) "
                "has been compressed due to context length limits. "
                "Key information may have been preserved in recent messages."
            )

        compress_messages = [
            SystemMessage(content=COMPACT_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Create a detailed compact summary of the following conversation history. "
                    "Follow the required <analysis> and <summary> structure exactly.\n\n"
                    f"{conversation_text}"
                ),
            ),
        ]

        try:
            response = self._llm.invoke(compress_messages)
            raw_response = response.content.strip() if response.content else ""
            summary = _extract_compact_summary(raw_response)

            # 检查摘要大小，如果太大则截断
            summary_tokens = estimate_tokens(summary)
            if summary_tokens > 5000:
                logger.warning("Summary too large (%d tokens), truncating", summary_tokens)
                # 截断到约 5000 tokens (约 20000 字符)
                summary = summary[:20000] + "\n\n[Summary truncated due to length]"

            return summary
        except Exception as e:
            logger.error("Compression LLM call failed: %s", e)
            return ""

    @staticmethod
    def _serialize_messages(messages: list[BaseMessage]) -> str:
        parts: list[str] = []
        for msg in messages:
            role = msg.type
            content = msg.content or ""

            if isinstance(msg, AIMessage) and msg.tool_calls:
                tool_names = [tc["name"] for tc in msg.tool_calls]
                parts.append(f"[{role}] (called tools: {', '.join(tool_names)})")
                if content:
                    parts.append(f"  {_truncate(content, 200)}")  # 减少到 200
            elif isinstance(msg, ToolMessage):
                parts.append(f"[tool:{msg.name}] {_truncate(content, 150)}")  # 减少到 150
            else:
                parts.append(f"[{role}] {_truncate(content, 300)}")  # 减少到 300

        return "\n".join(parts)


class CompressResult:
    """压缩结果。"""

    __slots__ = (
        "remove_message_ids",
        "boundary_message",
        "summary_message",
        "summary_text",
        "compressed_messages",
        "removed_count",
        "kept_count",
        "split_index",
        "pre_tokens",
        "post_tokens",
        "reason",
    )

    def __init__(
        self,
        remove_message_ids: list[str],
        boundary_message: HumanMessage,
        summary_message: HumanMessage,
        summary_text: str,
        compressed_messages: list[BaseMessage],
        removed_count: int,
        kept_count: int,
        split_index: int,
        pre_tokens: int,
        post_tokens: int,
        reason: str,
    ) -> None:
        self.remove_message_ids = remove_message_ids
        self.boundary_message = boundary_message
        self.summary_message = summary_message
        self.summary_text = summary_text
        self.compressed_messages = compressed_messages
        self.removed_count = removed_count
        self.kept_count = kept_count
        self.split_index = split_index
        self.pre_tokens = pre_tokens
        self.post_tokens = post_tokens
        self.reason = reason


def _truncate(text: str | list, max_len: int = 500) -> str:
    """截断文本。"""
    if isinstance(text, list):
        text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... ({len(text)} chars total)"


def _extract_compact_summary(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"<summary>\s*(.*?)\s*</summary>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

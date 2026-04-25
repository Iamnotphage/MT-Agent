"""Long-term memory management for global CONTEXT.md."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MEMORY_SECTION_HEADER = "## Agent Memories"


def parse_memories(content: str) -> list[str]:
    """Parse memory items from a global CONTEXT.md payload."""
    if MEMORY_SECTION_HEADER not in content:
        return []
    idx = content.index(MEMORY_SECTION_HEADER)
    section_content = content[idx + len(MEMORY_SECTION_HEADER):]
    next_section = re.search(r"\n## ", section_content)
    if next_section:
        section_content = section_content[:next_section.start()]
    memories = []
    for line in section_content.splitlines():
        line = line.strip()
        if line.startswith("- "):
            memories.append(line[2:].strip())
    return memories


class MemoryManager:
    """Manage agent memories stored in the global CONTEXT.md."""

    def __init__(
        self,
        global_context_path: Path,
        on_update: Callable[[str], None] | None = None,
    ) -> None:
        self._global_context_path = global_context_path
        self._on_update = on_update

    def get_memories(self, content: str | None = None) -> list[str]:
        """Parse memories from provided content, or from the current file."""
        if content is None:
            content = self._read_file_safe(self._global_context_path)
        return parse_memories(content)

    def save_memory(self, fact: str) -> str | None:
        """Persist a fact and return updated global content, or None if ignored."""
        sanitized = re.sub(r"[\r\n]+", " ", fact).strip().lstrip("- ")
        if not sanitized:
            return None

        self._global_context_path.parent.mkdir(parents=True, exist_ok=True)
        content = self._read_file_safe(self._global_context_path)
        new_content = self._append_memory_to_content(content, sanitized)
        self._global_context_path.write_text(new_content, encoding="utf-8")
        self._notify_updated(new_content)
        logger.info("Saved memory: %s", sanitized[:60])
        return new_content

    def remove_memory(self, index: int) -> tuple[bool, str | None]:
        """Remove a memory by index and return updated content when successful."""
        content = self._read_file_safe(self._global_context_path)
        memories = parse_memories(content)
        if index < 0 or index >= len(memories):
            return False, None

        memories.pop(index)
        new_content = self._rewrite_memories(content, memories)
        self._global_context_path.write_text(new_content, encoding="utf-8")
        self._notify_updated(new_content)
        return True, new_content

    def _notify_updated(self, content: str) -> None:
        if self._on_update is None:
            return
        try:
            self._on_update(content)
        except Exception as e:
            logger.warning("Failed to propagate memory update: %s", e)

    @staticmethod
    def _append_memory_to_content(content: str, fact: str) -> str:
        new_item = f"- {fact}"
        if MEMORY_SECTION_HEADER not in content:
            separator = "\n\n" if content.strip() else ""
            return content.rstrip() + separator + f"{MEMORY_SECTION_HEADER}\n\n{new_item}\n"
        idx = content.index(MEMORY_SECTION_HEADER)
        after_header = content[idx + len(MEMORY_SECTION_HEADER):]
        next_section = re.search(r"\n## ", after_header)
        if next_section:
            insert_pos = idx + len(MEMORY_SECTION_HEADER) + next_section.start()
            return content[:insert_pos].rstrip() + "\n" + new_item + "\n" + content[insert_pos:]
        return content.rstrip() + "\n" + new_item + "\n"

    @staticmethod
    def _rewrite_memories(content: str, memories: list[str]) -> str:
        if MEMORY_SECTION_HEADER not in content:
            return content
        idx = content.index(MEMORY_SECTION_HEADER)
        after_header = content[idx + len(MEMORY_SECTION_HEADER):]
        next_section = re.search(r"\n## ", after_header)
        before = content[: idx + len(MEMORY_SECTION_HEADER)]
        after = after_header[next_section.start():] if next_section else ""
        body = "\n\n" + "\n".join(f"- {m}" for m in memories) + ("\n" if memories else "\n")
        return before + body + after

    @staticmethod
    def _read_file_safe(filepath: Path) -> str:
        try:
            if filepath.is_file():
                return filepath.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("Failed to read memory file %s: %s", filepath, e)
        return ""

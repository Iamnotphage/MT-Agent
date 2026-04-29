"""Session recorder and resume helpers."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from core.context.compressor import ContextCompressor
from core.session.artifacts import (
    get_history_dir,
    get_session_artifact_dir,
    get_session_memory_dir,
    get_tool_result_path,
    resolve_session_relative_artifact,
)
from core.session.schema import (
    RECORD_COMPACT_BOUNDARY,
    RECORD_SESSION_END,
    RECORD_SESSION_MEMORY_UPDATE,
    RECORD_SESSION_START,
    get_record_type,
    is_renderable_record,
    is_transcript_message_record,
    make_session_end_record,
    make_session_start_record,
    normalize_compact_boundary_record,
    normalize_session_memory_update_record,
    normalize_transcript_record,
)
from core.session.stats import SessionStats
from core.utils.tokens import estimate_tokens

logger = logging.getLogger(__name__)


def format_relative_time(timestamp_ms: int) -> str:
    """将毫秒时间戳转为相对时间描述（如 '2 hours ago'）。"""
    if not timestamp_ms:
        return "unknown"
    diff = time.time() - timestamp_ms / 1000
    if diff < 60:
        return "just now"
    if diff < 3600:
        m = int(diff / 60)
        return f"{m} min{'s' if m > 1 else ''} ago"
    if diff < 86400:
        h = int(diff / 3600)
        return f"{h} hour{'s' if h > 1 else ''} ago"
    d = int(diff / 86400)
    if d == 1:
        return "1 day ago"
    return f"{d} days ago"


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小。"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def _is_compact_summary_transcript_record(record: dict[str, Any]) -> bool:
    if not is_transcript_message_record(record):
        return False
    content = str(record.get("content", "") or "")
    return content.startswith("<conversation_history_summary>")


def _build_session_memory_summary_message(summary_text: str, *, summary_path: str) -> HumanMessage:
    return HumanMessage(
        content=(
            f'<session_memory_summary path="{summary_path}">\n'
            f"{summary_text}\n"
            "</session_memory_summary>"
        )
    )


class SessionRecorder:
    """会话录制与历史管理。"""

    def __init__(self, working_directory: str, config: dict[str, Any]) -> None:
        self._working_dir = Path(working_directory).resolve()
        self._config = config

        self.stats = SessionStats()
        self._records: list[dict] = []
        self._resumed_from: Path | None = None
        self._thread_id: str = ""

    def record(self, record: dict) -> None:
        """记录一条会话消息（追加到内存缓冲区）。"""
        if is_transcript_message_record(record):
            record = normalize_transcript_record(record)
        if "timestamp" not in record:
            record["timestamp"] = int(time.time() * 1000)
        self._records.append(record)

    def set_thread_id(self, thread_id: str) -> None:
        """更新当前活跃的 LangGraph thread_id。"""
        self._thread_id = thread_id

    def resume_from(self, filepath: Path) -> None:
        """绑定被恢复的 session 文件，并沿用其 session_id/thread_id。"""
        self._resumed_from = filepath
        session_meta = self._read_session_metadata(filepath)
        session_id = str(session_meta.get("session_id", "") or "").strip()
        thread_id = str(session_meta.get("thread_id", "") or "").strip()
        if session_id:
            self.stats.session_id = session_id
        if thread_id:
            self._thread_id = thread_id
        logger.info(
            "resume_from: bound session file=%s session_id=%s thread_id=%s",
            filepath,
            self.stats.session_id,
            self._thread_id,
        )

    def flush(self) -> Path | None:
        """将会话记录写入磁盘 JSONL 文件。"""
        if not self._records:
            return None

        all_records: list[dict] = []
        if self._resumed_from and self._resumed_from.is_file():
            all_records.extend(self.load_raw_session(self._resumed_from))
        all_records.extend(self._records)

        start_record = make_session_start_record(
            session_id=self.stats.session_id,
            thread_id=self._thread_id,
            project=str(self._working_dir),
            model=self.stats.model,
            branch=self._get_git_branch(),
            timestamp=int(self.stats.start_time * 1000),
        )

        end_record = make_session_end_record(
            session_id=self.stats.session_id,
            thread_id=self._thread_id,
            stats=self.stats.to_dict(),
            timestamp=int(time.time() * 1000),
        )

        history_dir = self._get_history_dir()
        history_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        sid = self.stats.session_id
        filepath = history_dir / f"session-{ts}-{sid}.jsonl"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json.dumps(start_record, ensure_ascii=False) + "\n")
            for rec in all_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.write(json.dumps(end_record, ensure_ascii=False) + "\n")

        if self._resumed_from and self._resumed_from.is_file() and self._resumed_from != filepath:
            try:
                self._resumed_from.unlink()
                logger.info("Deleted old session file: %s", self._resumed_from)
            except OSError as e:
                logger.warning("Failed to delete old session file: %s", e)

        logger.info("Session saved to %s (%d records)", filepath, len(self._records))
        return filepath

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出当前项目的所有历史会话（按时间倒序）。"""
        history_dir = self._get_history_dir()
        if not history_dir.is_dir():
            return []

        sessions: list[dict[str, Any]] = []
        for filepath in sorted(
            history_dir.glob("session-*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                info = self._parse_session_file(filepath)
                if info:
                    sessions.append(info)
            except Exception as e:
                logger.warning("Skipping corrupt session file %s: %s", filepath, e)
        return sessions

    def load_session(self, filepath: Path) -> list[dict]:
        """加载指定会话文件的渲染记录（不含 session_start/session_end）。"""
        return [record for record in self.load_raw_session(filepath) if is_renderable_record(record)]

    def load_raw_session(self, filepath: Path) -> list[dict]:
        """加载指定会话文件中的全部业务记录（不含 session_start/session_end）。"""
        records: list[dict] = []
        for line in filepath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                rtype = get_record_type(record)
                if rtype not in {RECORD_SESSION_START, RECORD_SESSION_END}:
                    if is_transcript_message_record(record):
                        record = normalize_transcript_record(record)
                    elif rtype == RECORD_SESSION_MEMORY_UPDATE:
                        record = normalize_session_memory_update_record(record)
                    records.append(record)
            except json.JSONDecodeError:
                continue
        return records

    def build_resume_messages(self, filepath: Path) -> list[BaseMessage]:
        """从会话文件重建 resume 所需消息，只保留最后一次压缩摘要及其后的消息。"""
        records = self.load_raw_session(filepath)
        session_meta = self._read_session_metadata(filepath)
        source_session_id = str(session_meta.get("session_id", "") or "").strip() or self.stats.session_id
        logger.info(
            "build_resume_messages: filepath=%s record_count=%d source_session_id=%s",
            filepath,
            len(records),
            source_session_id,
        )

        boundary_record: dict[str, Any] | None = None
        last_boundary_idx = -1
        session_memory_record: dict[str, Any] | None = None
        for idx, record in enumerate(records):
            rtype = get_record_type(record)
            if rtype == RECORD_COMPACT_BOUNDARY:
                last_boundary_idx = idx
                boundary_record = normalize_compact_boundary_record(record)
            elif rtype == RECORD_SESSION_MEMORY_UPDATE:
                session_memory_record = normalize_session_memory_update_record(record)

        resumed: list[BaseMessage] = []
        if boundary_record:
            resumed.append(ContextCompressor.build_compact_boundary_message(
                pre_tokens=int(boundary_record.get("pre_tokens", 0) or 0),
                post_tokens=int(boundary_record.get("post_tokens", 0) or 0),
                reason=str(boundary_record.get("reason", "auto") or "auto"),
            ))
            if str(boundary_record.get("reason", "")) == "session_memory" and session_memory_record:
                session_summary_text = self._load_session_memory_summary_text(
                    session_memory_record,
                    session_id=source_session_id,
                )
                if session_summary_text:
                    resumed.append(_build_session_memory_summary_message(
                        session_summary_text,
                        summary_path=str(session_memory_record.get("summary_path", "")),
                    ))

        start_idx = last_boundary_idx + 1 if last_boundary_idx >= 0 else 0
        tail_records = records[start_idx:]

        # For non-session-memory full compact, restore summary from persisted transcript
        full_compact_summary_idx = -1
        if boundary_record and str(boundary_record.get("reason", "")) != "session_memory":
            for idx, r in enumerate(tail_records):
                if _is_compact_summary_transcript_record(r):
                    resumed.append(HumanMessage(content=str(r.get("content", ""))))
                    full_compact_summary_idx = idx
                    break

        transcript_records = [
            r for i, r in enumerate(tail_records)
            if is_transcript_message_record(r) and i != full_compact_summary_idx
        ]
        resumed.extend(self._build_messages_from_transcript(transcript_records))
        logger.info(
            "build_resume_messages: filepath=%s start_idx=%d transcript_records=%d resumed_messages=%d",
            filepath,
            start_idx,
            len(transcript_records),
            len(resumed),
        )
        return resumed

    def estimate_messages_tokens(self, messages: list[BaseMessage]) -> int:
        """估算一组消息的 token 数，用于 resume 后上下文占比展示。"""
        total = 0
        for msg in messages:
            role = getattr(msg, "type", "")
            content = msg.content
            if isinstance(content, list):
                content = str(content)
            total += estimate_tokens(f"[{role}] {content}")
        return total

    @staticmethod
    def _build_messages_from_transcript(records: list[dict]) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        for record in records:
            record = normalize_transcript_record(record)
            role = record.get("role")
            content = record.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                additional_kwargs: dict[str, Any] = {}
                reasoning_content = record.get("reasoning_content")
                if reasoning_content is not None:
                    additional_kwargs["reasoning_content"] = reasoning_content
                messages.append(AIMessage(
                    content=content,
                    tool_calls=record.get("tool_calls") or [],
                    additional_kwargs=additional_kwargs,
                ))
            elif role == "tool":
                kwargs: dict[str, Any] = {
                    "content": content,
                    "tool_call_id": record.get("tool_call_id", ""),
                }
                name = record.get("name")
                if name:
                    kwargs["name"] = name
                messages.append(ToolMessage(**kwargs))
        return messages

    @staticmethod
    def _parse_session_file(filepath: Path) -> dict[str, Any] | None:
        session_meta = SessionRecorder._read_session_metadata(filepath)
        session_id = str(session_meta.get("session_id", "") or "")
        thread_id = str(session_meta.get("thread_id", "") or "")
        model = str(session_meta.get("model", "") or "")
        branch = str(session_meta.get("branch", "") or "")
        timestamp = int(session_meta.get("timestamp", 0) or 0)
        records = list(session_meta.get("records", []) or [])

        transcript_records = [normalize_transcript_record(r) for r in records if is_transcript_message_record(r)]
        first_user_msg = ""
        message_count = 0
        for record in transcript_records:
            role = record.get("role")
            if role in {"user", "assistant"}:
                message_count += 1
            if role == "user" and not first_user_msg:
                first_user_msg = str(record.get("content", ""))[:80]

        if not first_user_msg:
            return None

        try:
            file_size = filepath.stat().st_size
        except OSError:
            file_size = 0

        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "model": model,
            "branch": branch,
            "timestamp": timestamp,
            "first_user_message": first_user_msg,
            "message_count": message_count,
            "file_size": file_size,
            "filepath": filepath,
        }

    @staticmethod
    def _read_session_metadata(filepath: Path) -> dict[str, Any]:
        session_id = ""
        thread_id = ""
        model = ""
        branch = ""
        timestamp = 0
        records: list[dict[str, Any]] = []

        for line in filepath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = record.get("type", "")
            if rtype == RECORD_SESSION_START:
                session_id = record.get("sessionId", "")
                thread_id = record.get("threadId", "")
                model = record.get("model", "")
                branch = record.get("branch", "")
                timestamp = record.get("timestamp", 0)
            else:
                records.append(record)

        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "model": model,
            "branch": branch,
            "timestamp": timestamp,
            "records": records,
        }

    def _get_history_dir(self) -> Path:
        """会话历史目录: ~/.mtagent/history/{projectHash}/"""
        return get_history_dir(str(self._working_dir), self._config)

    def get_artifact_dir(self) -> Path:
        """当前 session 的 artifact 根目录。"""
        return get_session_artifact_dir(
            str(self._working_dir),
            self._config,
            self.stats.session_id,
        )

    def get_tool_result_artifact_path(self, tool_call_id: str, suffix: str = ".txt") -> Path:
        """当前 session 下某个工具结果的 artifact 路径。"""
        return get_tool_result_path(
            str(self._working_dir),
            self._config,
            self.stats.session_id,
            tool_call_id,
            suffix=suffix,
        )

    def get_session_memory_artifact_dir(self) -> Path:
        """当前 session 的 session-memory 目录。"""
        return get_session_memory_dir(
            str(self._working_dir),
            self._config,
            self.stats.session_id,
        )

    def _load_session_memory_summary_text(self, record: dict[str, Any], *, session_id: str) -> str:
        summary_path = str(record.get("summary_path", "") or "")
        if not summary_path or not session_id:
            logger.info(
                "load_session_memory_summary: skipped summary_path=%s session_id=%s",
                summary_path,
                session_id,
            )
            return ""
        path = resolve_session_relative_artifact(
            str(self._working_dir),
            self._config,
            session_id,
            summary_path,
        )
        if not path.exists():
            logger.info(
                "load_session_memory_summary: missing path=%s session_id=%s",
                path,
                session_id,
            )
            return ""
        text = path.read_text(encoding="utf-8").strip()
        logger.info(
            "load_session_memory_summary: loaded path=%s chars=%d session_id=%s",
            path,
            len(text),
            session_id,
        )
        return text

    def get_checkpoint_path(self) -> Path:
        """当前项目的 LangGraph checkpoint SQLite 文件路径。"""
        history_dir = self._get_history_dir()
        history_dir.mkdir(parents=True, exist_ok=True)
        return history_dir / "checkpoints.sqlite"

    def _get_git_branch(self) -> str:
        """获取当前 git 分支名。"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self._working_dir,
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

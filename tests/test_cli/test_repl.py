from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from cli.repl import Repl
from core.event_bus import EventBus


def _make_runtime(tmp_path: Path, *, last_input_tokens: int, last_effective_context_limit: int):
    workspace = tmp_path / "project"
    workspace.mkdir(parents=True, exist_ok=True)
    stats = SimpleNamespace(
        model="deepseek-v4-flash",
        last_input_tokens=last_input_tokens,
        last_effective_context_limit=last_effective_context_limit,
    )
    session = SimpleNamespace(stats=stats, set_thread_id=lambda _thread_id: None)
    context_manager = SimpleNamespace(_working_dir=workspace)
    return SimpleNamespace(
        session=session,
        context_manager=context_manager,
        event_bus=EventBus(),
    )


def test_context_status_uses_effective_context_limit(tmp_path):
    runtime = _make_runtime(
        tmp_path,
        last_input_tokens=10_000,
        last_effective_context_limit=20_000,
    )
    repl = Repl(Console(record=True, width=100), runtime)

    status = repl._context_status()

    assert "50% left" in status
    assert str(runtime.context_manager._working_dir) in status


def test_context_status_falls_back_to_token_limit_when_effective_limit_missing(tmp_path):
    runtime = _make_runtime(
        tmp_path,
        last_input_tokens=10_000,
        last_effective_context_limit=0,
    )
    repl = Repl(Console(record=True, width=100), runtime)

    status = repl._context_status()

    assert "99% left" in status

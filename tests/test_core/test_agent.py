from unittest.mock import patch

from config.settings import CONTEXT as CONTEXT_CONFIG


def test_runtime_omits_session_memory_when_disabled(tmp_path):
    """enable_session_memory_compact=False 时不创建 session memory 组件。"""
    with patch.dict(CONTEXT_CONFIG, {"enable_session_memory_compact": False}):
        # 需要 mock 掉外部依赖才能实例化 runtime
        from core.agent import create_agent_runtime

        with patch("core.agent.load_llm_config", return_value={
            "api_key": "test", "base_url": "http://localhost", "model": "test-model",
        }), patch("core.agent.create_chat_model"), patch("core.agent.build_agent_graph"):
            runtime = create_agent_runtime(workspace=str(tmp_path))

    assert runtime.session_memory_manager is None
    assert runtime.session_memory_worker is None


def test_runtime_creates_session_memory_when_enabled(tmp_path):
    """enable_session_memory_compact=True 时创建 session memory 组件。"""
    with patch.dict(CONTEXT_CONFIG, {"enable_session_memory_compact": True}):
        from core.agent import create_agent_runtime

        with patch("core.agent.load_llm_config", return_value={
            "api_key": "test", "base_url": "http://localhost", "model": "test-model",
        }), patch("core.agent.create_chat_model"), patch("core.agent.build_agent_graph"):
            runtime = create_agent_runtime(workspace=str(tmp_path))

    assert runtime.session_memory_manager is not None
    assert runtime.session_memory_worker is not None

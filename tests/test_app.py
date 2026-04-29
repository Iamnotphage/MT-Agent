from datetime import datetime

from app import build_default_log_file_path


def test_build_default_log_file_path_uses_timestamp_and_logs_dir(tmp_path):
    path = build_default_log_file_path(
        base_dir=str(tmp_path),
        now=datetime(2026, 4, 28, 18, 45, 12),
    )

    assert path.endswith("logs/mt-agent-20260428-184512.log")

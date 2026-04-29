from pathlib import Path

import pytest
from langchain_core.tools.base import ToolException

from tools.files.edit_file import EditFileTool
from tools.files.glob import GlobTool
from tools.files.grep import GrepTool
from tools.files.ls import LsTool
from tools.files.write_file import WriteFileTool
from tools.workspace_paths import ensure_within_workspace, resolve_workspace_path


def test_resolve_workspace_path_allows_relative_child(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "src" / "app.py"
    target.parent.mkdir()
    target.write_text("print('ok')\n")

    resolved = resolve_workspace_path(workspace, "src/app.py")

    assert resolved == target.resolve()


def test_resolve_workspace_path_blocks_traversal(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    with pytest.raises(ToolException, match="越界"):
        resolve_workspace_path(workspace, "../../etc/passwd")


def test_resolve_workspace_path_blocks_absolute_outside_workspace(tmp_path):
    workspace = tmp_path / "repo"
    outside = tmp_path / "outside.txt"
    workspace.mkdir()
    outside.write_text("secret\n")

    with pytest.raises(ToolException, match="越界"):
        resolve_workspace_path(workspace, str(outside))


def test_resolve_workspace_path_blocks_sibling_prefix_escape(tmp_path):
    workspace = tmp_path / "repo"
    sibling = tmp_path / "repo2"
    workspace.mkdir()
    sibling.mkdir()
    victim = sibling / "secret.txt"
    victim.write_text("secret\n")

    with pytest.raises(ToolException, match="越界"):
        resolve_workspace_path(workspace, str(victim))


def test_ensure_within_workspace_accepts_workspace_root(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    assert ensure_within_workspace(workspace.resolve(), workspace.resolve()) == workspace.resolve()


# ── Multi-tool regression: absolute-path and sibling-prefix escapes ──


def test_write_file_blocks_absolute_outside_workspace(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    tool = WriteFileTool(workspace=workspace)

    with pytest.raises(ToolException, match="workspace|工作区|越界"):
        tool._run(file_path=str(outside), content="secret\n")


def test_edit_file_blocks_sibling_prefix_escape(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    sibling = tmp_path / "repo2"
    sibling.mkdir()
    victim = sibling / "victim.txt"
    victim.write_text("hello\n")
    tool = EditFileTool(workspace=workspace)

    with pytest.raises(ToolException, match="workspace|工作区|越界"):
        tool._run(file_path=str(victim), old_string="hello", new_string="bye")


def test_ls_blocks_absolute_outside_workspace(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    tool = LsTool(workspace=workspace)

    with pytest.raises(ToolException, match="workspace|工作区|越界"):
        tool._run(dir_path=str(outside))


def test_glob_blocks_absolute_outside_workspace(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    tool = GlobTool(workspace=workspace)

    with pytest.raises(ToolException, match="workspace|工作区|越界"):
        tool._run(pattern="*.py", path=str(outside))


def test_grep_blocks_absolute_outside_workspace(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    tool = GrepTool(workspace=workspace)

    with pytest.raises(ToolException, match="workspace|工作区|越界"):
        tool._run(pattern="secret", path=str(outside))

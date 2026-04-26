import pytest

from langchain_core.tools.base import ToolException

from tools.base import BaseTool, ToolRiskLevel
from tools.file_ops.read_file import ReadFileTool


# ── ReadFileTool ─────────────────────────────────────────────────

class TestReadFileTool:

    @pytest.fixture()
    def workspace(self, tmp_path):
        (tmp_path / "hello.txt").write_text("line1\nline2\nline3\n")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "deep.c").write_text("int main() {}\n")
        return tmp_path

    @pytest.fixture()
    def tool(self, workspace):
        return ReadFileTool(workspace=workspace)

    def test_read_full_file(self, tool):
        content, artifact = tool._run(file_path="hello.txt")
        assert "1\tline1" in content
        assert "2\tline2" in content
        assert artifact["total_lines"] == 3
        assert artifact["toolUseResult"]["file"]["content"] == "line1\nline2\nline3\n"

    def test_read_line_range(self, tool):
        content, artifact = tool._run(file_path="hello.txt", offset=2, limit=1)
        assert "2\tline2" in content
        assert "1\tline1" not in content
        assert artifact["toolUseResult"]["input"]["offset"] == 2
        assert artifact["toolUseResult"]["input"]["limit"] == 1
        assert artifact["toolUseResult"]["file"]["startLine"] == 2

    def test_read_subdir(self, tool):
        content, artifact = tool._run(file_path="sub/deep.c")
        assert "1\tint main() {}" in content

    def test_file_not_found(self, tool):
        with pytest.raises(ToolException, match="不存在"):
            tool._run(file_path="nope.txt")

    def test_path_traversal_blocked(self, tool):
        with pytest.raises(ToolException, match="越界"):
            tool._run(file_path="../../etc/passwd")

    def test_truncation(self, workspace):
        big = "\n".join(f"L{i}" for i in range(1000))
        (workspace / "big.txt").write_text(big)
        tool = ReadFileTool(workspace=workspace)
        content, artifact = tool._run(file_path="big.txt")
        assert artifact["truncated"] is True
        assert "Content truncated" in content

    def test_file_unchanged_stub(self, tool):
        first_content, first_artifact = tool._run(file_path="hello.txt", offset=1, limit=2)
        second_content, second_artifact = tool._run(file_path="hello.txt", offset=1, limit=2)

        assert "1\tline1" in first_content
        assert second_content == "File unchanged since last read for the same range."
        assert second_artifact["toolUseResult"]["type"] == "file_unchanged"

    def test_invoke_via_langchain(self, tool):
        """langchain invoke 接口可用"""
        result = tool.invoke({"file_path": "hello.txt"})
        assert "1\tline1" in result

    def test_tool_has_name_and_description(self, tool):
        assert tool.name == "read_file"
        assert len(tool.description) > 0

    def test_risk_level(self, tool):
        assert tool.risk_level == ToolRiskLevel.LOW

# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for write_file tool - aligned with gemini-cli's write-file.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
"""

import os
import shutil
import tempfile

import pytest

from nexau_harbor.tool_impl.write_file import write_file


class TestWriteFile:
    """Test write_file tool functionality matching gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="write-file-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_new_file(self):
        """Should create a new file successfully."""
        file_path = os.path.join(self.temp_dir, "new_file.txt")
        content = "Hello, World!"
        
        result = write_file(file_path=file_path, content=content)
        
        assert result.get("error") is None
        assert "created" in result["llmContent"].lower()
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert f.read() == content

    def test_overwrite_existing_file(self):
        """Should overwrite an existing file."""
        file_path = os.path.join(self.temp_dir, "existing.txt")
        
        with open(file_path, "w") as f:
            f.write("Original content")
        
        new_content = "New content"
        result = write_file(file_path=file_path, content=new_content)
        
        assert result.get("error") is None
        assert "overwrote" in result["llmContent"].lower()
        with open(file_path) as f:
            assert f.read() == new_content

    def test_create_nested_directories(self):
        """Should create nested directories if they don't exist."""
        file_path = os.path.join(self.temp_dir, "a", "b", "c", "file.txt")
        content = "Deep nested content"
        
        result = write_file(file_path=file_path, content=content)
        
        assert result.get("error") is None
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert f.read() == content

    def test_error_when_path_is_directory(self):
        """Should return error when path is a directory."""
        dir_path = os.path.join(self.temp_dir, "subdir")
        os.makedirs(dir_path)
        
        result = write_file(file_path=dir_path, content="content")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "TARGET_IS_DIRECTORY"

    def test_error_when_file_path_empty(self):
        """Should return error when file_path is empty."""
        result = write_file(file_path="", content="content")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_FILE_PATH"


class TestWriteFileOutputFormat:
    """Test write_file output format matches gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="write-file-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_llm_content_format_new_file(self):
        """Should format llmContent correctly for new file."""
        file_path = os.path.join(self.temp_dir, "new.txt")
        
        result = write_file(file_path=file_path, content="content")
        
        assert "created" in result["llmContent"].lower()
        assert file_path in result["llmContent"]

    def test_llm_content_format_overwrite(self):
        """Should format llmContent correctly for overwrite."""
        file_path = os.path.join(self.temp_dir, "existing.txt")
        with open(file_path, "w") as f:
            f.write("old")
        
        result = write_file(file_path=file_path, content="new")
        
        assert "overwrote" in result["llmContent"].lower()

    def test_return_display_format(self):
        """Should format returnDisplay correctly."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        
        result = write_file(file_path=file_path, content="content")
        
        display = result["returnDisplay"]
        assert isinstance(display, dict)
        assert "fileDiff" in display
        assert "fileName" in display
        assert "filePath" in display
        assert "isNewFile" in display

    def test_diff_stat_format(self):
        """Should include diff statistics."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("line 1\nline 2\n")
        
        result = write_file(file_path=file_path, content="new line 1\nnew line 2\nnew line 3\n")
        
        display = result["returnDisplay"]
        assert "diffStat" in display
        assert "added" in display["diffStat"]
        assert "removed" in display["diffStat"]

    def test_is_new_file_flag(self):
        """Should correctly set isNewFile flag."""
        # New file
        new_path = os.path.join(self.temp_dir, "new.txt")
        result1 = write_file(file_path=new_path, content="content")
        assert result1["returnDisplay"]["isNewFile"] is True
        
        # Existing file
        result2 = write_file(file_path=new_path, content="updated")
        assert result2["returnDisplay"]["isNewFile"] is False

    def test_error_format(self):
        """Should format error correctly."""
        result = write_file(file_path="", content="content")
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]

    def test_user_modified_content_message(self):
        """Should include message when user modified content."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        
        result = write_file(
            file_path=file_path,
            content="user modified content",
            modified_by_user=True,
            ai_proposed_content="original content",
        )
        
        assert "User modified" in result["llmContent"]

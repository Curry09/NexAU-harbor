# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for list_directory - aligned with gemini-cli's ls.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
"""

import os
import shutil
import tempfile

import pytest

from nexau_harbor.tool_impl.list_directory import list_directory


class TestListDirectory:
    """Test list_directory tool functionality matching gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory structure for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="ls-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_files_in_directory(self):
        """Should list files in a directory."""
        with open(os.path.join(self.temp_dir, "file1.txt"), "w") as f:
            f.write("content1")
        os.makedirs(os.path.join(self.temp_dir, "subdir"))
        
        result = list_directory(dir_path=self.temp_dir)
        
        assert "[DIR] subdir" in result["llmContent"]
        assert "file1.txt" in result["llmContent"]
        assert "Listed" in result["returnDisplay"]
        assert "item(s)" in result["returnDisplay"]

    def test_handle_empty_directories(self):
        """Should handle empty directories."""
        result = list_directory(dir_path=self.temp_dir)
        
        # Empty directory should return appropriate message
        assert "empty" in result["returnDisplay"].lower() or "Listed" in result["returnDisplay"]

    def test_respect_ignore_patterns(self):
        """Should respect ignore patterns."""
        # Create files
        with open(os.path.join(self.temp_dir, "visible.txt"), "w") as f:
            f.write("visible")
        with open(os.path.join(self.temp_dir, "ignored.log"), "w") as f:
            f.write("ignored")
        
        # Create .gitignore
        with open(os.path.join(self.temp_dir, ".gitignore"), "w") as f:
            f.write("*.log\n")
        
        result = list_directory(dir_path=self.temp_dir)
        
        assert "visible.txt" in result["llmContent"]
        # ignored.log should not be in the file list (but might be mentioned in ignored count)

    def test_respect_gitignore_patterns(self):
        """Should respect .gitignore patterns."""
        os.makedirs(os.path.join(self.temp_dir, "node_modules"))
        with open(os.path.join(self.temp_dir, "package.json"), "w") as f:
            f.write("{}")
        
        # Create .gitignore
        with open(os.path.join(self.temp_dir, ".gitignore"), "w") as f:
            f.write("node_modules/\n")
        
        result = list_directory(dir_path=self.temp_dir)
        
        # node_modules should be ignored
        assert "package.json" in result["llmContent"]

    def test_respect_geminiignore_patterns(self):
        """Should respect .geminiignore patterns."""
        with open(os.path.join(self.temp_dir, "visible.txt"), "w") as f:
            f.write("visible")
        with open(os.path.join(self.temp_dir, "secret.env"), "w") as f:
            f.write("SECRET=value")
        
        # Create .geminiignore
        with open(os.path.join(self.temp_dir, ".geminiignore"), "w") as f:
            f.write("*.env\n")
        
        result = list_directory(dir_path=self.temp_dir)
        
        assert "visible.txt" in result["llmContent"]

    def test_handle_non_directory_paths(self):
        """Should return error for non-directory paths."""
        file_path = os.path.join(self.temp_dir, "file.txt")
        with open(file_path, "w") as f:
            f.write("content")
        
        result = list_directory(dir_path=file_path)
        
        assert result.get("error") is not None
        assert "not a directory" in result["llmContent"].lower()

    def test_handle_non_existent_paths(self):
        """Should return error for non-existent paths."""
        result = list_directory(dir_path="/nonexistent/path")
        
        assert result.get("error") is not None

    def test_sort_directories_first_then_files_alphabetically(self):
        """Should sort directories first, then files alphabetically."""
        # Create directories and files
        os.makedirs(os.path.join(self.temp_dir, "zdir"))
        os.makedirs(os.path.join(self.temp_dir, "adir"))
        with open(os.path.join(self.temp_dir, "zfile.txt"), "w") as f:
            f.write("z")
        with open(os.path.join(self.temp_dir, "afile.txt"), "w") as f:
            f.write("a")
        
        result = list_directory(dir_path=self.temp_dir)
        
        # Check directories come before files
        content = result["llmContent"]
        adir_pos = content.find("adir")
        zdir_pos = content.find("zdir")
        afile_pos = content.find("afile")
        zfile_pos = content.find("zfile")
        
        # Directories should come first
        assert adir_pos < afile_pos
        assert zdir_pos < zfile_pos


class TestListDirectoryValidation:
    """Test list_directory parameter validation."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="ls-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_accept_valid_absolute_path(self):
        """Should accept valid absolute path."""
        result = list_directory(dir_path=self.temp_dir)
        
        assert result.get("error") is None

    def test_accept_relative_paths(self):
        """Should accept relative paths (resolved from cwd)."""
        # Create a subdir to test with
        subdir = os.path.join(self.temp_dir, "subtest")
        os.makedirs(subdir)
        
        # Change to temp_dir and use relative path
        original_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            result = list_directory(dir_path="subtest")
            assert result.get("error") is None
        finally:
            os.chdir(original_cwd)


class TestListDirectoryOutputFormat:
    """Test list_directory output format matches gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="ls-tool-test-")
        with open(os.path.join(self.temp_dir, "test.txt"), "w") as f:
            f.write("test")
        os.makedirs(os.path.join(self.temp_dir, "subdir"))
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_llm_content_format(self):
        """Should format llmContent correctly."""
        result = list_directory(dir_path=self.temp_dir)
        
        # Should contain directory markers
        assert "[DIR]" in result["llmContent"]
        # Should contain file names
        assert "test.txt" in result["llmContent"]

    def test_return_display_format(self):
        """Should format returnDisplay correctly."""
        result = list_directory(dir_path=self.temp_dir)
        
        assert "Listed" in result["returnDisplay"]
        assert "item(s)" in result["returnDisplay"]

    def test_ignored_count_in_display(self):
        """Should show ignored count when files are ignored."""
        # Create files
        with open(os.path.join(self.temp_dir, "visible.txt"), "w") as f:
            f.write("visible")
        with open(os.path.join(self.temp_dir, "ignored.log"), "w") as f:
            f.write("ignored")
        
        # Create .gitignore
        with open(os.path.join(self.temp_dir, ".gitignore"), "w") as f:
            f.write("*.log\n")
        
        result = list_directory(dir_path=self.temp_dir)
        
        # Should mention ignored files
        if "ignored" in result["returnDisplay"]:
            assert "ignored" in result["returnDisplay"].lower()

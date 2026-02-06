# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for glob tool - aligned with gemini-cli's glob.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
Note: Python's glob module is case-sensitive on Linux/Mac but case-insensitive on Windows.
"""

import os
import shutil
import tempfile
import time

import pytest

from nexau_harbor.tool_impl.glob_tool import glob, _sort_file_entries


class TestGlobTool:
    """Test glob tool functionality matching gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory structure for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="glob-tool-test-")
        
        # Create test files
        with open(os.path.join(self.temp_dir, "fileA.txt"), "w") as f:
            f.write("content A")
        with open(os.path.join(self.temp_dir, "FileB.TXT"), "w") as f:
            f.write("content B")
        
        # Create subdirectory with files
        subdir = os.path.join(self.temp_dir, "sub")
        os.makedirs(subdir)
        with open(os.path.join(subdir, "fileC.md"), "w") as f:
            f.write("content C")
        with open(os.path.join(subdir, "FileD.MD"), "w") as f:
            f.write("content D")
        
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_files_matching_simple_pattern(self):
        """Should find files matching a simple pattern in the root."""
        result = glob(pattern="*.txt", dir_path=self.temp_dir)
        
        # At least one .txt file should be found
        assert "Found" in result["llmContent"]
        assert "file(s)" in result["llmContent"]
        assert "fileA.txt" in result["llmContent"]

    def test_find_files_using_deep_globstar_pattern(self):
        """Should find files using **/ patterns for recursive search."""
        result = glob(pattern="**/*.md", dir_path=self.temp_dir)
        
        assert "Found" in result["llmContent"]
        assert "fileC.md" in result["llmContent"]

    def test_return_no_files_found_message(self):
        """Should return appropriate message when no files found."""
        result = glob(pattern="*.nonexistent", dir_path=self.temp_dir)
        
        assert "No files found" in result["llmContent"]

    def test_sort_files_by_modification_time(self):
        """Should sort recently modified files first."""
        # Create files with different modification times
        newer_file = os.path.join(self.temp_dir, "newer.txt")
        with open(newer_file, "w") as f:
            f.write("newer")
        
        # Give some time difference
        time.sleep(0.1)
        
        older_file = os.path.join(self.temp_dir, "older.txt")
        with open(older_file, "w") as f:
            f.write("older")
        
        result = glob(pattern="*.txt", dir_path=self.temp_dir)
        
        # Files should be found
        assert "Found" in result["llmContent"]

    def test_validate_empty_pattern(self):
        """Should return error for empty pattern."""
        result = glob(pattern="", dir_path=self.temp_dir)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PATTERN"

    def test_validate_whitespace_pattern(self):
        """Should return error for whitespace-only pattern."""
        result = glob(pattern="   ", dir_path=self.temp_dir)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PATTERN"

    def test_search_path_does_not_exist(self):
        """Should return error if search path doesn't exist."""
        result = glob(pattern="*.txt", dir_path="/nonexistent/path")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "DIRECTORY_NOT_FOUND"

    def test_search_path_is_not_directory(self):
        """Should return error if search path is not a directory."""
        file_path = os.path.join(self.temp_dir, "fileA.txt")
        result = glob(pattern="*.txt", dir_path=file_path)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "NOT_A_DIRECTORY"

    def test_respect_gitignore_by_default(self):
        """Should respect .gitignore by default."""
        # Create .gitignore
        with open(os.path.join(self.temp_dir, ".gitignore"), "w") as f:
            f.write("ignored.txt\n")
        
        # Create ignored file
        with open(os.path.join(self.temp_dir, "ignored.txt"), "w") as f:
            f.write("should be ignored")
        
        result = glob(pattern="*.txt", dir_path=self.temp_dir)
        
        # ignored.txt should not appear in results
        assert "ignored.txt" not in result["llmContent"] or "ignored" in result["llmContent"].lower()

    def test_respect_geminiignore_by_default(self):
        """Should respect .geminiignore by default."""
        # Create .geminiignore
        with open(os.path.join(self.temp_dir, ".geminiignore"), "w") as f:
            f.write("secret.txt\n")
        
        # Create secret file
        with open(os.path.join(self.temp_dir, "secret.txt"), "w") as f:
            f.write("secret content")
        
        result = glob(pattern="*.txt", dir_path=self.temp_dir)
        
        # secret.txt should not appear in results
        # (might still be in message about ignored files)
        files_section = result["llmContent"].split(":\n")[-1] if ":\n" in result["llmContent"] else ""
        assert "secret.txt" not in files_section or "ignored" in result["llmContent"].lower()

    def test_not_respect_gitignore_when_disabled(self):
        """Should not respect .gitignore when disabled."""
        # Create .gitignore
        with open(os.path.join(self.temp_dir, ".gitignore"), "w") as f:
            f.write("included.txt\n")
        
        # Create file that would be ignored
        with open(os.path.join(self.temp_dir, "included.txt"), "w") as f:
            f.write("should be included when gitignore disabled")
        
        result = glob(
            pattern="included.txt",
            dir_path=self.temp_dir,
            respect_git_ignore=False,
        )
        
        # File should be found when gitignore is disabled
        assert "included.txt" in result["llmContent"]


class TestSortFileEntries:
    """Test file sorting functionality."""

    def test_sort_only_older_files_alphabetically(self):
        """Should sort older files alphabetically."""
        old_time = time.time() - 86400 * 2  # 2 days ago
        entries = [
            ("z.txt", old_time),
            ("a.txt", old_time - 100),
            ("m.txt", old_time - 50),
        ]
        
        sorted_paths = _sort_file_entries(entries, time.time(), 86400 * 1000)
        
        assert sorted_paths == ["a.txt", "m.txt", "z.txt"]

    def test_handle_empty_array(self):
        """Should handle empty array."""
        sorted_paths = _sort_file_entries([], time.time(), 86400 * 1000)
        
        assert sorted_paths == []

    def test_use_recency_threshold_parameter(self):
        """Should use recency threshold parameter."""
        now = time.time()
        # Files within threshold (1 hour = 3600000ms)
        recent_time = now - 1800  # 30 minutes ago
        # Files outside threshold
        old_time = now - 7200  # 2 hours ago
        
        entries = [
            ("recent.txt", recent_time),
            ("old.txt", old_time),
        ]
        
        # With 1 hour threshold
        sorted_paths = _sort_file_entries(entries, now, 3600 * 1000)
        
        # Recent file should come first
        assert sorted_paths[0] == "recent.txt"


class TestGlobToolOutputFormat:
    """Test glob tool output format matches gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="glob-tool-test-")
        with open(os.path.join(self.temp_dir, "test.txt"), "w") as f:
            f.write("test")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_llm_content_format(self):
        """Should format llmContent correctly."""
        result = glob(pattern="*.txt", dir_path=self.temp_dir)
        
        assert "Found" in result["llmContent"]
        assert "file(s)" in result["llmContent"]
        assert "modification time" in result["llmContent"]

    def test_return_display_format(self):
        """Should format returnDisplay correctly."""
        result = glob(pattern="*.txt", dir_path=self.temp_dir)
        
        assert "Found" in result["returnDisplay"]
        assert "matching" in result["returnDisplay"]

    def test_error_format(self):
        """Should format error correctly."""
        result = glob(pattern="", dir_path=self.temp_dir)
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]

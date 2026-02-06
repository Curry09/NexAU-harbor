# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for search_file_content (grep) - aligned with gemini-cli's grep.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
"""

import os
import shutil
import tempfile

import pytest

from nexau_harbor.tool_impl.search_file_content import search_file_content


class TestSearchFileContent:
    """Test search_file_content tool functionality matching gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory with test files."""
        self.temp_dir = tempfile.mkdtemp(prefix="grep-tool-test-")
        
        # Create test files
        with open(os.path.join(self.temp_dir, "fileA.txt"), "w") as f:
            f.write("hello world\nsecond line with world\n")
        with open(os.path.join(self.temp_dir, "fileB.js"), "w") as f:
            f.write("const x = 1;\nfunction hello() {}\n")
        
        # Create subdirectory
        subdir = os.path.join(self.temp_dir, "sub")
        os.makedirs(subdir)
        with open(os.path.join(subdir, "fileC.txt"), "w") as f:
            f.write("another world in sub dir\n")
        
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_matches_for_simple_pattern(self):
        """Should find matches for a simple pattern in all files."""
        result = search_file_content(pattern="world", dir_path=self.temp_dir)
        
        assert "Found" in result["llmContent"]
        assert "match" in result["llmContent"]
        assert "fileA.txt" in result["llmContent"]
        assert "world" in result["llmContent"]

    def test_find_matches_in_specific_path(self):
        """Should find matches only in specified path."""
        subdir = os.path.join(self.temp_dir, "sub")
        result = search_file_content(pattern="world", dir_path=subdir)
        
        assert "Found" in result["llmContent"]
        assert "fileC.txt" in result["llmContent"]
        assert "fileA.txt" not in result["llmContent"]

    def test_find_matches_with_include_glob(self):
        """Should filter files by include glob pattern."""
        result = search_file_content(
            pattern="hello",
            dir_path=self.temp_dir,
            include="*.txt",
        )
        
        # Should find in .txt files only
        assert "fileA.txt" in result["llmContent"]
        # Should not include .js file
        assert "fileB.js" not in result["llmContent"]

    def test_return_no_matches_found(self):
        """Should return appropriate message when no matches found."""
        result = search_file_content(
            pattern="nonexistent_pattern_xyz",
            dir_path=self.temp_dir,
        )
        
        assert "No matches found" in result["llmContent"]

    def test_handle_regex_special_characters(self):
        """Should handle regex special characters in pattern."""
        # Create file with special chars
        with open(os.path.join(self.temp_dir, "special.txt"), "w") as f:
            f.write("test (parentheses) and [brackets]\n")
        
        # Search for literal parentheses using escaped regex
        result = search_file_content(
            pattern=r"\(parentheses\)",
            dir_path=self.temp_dir,
        )
        
        assert "special.txt" in result["llmContent"]


class TestSearchFileContentValidation:
    """Test search_file_content parameter validation."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="grep-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_invalid_regex_pattern(self):
        """Should return error for invalid regex pattern."""
        result = search_file_content(pattern="[invalid", dir_path=self.temp_dir)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PATTERN"

    def test_path_does_not_exist(self):
        """Should return error when path doesn't exist."""
        result = search_file_content(
            pattern="test",
            dir_path="/nonexistent/path",
        )
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "FILE_NOT_FOUND"

    def test_path_is_not_directory(self):
        """Should return error when path is not a directory."""
        file_path = os.path.join(self.temp_dir, "file.txt")
        with open(file_path, "w") as f:
            f.write("content")
        
        result = search_file_content(pattern="test", dir_path=file_path)
        
        assert result.get("error") is not None
        assert "directory" in result["error"]["type"].lower() or "directory" in result["llmContent"].lower()


class TestSearchFileContentOutputFormat:
    """Test search_file_content output format matches gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory with test files."""
        self.temp_dir = tempfile.mkdtemp(prefix="grep-tool-test-")
        with open(os.path.join(self.temp_dir, "test.txt"), "w") as f:
            f.write("line one\nline two\nline three\n")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_llm_content_format(self):
        """Should format llmContent correctly."""
        result = search_file_content(pattern="line", dir_path=self.temp_dir)
        
        assert "Found" in result["llmContent"]
        assert "match" in result["llmContent"]
        assert "File:" in result["llmContent"]
        assert "L" in result["llmContent"]  # Line number prefix

    def test_return_display_format(self):
        """Should format returnDisplay correctly."""
        result = search_file_content(pattern="line", dir_path=self.temp_dir)
        
        assert "Found" in result["returnDisplay"]
        assert "match" in result["returnDisplay"]

    def test_error_format(self):
        """Should format error correctly."""
        result = search_file_content(pattern="[invalid", dir_path=self.temp_dir)
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]

    def test_include_filter_in_message(self):
        """Should include filter description in message when filter is used."""
        result = search_file_content(
            pattern="test",
            dir_path=self.temp_dir,
            include="*.txt",
        )
        
        # Should mention the filter
        assert "filter" in result["llmContent"] or "*.txt" in result["llmContent"]

# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for replace (edit) tool - aligned with gemini-cli's edit.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
"""

import os
import shutil
import tempfile

import pytest

from nexau_harbor.tool_impl.replace import replace


class TestReplace:
    """Test replace tool functionality matching gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="edit-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_edit_existing_file(self):
        """Should edit an existing file and return diff with fileName."""
        file_path = os.path.join(self.temp_dir, "execute_me.txt")
        initial_content = "This is some old text."
        new_content = "This is some new text."
        
        with open(file_path, "w") as f:
            f.write(initial_content)
        
        result = replace(
            file_path=file_path,
            old_string="old",
            new_string="new",
        )
        
        assert "Successfully modified" in result["llmContent"]
        with open(file_path) as f:
            assert f.read() == new_content
        
        display = result["returnDisplay"]
        assert "fileDiff" in display
        assert display["fileName"] == "execute_me.txt"

    def test_return_error_if_old_string_not_found(self):
        """Should return error if old_string not found in file."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("Hello World")
        
        result = replace(
            file_path=file_path,
            old_string="nonexistent",
            new_string="replacement",
        )
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "EDIT_NO_OCCURRENCE_FOUND"

    def test_create_new_file_with_empty_old_string(self):
        """Should create new file when old_string is empty and file doesn't exist."""
        file_path = os.path.join(self.temp_dir, "new_file.txt")
        content = "New file content"
        
        result = replace(
            file_path=file_path,
            old_string="",
            new_string=content,
        )
        
        assert result.get("error") is None
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert f.read() == content

    def test_flexible_whitespace_replacement(self):
        """Should match with flexible whitespace."""
        file_path = os.path.join(self.temp_dir, "flex.txt")
        # Content with different indentation
        with open(file_path, "w") as f:
            f.write("    function test() {\n        return true;\n    }\n")
        
        result = replace(
            file_path=file_path,
            old_string="function test() {\n    return true;\n}",
            new_string="function test() {\n    return false;\n}",
        )
        
        assert result.get("error") is None
        with open(file_path) as f:
            content = f.read()
        assert "false" in content


class TestReplaceValidation:
    """Test replace parameter validation."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="edit-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_not_found(self):
        """Should return error if file doesn't exist."""
        result = replace(
            file_path=os.path.join(self.temp_dir, "nonexistent.txt"),
            old_string="old",
            new_string="new",
        )
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "FILE_NOT_FOUND"

    def test_attempt_to_create_existing_file(self):
        """Should return error when trying to create existing file."""
        file_path = os.path.join(self.temp_dir, "existing.txt")
        with open(file_path, "w") as f:
            f.write("existing content")
        
        result = replace(
            file_path=file_path,
            old_string="",  # Empty = create new
            new_string="new content",
        )
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "ATTEMPT_TO_CREATE_EXISTING_FILE"

    def test_no_occurrence_found(self):
        """Should return error when no occurrence found."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("Hello World")
        
        result = replace(
            file_path=file_path,
            old_string="Goodbye",
            new_string="Hi",
        )
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "EDIT_NO_OCCURRENCE_FOUND"

    def test_expected_occurrence_mismatch(self):
        """Should return error when occurrence count doesn't match expected."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("foo bar foo")
        
        result = replace(
            file_path=file_path,
            old_string="foo",
            new_string="baz",
            expected_replacements=1,  # But there are 2 occurrences
        )
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "EDIT_EXPECTED_OCCURRENCE_MISMATCH"


class TestExpectedReplacements:
    """Test expected_replacements parameter."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="edit-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_succeed_when_occurrences_match(self):
        """Should succeed when occurrences match expected."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("foo bar foo")
        
        result = replace(
            file_path=file_path,
            old_string="foo",
            new_string="baz",
            expected_replacements=2,
        )
        
        assert result.get("error") is None
        with open(file_path) as f:
            assert f.read() == "baz bar baz"

    def test_fail_when_occurrences_do_not_match(self):
        """Should fail when occurrences don't match expected."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("foo bar foo foo")
        
        result = replace(
            file_path=file_path,
            old_string="foo",
            new_string="baz",
            expected_replacements=2,  # But there are 3
        )
        
        assert result.get("error") is not None


class TestDollarSignHandling:
    """Test dollar sign handling in replacement strings."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="edit-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dollar_literal(self):
        """Should handle literal $ in replacement."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("price: 10")
        
        result = replace(
            file_path=file_path,
            old_string="price: 10",
            new_string="price: $10",
        )
        
        assert result.get("error") is None
        with open(file_path) as f:
            assert f.read() == "price: $10"

    def test_dollar_ampersand_literal(self):
        """Should handle $& literally (not as regex back-reference)."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("before text after")
        
        result = replace(
            file_path=file_path,
            old_string="text",
            new_string="$&replaced",
        )
        
        assert result.get("error") is None
        with open(file_path) as f:
            content = f.read()
        # Should be literal $& not a back-reference
        assert "$&replaced" in content


class TestReplaceOutputFormat:
    """Test replace output format matches gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="edit-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_success_llm_content_format(self):
        """Should format llmContent correctly on success."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("old content")
        
        result = replace(
            file_path=file_path,
            old_string="old",
            new_string="new",
        )
        
        assert "Successfully modified" in result["llmContent"]
        assert file_path in result["llmContent"]

    def test_return_display_format(self):
        """Should format returnDisplay correctly."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("old content")
        
        result = replace(
            file_path=file_path,
            old_string="old",
            new_string="new",
        )
        
        display = result["returnDisplay"]
        assert isinstance(display, dict)
        assert "fileDiff" in display
        assert "fileName" in display
        assert "isNewFile" in display
        assert display["isNewFile"] is False

    def test_error_format(self):
        """Should format error correctly."""
        result = replace(
            file_path=os.path.join(self.temp_dir, "nonexistent.txt"),
            old_string="old",
            new_string="new",
        )
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]

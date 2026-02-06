# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for save_memory - aligned with gemini-cli's memoryTool.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
"""

import os
import shutil
import tempfile

import pytest

from nexau_harbor.tool_impl.save_memory import save_memory


class TestSaveMemory:
    """Test save_memory tool functionality matching gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="memory-tool-test-")
        self.memory_file = os.path.join(self.temp_dir, "GEMINI.md")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_memory_file_if_not_exists(self):
        """Should create GEMINI.md file if it doesn't exist."""
        fact = "This is a new fact."
        
        result = save_memory(fact=fact, memory_file_path=self.memory_file)
        
        assert result.get("error") is None
        assert os.path.exists(self.memory_file)
        with open(self.memory_file) as f:
            content = f.read()
        assert fact in content

    def test_append_fact_to_existing_file(self):
        """Should append fact to existing GEMINI.md file."""
        # Create existing file with content
        existing_content = "# Existing Content\n\nSome existing content.\n"
        with open(self.memory_file, "w") as f:
            f.write(existing_content)
        
        fact = "New fact to append."
        result = save_memory(fact=fact, memory_file_path=self.memory_file)
        
        assert result.get("error") is None
        with open(self.memory_file) as f:
            content = f.read()
        
        assert fact in content

    def test_add_fact_under_correct_header(self):
        """Should add fact under the correct header section."""
        fact = "Test fact."
        
        result = save_memory(fact=fact, memory_file_path=self.memory_file)
        
        assert result.get("error") is None
        with open(self.memory_file) as f:
            content = f.read()
        
        # Should contain the header and fact
        assert "## Gemini Added Memories" in content
        assert fact in content

    def test_error_when_fact_empty(self):
        """Should return error when fact is empty."""
        result = save_memory(fact="", memory_file_path=self.memory_file)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"

    def test_error_when_fact_whitespace_only(self):
        """Should return error when fact is only whitespace."""
        result = save_memory(fact="   ", memory_file_path=self.memory_file)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"


class TestSaveMemoryOutputFormat:
    """Test save_memory output format matches gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="memory-tool-test-")
        self.memory_file = os.path.join(self.temp_dir, "GEMINI.md")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_llm_content_format_success(self):
        """Should format llmContent correctly on success."""
        fact = "Test fact for memory."
        
        result = save_memory(fact=fact, memory_file_path=self.memory_file)
        
        assert result.get("error") is None
        # llmContent should be JSON with success and message
        assert "success" in result["llmContent"]

    def test_return_display_format(self):
        """Should format returnDisplay correctly."""
        fact = "Test fact."
        
        result = save_memory(fact=fact, memory_file_path=self.memory_file)
        
        # returnDisplay should indicate success with the fact
        assert "remembered" in result["returnDisplay"].lower() or "okay" in result["returnDisplay"].lower()
        assert fact in result["returnDisplay"]

    def test_error_format(self):
        """Should format error correctly."""
        result = save_memory(fact="", memory_file_path=self.memory_file)
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]


class TestSaveMemoryFileManagement:
    """Test save_memory file management."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="memory-tool-test-")
        self.memory_file = os.path.join(self.temp_dir, "GEMINI.md")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_preserve_existing_content(self):
        """Should preserve existing content when appending."""
        # Create file with existing content including section header
        with open(self.memory_file, "w") as f:
            f.write("# My Memory\n\n## Gemini Added Memories\n- Fact 1\n- Fact 2\n")
        
        result = save_memory(fact="Fact 3", memory_file_path=self.memory_file)
        
        assert result.get("error") is None
        with open(self.memory_file) as f:
            content = f.read()
        
        assert "Fact 1" in content
        assert "Fact 2" in content
        assert "Fact 3" in content

    def test_handle_special_characters(self):
        """Should handle special characters in fact."""
        special_fact = "Fact with special chars: <>&\"'"
        
        result = save_memory(fact=special_fact, memory_file_path=self.memory_file)
        
        assert result.get("error") is None
        with open(self.memory_file) as f:
            content = f.read()
        assert special_fact in content

    def test_handle_multiline_fact(self):
        """Should handle multiline facts."""
        multiline_fact = "Line 1\nLine 2\nLine 3"
        
        result = save_memory(fact=multiline_fact, memory_file_path=self.memory_file)
        
        assert result.get("error") is None
        with open(self.memory_file) as f:
            content = f.read()
        # The fact should be stored, possibly reformatted
        assert "Line 1" in content

    def test_user_modified_content(self):
        """Should handle user-modified content."""
        # First create a file
        save_memory(fact="Initial fact", memory_file_path=self.memory_file)
        
        # Now update with user-modified content
        modified_content = "# User Modified\n\nCustom content here.\n"
        result = save_memory(
            fact="Ignored",
            modified_by_user=True,
            modified_content=modified_content,
            memory_file_path=self.memory_file,
        )
        
        assert result.get("error") is None
        with open(self.memory_file) as f:
            content = f.read()
        assert content == modified_content

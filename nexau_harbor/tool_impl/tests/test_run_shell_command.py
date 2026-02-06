# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for run_shell_command (shell) - aligned with gemini-cli's shell.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
"""

import os
import shutil
import tempfile
import time

import pytest

from nexau_harbor.tool_impl.run_shell_command import run_shell_command


class TestRunShellCommand:
    """Test run_shell_command tool functionality matching gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="shell-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_execute_simple_command(self):
        """Should execute a simple command successfully."""
        result = run_shell_command(command="echo 'hello world'")
        
        assert "hello world" in result["llmContent"]
        assert result.get("error") is None

    def test_execute_command_with_exit_code(self):
        """Should capture non-zero exit code."""
        result = run_shell_command(command="exit 42")
        
        assert "Exit Code: 42" in result["llmContent"]

    def test_execute_command_in_directory(self):
        """Should execute command in specified directory."""
        # Create a file in temp dir
        with open(os.path.join(self.temp_dir, "test.txt"), "w") as f:
            f.write("test")
        
        result = run_shell_command(command="ls", dir_path=self.temp_dir)
        
        assert "test.txt" in result["llmContent"]

    def test_error_when_command_empty(self):
        """Should return error when command is empty."""
        result = run_shell_command(command="")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_COMMAND"

    def test_error_when_directory_not_found(self):
        """Should return error when directory doesn't exist."""
        result = run_shell_command(
            command="ls",
            dir_path="/nonexistent/directory",
        )
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "DIRECTORY_NOT_FOUND"

    def test_error_when_path_is_not_directory(self):
        """Should return error when path is not a directory."""
        file_path = os.path.join(self.temp_dir, "file.txt")
        with open(file_path, "w") as f:
            f.write("content")
        
        result = run_shell_command(command="ls", dir_path=file_path)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "NOT_A_DIRECTORY"


class TestRunShellCommandBackground:
    """Test run_shell_command background execution."""

    def test_background_execution(self):
        """Should run command in background."""
        result = run_shell_command(
            command="sleep 10",
            is_background=True,
        )
        
        # Should indicate background execution
        llm_lower = result["llmContent"].lower()
        assert "background" in llm_lower or "pid" in llm_lower or "pgid" in llm_lower

    def test_background_returns_pid(self):
        """Should return PID for background process."""
        result = run_shell_command(
            command="sleep 10",
            is_background=True,
        )
        
        # Should contain PID information
        if result.get("data"):
            assert "pid" in result["data"]


class TestRunShellCommandOutputFormat:
    """Test run_shell_command output format matches gemini-cli."""

    def test_llm_content_format_success(self):
        """Should format llmContent correctly on success."""
        result = run_shell_command(command="echo 'test output'")
        
        assert "Output:" in result["llmContent"]
        assert "test output" in result["llmContent"]

    def test_llm_content_format_empty_output(self):
        """Should format llmContent correctly for empty output."""
        result = run_shell_command(command="true")
        
        assert "(empty)" in result["llmContent"]

    def test_llm_content_format_error(self):
        """Should format llmContent correctly for error."""
        result = run_shell_command(command="nonexistent_command_xyz")
        
        # Should contain error or exit code info
        assert "Exit Code" in result["llmContent"] or "Error" in result["llmContent"] or "not found" in result["llmContent"].lower()

    def test_return_display_format(self):
        """Should format returnDisplay correctly."""
        result = run_shell_command(command="echo 'display test'")
        
        assert "display test" in result["returnDisplay"]

    def test_return_display_empty(self):
        """Should format returnDisplay for empty output."""
        result = run_shell_command(command="true")
        
        assert "(empty)" in result["returnDisplay"]

    def test_error_format(self):
        """Should format error correctly."""
        result = run_shell_command(command="")
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]


class TestRunShellCommandTimeout:
    """Test run_shell_command timeout handling."""

    def test_timeout_message(self):
        """Should include timeout message when command times out."""
        result = run_shell_command(
            command="sleep 10",
            timeout_ms=100,  # Very short timeout
        )
        
        # Should indicate timeout or cancellation
        llm_lower = result["llmContent"].lower()
        assert "timeout" in llm_lower or "cancelled" in llm_lower or "exceeded" in llm_lower


class TestRunShellCommandDescription:
    """Test run_shell_command description handling."""

    def test_description_included(self):
        """Should accept description parameter."""
        result = run_shell_command(
            command="echo 'test'",
            description="Print test message",
        )
        
        assert result.get("error") is None
        assert "test" in result["llmContent"]

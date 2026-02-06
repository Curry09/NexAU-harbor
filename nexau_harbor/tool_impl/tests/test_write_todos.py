# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for write_todos - aligned with gemini-cli's write-todos.test.ts

Test cases verify input/output format matches gemini-cli exactly.
"""

import pytest

from nexau_harbor.tool_impl.write_todos import write_todos


class TestWriteTodos:
    """Test write_todos tool functionality matching gemini-cli."""

    def test_update_todo_list_successfully(self):
        """Should update todo list successfully."""
        todos = [
            {"description": "Task 1", "status": "pending"},
            {"description": "Task 2", "status": "in_progress"},
            {"description": "Task 3", "status": "completed"},
        ]
        
        result = write_todos(todos=todos)
        
        assert "Successfully updated the todo list" in result["llmContent"]
        assert "1. [pending] Task 1" in result["llmContent"]
        assert "2. [in_progress] Task 2" in result["llmContent"]
        assert "3. [completed] Task 3" in result["llmContent"]

    def test_clear_todo_list(self):
        """Should clear todo list when empty array is provided."""
        result = write_todos(todos=[])
        
        assert "Successfully cleared the todo list" in result["llmContent"]

    def test_error_when_todos_not_array(self):
        """Should return error when todos is not an array."""
        result = write_todos(todos="not an array")  # type: ignore
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"
        assert "`todos` parameter must be an array" in result["llmContent"]

    def test_error_when_todo_item_not_object(self):
        """Should return error when todo item is not an object."""
        result = write_todos(todos=["not an object"])  # type: ignore
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"

    def test_error_when_description_missing(self):
        """Should return error when description is missing."""
        todos = [{"status": "pending"}]
        
        result = write_todos(todos=todos)  # type: ignore
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"
        assert "non-empty description" in result["llmContent"]

    def test_error_when_description_empty(self):
        """Should return error when description is empty."""
        todos = [{"description": "", "status": "pending"}]
        
        result = write_todos(todos=todos)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"

    def test_error_when_status_invalid(self):
        """Should return error when status is invalid."""
        todos = [{"description": "Task", "status": "invalid_status"}]
        
        result = write_todos(todos=todos)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"
        assert "valid status" in result["llmContent"]

    def test_error_when_multiple_in_progress(self):
        """Should return error when multiple tasks are in_progress."""
        todos = [
            {"description": "Task 1", "status": "in_progress"},
            {"description": "Task 2", "status": "in_progress"},
        ]
        
        result = write_todos(todos=todos)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"
        assert 'Only one task can be "in_progress"' in result["llmContent"]


class TestWriteTodosOutputFormat:
    """Test write_todos output format matches gemini-cli."""

    def test_llm_content_format(self):
        """Should format llmContent correctly."""
        todos = [
            {"description": "Task 1", "status": "pending"},
            {"description": "Task 2", "status": "completed"},
        ]
        
        result = write_todos(todos=todos)
        
        assert "Successfully updated the todo list" in result["llmContent"]
        # Check numbered list format
        assert "1. [pending] Task 1" in result["llmContent"]
        assert "2. [completed] Task 2" in result["llmContent"]

    def test_return_display_format(self):
        """Should format returnDisplay correctly."""
        todos = [
            {"description": "Task 1", "status": "pending"},
        ]
        
        result = write_todos(todos=todos)
        
        # returnDisplay should contain the todos
        assert isinstance(result["returnDisplay"], dict)
        assert "todos" in result["returnDisplay"]
        assert result["returnDisplay"]["todos"] == todos

    def test_error_format(self):
        """Should format error correctly."""
        result = write_todos(todos="invalid")  # type: ignore
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]


class TestWriteTodosValidStatuses:
    """Test all valid todo statuses."""

    @pytest.mark.parametrize("status", ["pending", "in_progress", "completed", "cancelled"])
    def test_valid_status(self, status):
        """Should accept all valid statuses."""
        todos = [{"description": "Task", "status": status}]
        
        result = write_todos(todos=todos)
        
        assert result.get("error") is None
        assert f"[{status}]" in result["llmContent"]

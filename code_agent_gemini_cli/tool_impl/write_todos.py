# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
write_todos tool - Manages task lists for complex operations.

Based on gemini-cli's write-todos.ts implementation.
"""

import json
from typing import Any


# Valid todo statuses
VALID_STATUSES = ["pending", "in_progress", "completed", "cancelled"]


def write_todos(todos: list[dict[str, Any]]) -> str:
    """
    Updates or creates a todo list for tracking subtasks.
    
    Use this for complex queries requiring multiple steps.
    Each todo should have:
    - description: The task description
    - status: 'pending', 'in_progress', 'completed', or 'cancelled'
    
    Guidelines:
    - Only one task should be 'in_progress' at a time
    - Mark tasks as 'in_progress' before starting work
    - Update status immediately when completing/cancelling
    
    Args:
        todos: Array of todo items with description and status
        
    Returns:
        JSON string with the updated todo list
    """
    try:
        # Validate input
        if not isinstance(todos, list):
            return json.dumps({
                "success": False,
                "error": "'todos' must be an array.",
                "type": "INVALID_INPUT",
            })
        
        # Validate each todo
        validated_todos = []
        in_progress_count = 0
        
        for i, todo in enumerate(todos):
            if not isinstance(todo, dict):
                return json.dumps({
                    "success": False,
                    "error": f"Todo {i + 1}: Must be an object.",
                    "type": "INVALID_TODO",
                })
            
            description = todo.get("description", "")
            status = todo.get("status", "")
            
            if not description or not description.strip():
                return json.dumps({
                    "success": False,
                    "error": f"Todo {i + 1}: 'description' is required and must be non-empty.",
                    "type": "MISSING_DESCRIPTION",
                })
            
            if status not in VALID_STATUSES:
                return json.dumps({
                    "success": False,
                    "error": f"Todo {i + 1}: Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}",
                    "type": "INVALID_STATUS",
                })
            
            if status == "in_progress":
                in_progress_count += 1
            
            validated_todos.append({
                "index": i + 1,
                "description": description.strip(),
                "status": status,
            })
        
        # Validate only one in_progress
        if in_progress_count > 1:
            return json.dumps({
                "success": False,
                "error": f"Only one task can be 'in_progress' at a time. Found {in_progress_count}.",
                "type": "MULTIPLE_IN_PROGRESS",
            })
        
        # Build formatted todo list
        if not validated_todos:
            return json.dumps({
                "success": True,
                "message": "Todo list cleared.",
                "todos": [],
                "count": 0,
            })
        
        # Status symbols
        status_symbols = {
            "pending": "○",
            "in_progress": "◉",
            "completed": "✓",
            "cancelled": "✗",
        }
        
        formatted_lines = []
        for todo in validated_todos:
            symbol = status_symbols.get(todo["status"], "?")
            formatted_lines.append(f"{todo['index']}. [{symbol}] [{todo['status']}] {todo['description']}")
        
        # Count by status
        counts = {status: 0 for status in VALID_STATUSES}
        for todo in validated_todos:
            counts[todo["status"]] += 1
        
        summary_parts = []
        if counts["completed"]:
            summary_parts.append(f"{counts['completed']} completed")
        if counts["in_progress"]:
            summary_parts.append(f"{counts['in_progress']} in progress")
        if counts["pending"]:
            summary_parts.append(f"{counts['pending']} pending")
        if counts["cancelled"]:
            summary_parts.append(f"{counts['cancelled']} cancelled")
        
        summary = ", ".join(summary_parts) if summary_parts else "empty"
        
        return json.dumps({
            "success": True,
            "message": f"Successfully updated the todo list. Current status: {summary}.",
            "todos": validated_todos,
            "count": len(validated_todos),
            "summary": counts,
            "formatted": "\n".join(formatted_lines),
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error updating todos: {str(e)}",
            "type": "TODO_ERROR",
        })

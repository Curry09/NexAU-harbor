# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
write_file tool - Writes content to a specified file in the local filesystem.

Based on gemini-cli's write-file.ts implementation.
"""

import json
import os
from pathlib import Path
from typing import Any


def _detect_line_ending(content: str) -> str:
    """Detect the dominant line ending in content."""
    if "\r\n" in content:
        return "\r\n"
    elif "\n" in content:
        return "\n"
    elif "\r" in content:
        return "\r"
    return "\n"


def _ensure_parent_dirs(file_path: str) -> None:
    """Create parent directories if they don't exist."""
    parent = Path(file_path).parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)


def write_file(
    file_path: str,
    content: str,
) -> str:
    """
    Writes content to a specified file in the local filesystem.
    
    Creates parent directories if they don't exist.
    Overwrites the file if it already exists.
    
    Args:
        file_path: The path to the file to write to
        content: The content to write to the file
        
    Returns:
        JSON string with operation result
    """
    try:
        # Resolve path
        resolved_path = os.path.abspath(file_path)
        
        # Check if it's a directory
        if os.path.isdir(resolved_path):
            return json.dumps({
                "error": f"Path is a directory, not a file: {file_path}",
                "type": "TARGET_IS_DIRECTORY",
                "success": False,
            })
        
        # Check if file exists (for determining operation type)
        file_exists = os.path.exists(resolved_path)
        operation = "update" if file_exists else "create"
        
        # Read original content if file exists (for comparison)
        original_content = ""
        original_line_ending = "\n"
        encoding = "utf-8"
        
        if file_exists:
            try:
                with open(resolved_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
                original_line_ending = _detect_line_ending(original_content)
            except UnicodeDecodeError:
                pass  # Will use default encoding
        
        # Create parent directories
        _ensure_parent_dirs(resolved_path)
        
        # Preserve line endings if updating
        final_content = content
        if file_exists and original_line_ending == "\r\n":
            # Convert to CRLF if original was CRLF
            final_content = content.replace("\r\n", "\n").replace("\n", "\r\n")
        
        # Write file
        with open(resolved_path, "w", encoding=encoding, newline="") as f:
            f.write(final_content)
        
        # Calculate stats
        num_lines = len(final_content.splitlines())
        
        result: dict[str, Any] = {
            "success": True,
            "operation": operation,
            "file_path": file_path,
            "num_lines": num_lines,
            "message": (
                f"Successfully created and wrote to new file: {file_path}."
                if operation == "create"
                else f"Successfully overwrote file: {file_path}."
            ),
        }
        
        return json.dumps(result, ensure_ascii=False)
        
    except PermissionError:
        return json.dumps({
            "error": f"Permission denied: {file_path}",
            "type": "PERMISSION_DENIED",
            "success": False,
        })
    except OSError as e:
        error_type = "NO_SPACE_LEFT" if "No space left" in str(e) else "WRITE_ERROR"
        return json.dumps({
            "error": f"Error writing file: {str(e)}",
            "type": error_type,
            "success": False,
        })
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "type": "WRITE_ERROR",
            "success": False,
        })

# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
save_memory tool - Saves facts to long-term memory.

Based on gemini-cli's memoryTool.ts implementation.
Stores facts in a GEMINI.md file with proper section management.
"""

import difflib
import json
import os
from pathlib import Path
from typing import Any


# Configuration constants
DEFAULT_CONTEXT_FILENAME = "GEMINI.md"
MEMORY_SECTION_HEADER = "## Gemini Added Memories"


def _get_global_gemini_dir() -> str:
    """Get the global Gemini directory path."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".gemini")


def _get_global_memory_file_path() -> str:
    """Get the path to the global memory file."""
    return os.path.join(_get_global_gemini_dir(), DEFAULT_CONTEXT_FILENAME)


def _ensure_newline_separation(current_content: str) -> str:
    """Ensure proper newline separation before appending content."""
    if len(current_content) == 0:
        return ""
    if current_content.endswith("\n\n") or current_content.endswith("\r\n\r\n"):
        return ""
    if current_content.endswith("\n") or current_content.endswith("\r\n"):
        return "\n"
    return "\n\n"


def _read_memory_file_content(file_path: str) -> str:
    """Read the current content of the memory file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def _compute_new_content(current_content: str, fact: str) -> str:
    """Compute the new content that would result from adding a memory entry."""
    # Process the fact
    processed_text = fact.strip()
    # Remove leading dashes
    import re
    processed_text = re.sub(r"^(-+\s*)+", "", processed_text).strip()
    new_memory_item = f"- {processed_text}"
    
    header_index = current_content.find(MEMORY_SECTION_HEADER)
    
    if header_index == -1:
        # Header not found, append header and then the entry
        separator = _ensure_newline_separation(current_content)
        return f"{current_content}{separator}{MEMORY_SECTION_HEADER}\n{new_memory_item}\n"
    else:
        # Header found, find where to insert the new memory entry
        start_of_section = header_index + len(MEMORY_SECTION_HEADER)
        
        # Find end of section (next ## header or end of file)
        end_of_section_index = current_content.find("\n## ", start_of_section)
        if end_of_section_index == -1:
            end_of_section_index = len(current_content)
        
        before_section = current_content[:start_of_section].rstrip()
        section_content = current_content[start_of_section:end_of_section_index].rstrip()
        after_section = current_content[end_of_section_index:]
        
        section_content += f"\n{new_memory_item}"
        
        result = f"{before_section}\n{section_content.lstrip()}\n{after_section}".rstrip() + "\n"
        return result


def _generate_diff(file_path: str, original: str, new: str) -> str:
    """Generate unified diff between original and new content."""
    original_lines = original.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"Current: {file_path}",
        tofile=f"Proposed: {file_path}",
    )
    
    return "".join(diff)


def save_memory(
    fact: str,
    modified_by_user: bool = False,
    modified_content: str | None = None,
    memory_file_path: str | None = None,
) -> dict[str, Any]:
    """
    Saves a specific piece of information or fact to long-term memory.
    
    Use this tool when the user explicitly asks you to remember something,
    or when they state a clear, concise fact that seems important to retain.
    
    Args:
        fact: The specific fact or piece of information to remember
        modified_by_user: Whether the content was modified by user
        modified_content: User-modified content (if modified_by_user is True)
        memory_file_path: Custom path for memory file (optional)
        
    Returns:
        Dict with llmContent and returnDisplay matching gemini-cli format
    """
    try:
        # Validate fact
        if not fact or not fact.strip():
            return {
                "llmContent": json.dumps({
                    "success": False,
                    "error": 'Parameter "fact" must be a non-empty string.',
                }),
                "returnDisplay": "Error: Fact cannot be empty.",
                "error": {
                    "message": 'Parameter "fact" must be a non-empty string.',
                    "type": "INVALID_PARAMETER",
                },
            }
        
        # Determine memory file path
        file_path = memory_file_path or _get_global_memory_file_path()
        
        # Ensure directory exists
        parent_dir = Path(file_path).parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        
        if modified_by_user and modified_content is not None:
            # User modified the content, write it directly
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)
            
            success_message = "Okay, I've updated the memory file with your modifications."
            return {
                "llmContent": json.dumps({
                    "success": True,
                    "message": success_message,
                }),
                "returnDisplay": success_message,
            }
        else:
            # Normal memory entry logic
            current_content = _read_memory_file_content(file_path)
            new_content = _compute_new_content(current_content, fact)
            
            # Write the new content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            success_message = f'Okay, I\'ve remembered that: "{fact}"'
            return {
                "llmContent": json.dumps({
                    "success": True,
                    "message": success_message,
                }),
                "returnDisplay": success_message,
            }
            
    except PermissionError:
        error_msg = f"Permission denied writing to memory file: {file_path}"
        return {
            "llmContent": json.dumps({
                "success": False,
                "error": f"Failed to save memory. Detail: {error_msg}",
            }),
            "returnDisplay": f"Error saving memory: {error_msg}",
            "error": {
                "message": error_msg,
                "type": "MEMORY_TOOL_EXECUTION_ERROR",
            },
        }
    except Exception as e:
        error_msg = str(e)
        return {
            "llmContent": json.dumps({
                "success": False,
                "error": f"Failed to save memory. Detail: {error_msg}",
            }),
            "returnDisplay": f"Error saving memory: {error_msg}",
            "error": {
                "message": error_msg,
                "type": "MEMORY_TOOL_EXECUTION_ERROR",
            },
        }

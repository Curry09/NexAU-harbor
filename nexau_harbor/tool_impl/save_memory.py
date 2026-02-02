# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
save_memory tool - Saves facts to long-term memory.

Based on gemini-cli's memoryTool.ts implementation.
"""

import json
import os
from pathlib import Path
from typing import Any


# Configuration
DEFAULT_MEMORY_FILE = "GEMINI.md"
MEMORY_SECTION_HEADER = "## Gemini Added Memories"


def _get_memory_file_path() -> str:
    """Get the path to the memory file."""
    # Try to use a global location first
    home = Path.home()
    gemini_dir = home / ".gemini"
    
    # Create directory if it doesn't exist
    gemini_dir.mkdir(parents=True, exist_ok=True)
    
    return str(gemini_dir / DEFAULT_MEMORY_FILE)


def _ensure_newline_separation(content: str) -> str:
    """Ensure proper newline separation before appending content."""
    if not content:
        return ""
    if content.endswith("\n\n") or content.endswith("\r\n\r\n"):
        return ""
    if content.endswith("\n") or content.endswith("\r\n"):
        return "\n"
    return "\n\n"


def _compute_new_content(current_content: str, fact: str) -> str:
    """Compute new content with the memory entry added."""
    # Clean up the fact
    processed_fact = fact.strip()
    # Remove leading dashes if present
    processed_fact = processed_fact.lstrip("-").strip()
    new_memory_item = f"- {processed_fact}"
    
    header_index = current_content.find(MEMORY_SECTION_HEADER)
    
    if header_index == -1:
        # Header not found, append header and entry
        separator = _ensure_newline_separation(current_content)
        return f"{current_content}{separator}{MEMORY_SECTION_HEADER}\n{new_memory_item}\n"
    else:
        # Header found, insert after it
        start_of_section = header_index + len(MEMORY_SECTION_HEADER)
        
        # Find end of section (next ## header or end of file)
        end_of_section = current_content.find("\n## ", start_of_section)
        if end_of_section == -1:
            end_of_section = len(current_content)
        
        before_section = current_content[:start_of_section].rstrip()
        section_content = current_content[start_of_section:end_of_section].strip()
        after_section = current_content[end_of_section:]
        
        # Add new item to section
        if section_content:
            section_content = f"{section_content}\n{new_memory_item}"
        else:
            section_content = new_memory_item
        
        return f"{before_section}\n{section_content}\n{after_section}".rstrip() + "\n"


def save_memory(fact: str) -> str:
    """
    Saves a specific piece of information to long-term memory.
    
    Use this when the user explicitly asks to remember something,
    or when they state a clear, concise fact that's important to retain.
    
    Args:
        fact: The fact or information to remember
        
    Returns:
        JSON string with operation result
    """
    try:
        # Validate input
        if not fact or not fact.strip():
            return json.dumps({
                "success": False,
                "error": "Fact cannot be empty.",
                "type": "INVALID_INPUT",
            })
        
        # Get memory file path
        memory_file = _get_memory_file_path()
        
        # Read current content
        current_content = ""
        if os.path.exists(memory_file):
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    current_content = f.read()
            except IOError:
                pass
        
        # Compute new content
        new_content = _compute_new_content(current_content, fact)
        
        # Write new content
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(memory_file), exist_ok=True)
            
            with open(memory_file, "w", encoding="utf-8") as f:
                f.write(new_content)
        except IOError as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to write memory file: {str(e)}",
                "type": "WRITE_ERROR",
            })
        
        return json.dumps({
            "success": True,
            "message": f'Okay, I\'ve remembered that: "{fact}"',
            "memory_file": memory_file,
        })
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error saving memory: {str(e)}",
            "type": "MEMORY_ERROR",
        })

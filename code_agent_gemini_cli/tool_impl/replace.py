# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
replace tool - Replaces text within a file.

Based on gemini-cli's edit.ts implementation.
Supports exact matching, flexible whitespace matching, and regex-based matching.
"""

import difflib
import json
import os
import re
from typing import Any


def _detect_encoding(file_path: str) -> str:
    """Detect file encoding with fallback to utf-8."""
    try:
        import chardet
        with open(file_path, "rb") as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            if result["encoding"] and result["confidence"] > 0.7:
                return result["encoding"]
    except (ImportError, Exception):
        pass
    return "utf-8"


def _detect_line_ending(content: str) -> str:
    """Detect line ending style."""
    if "\r\n" in content:
        return "\r\n"
    elif "\n" in content:
        return "\n"
    return "\n"


def _restore_trailing_newline(original: str, modified: str) -> str:
    """Restore trailing newline consistency."""
    had_trailing = original.endswith("\n")
    if had_trailing and not modified.endswith("\n"):
        return modified + "\n"
    elif not had_trailing and modified.endswith("\n"):
        return modified.rstrip("\n")
    return modified


def _safe_literal_replace(content: str, old_string: str, new_string: str) -> str:
    """Safely replace literal string (handles $ sequences)."""
    # Use simple replace for literal replacement
    return content.replace(old_string, new_string, 1)


def _calculate_exact_replacement(content: str, old_string: str, new_string: str) -> tuple[str, int] | None:
    """Try exact string replacement."""
    normalized_content = content
    normalized_old = old_string.replace("\r\n", "\n")
    normalized_new = new_string.replace("\r\n", "\n")
    
    occurrences = normalized_content.count(normalized_old)
    if occurrences > 0:
        modified = _safe_literal_replace(normalized_content, normalized_old, normalized_new)
        modified = _restore_trailing_newline(content, modified)
        return modified, occurrences
    return None


def _calculate_flexible_replacement(content: str, old_string: str, new_string: str) -> tuple[str, int] | None:
    """Try flexible whitespace matching replacement."""
    normalized_old = old_string.replace("\r\n", "\n")
    normalized_new = new_string.replace("\r\n", "\n")
    
    source_lines = content.split("\n")
    search_lines_stripped = [line.strip() for line in normalized_old.split("\n")]
    replace_lines = normalized_new.split("\n")
    
    occurrences = 0
    i = 0
    while i <= len(source_lines) - len(search_lines_stripped):
        window = source_lines[i:i + len(search_lines_stripped)]
        window_stripped = [line.strip() for line in window]
        
        if window_stripped == search_lines_stripped:
            occurrences += 1
            # Get indentation from first matched line
            first_line = window[0]
            indent_match = re.match(r"^(\s*)", first_line)
            indentation = indent_match.group(1) if indent_match else ""
            
            # Apply indentation to replacement
            new_block = [indentation + line for line in replace_lines]
            source_lines[i:i + len(search_lines_stripped)] = new_block
            i += len(replace_lines)
        else:
            i += 1
    
    if occurrences > 0:
        modified = "\n".join(source_lines)
        modified = _restore_trailing_newline(content, modified)
        return modified, occurrences
    return None


def _calculate_regex_replacement(content: str, old_string: str, new_string: str) -> tuple[str, int] | None:
    """Try regex-based flexible replacement."""
    normalized_old = old_string.replace("\r\n", "\n")
    normalized_new = new_string.replace("\r\n", "\n")
    
    # Build flexible regex pattern
    delimiters = ["(", ")", ":", "[", "]", "{", "}", ">", "<", "="]
    processed = normalized_old
    for delim in delimiters:
        processed = processed.replace(delim, f" {delim} ")
    
    tokens = [t for t in processed.split() if t]
    if not tokens:
        return None
    
    escaped_tokens = [re.escape(t) for t in tokens]
    pattern_str = r"\s*".join(escaped_tokens)
    final_pattern = r"^(\s*)" + pattern_str
    
    try:
        regex = re.compile(final_pattern, re.MULTILINE)
        match = regex.search(content)
        
        if not match:
            return None
        
        indentation = match.group(1) or ""
        new_lines = normalized_new.split("\n")
        new_block = "\n".join(indentation + line for line in new_lines)
        
        modified = regex.sub(new_block, content, count=1)
        modified = _restore_trailing_newline(content, modified)
        return modified, 1
        
    except re.error:
        return None


def _generate_diff(original: str, modified: str, file_path: str) -> str:
    """Generate unified diff."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{os.path.basename(file_path)}",
        tofile=f"b/{os.path.basename(file_path)}",
    )
    return "".join(diff)


def replace(
    file_path: str,
    instruction: str,
    old_string: str,
    new_string: str,
    expected_replacements: int | None = None,
) -> str:
    """
    Replaces text within a file.
    
    By default, replaces a single occurrence, but can replace multiple occurrences
    when `expected_replacements` is specified.
    
    Supports three matching strategies:
    1. Exact matching
    2. Flexible whitespace matching
    3. Regex-based matching
    
    Args:
        file_path: The path to the file to modify
        instruction: A clear instruction for what needs to be changed
        old_string: The exact literal text to replace
        new_string: The replacement text
        expected_replacements: Number of replacements expected (default 1)
        
    Returns:
        JSON string with operation result
    """
    try:
        # Resolve path
        resolved_path = os.path.abspath(file_path)
        expected = expected_replacements if expected_replacements is not None else 1
        
        # Validate input
        if old_string == new_string:
            return json.dumps({
                "success": False,
                "error": "No changes to apply. The old_string and new_string are identical.",
                "type": "EDIT_NO_CHANGE",
            })
        
        # Check if creating new file
        is_new_file = old_string == "" and not os.path.exists(resolved_path)
        
        if is_new_file:
            # Create new file
            parent = os.path.dirname(resolved_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(new_string)
            
            return json.dumps({
                "success": True,
                "operation": "create",
                "file_path": file_path,
                "message": f"Created new file: {file_path} with provided content.",
                "num_lines": len(new_string.splitlines()),
            })
        
        # File must exist for update/remove operations
        if not os.path.exists(resolved_path):
            return json.dumps({
                "success": False,
                "error": f"File not found: {file_path}",
                "type": "FILE_NOT_FOUND",
            })
        
        # Cannot create existing file
        if old_string == "":
            return json.dumps({
                "success": False,
                "error": f"File already exists, cannot create: {file_path}. Use non-empty old_string to edit.",
                "type": "FILE_EXISTS",
            })
        
        # Read current content
        encoding = _detect_encoding(resolved_path)
        try:
            with open(resolved_path, encoding=encoding) as f:
                current_content = f.read()
        except UnicodeDecodeError:
            with open(resolved_path, encoding="latin-1") as f:
                current_content = f.read()
        
        # Normalize content for processing
        normalized_content = current_content.replace("\r\n", "\n")
        original_line_ending = _detect_line_ending(current_content)
        
        # Try replacement strategies in order
        result = _calculate_exact_replacement(normalized_content, old_string, new_string)
        strategy = "exact"
        
        if result is None:
            result = _calculate_flexible_replacement(normalized_content, old_string, new_string)
            strategy = "flexible"
        
        if result is None:
            result = _calculate_regex_replacement(normalized_content, old_string, new_string)
            strategy = "regex"
        
        if result is None:
            return json.dumps({
                "success": False,
                "error": (
                    f"Failed to edit, 0 occurrences found for old_string in {file_path}. "
                    "Ensure you're not escaping content incorrectly and check whitespace, indentation, and context. "
                    "Use read_file tool to verify."
                ),
                "type": "EDIT_NO_OCCURRENCE_FOUND",
            })
        
        new_content, occurrences = result
        
        # Validate occurrence count
        if occurrences != expected:
            return json.dumps({
                "success": False,
                "error": f"Expected {expected} occurrence(s) but found {occurrences}.",
                "type": "EDIT_OCCURRENCE_MISMATCH",
                "occurrences_found": occurrences,
            })
        
        # Restore original line endings
        if original_line_ending == "\r\n":
            new_content = new_content.replace("\n", "\r\n")
        
        # Write updated content
        with open(resolved_path, "w", encoding=encoding, newline="") as f:
            f.write(new_content)
        
        # Generate diff
        diff = _generate_diff(current_content, new_content, file_path)
        
        result_data: dict[str, Any] = {
            "success": True,
            "operation": "update",
            "file_path": file_path,
            "message": f"Successfully modified file: {file_path} ({occurrences} replacement(s)).",
            "occurrences": occurrences,
            "strategy": strategy,
            "num_lines": len(new_content.splitlines()),
        }
        
        if diff:
            result_data["diff"] = diff
        
        return json.dumps(result_data, ensure_ascii=False)
        
    except PermissionError:
        return json.dumps({
            "success": False,
            "error": f"Permission denied: {file_path}",
            "type": "PERMISSION_DENIED",
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error editing file: {str(e)}",
            "type": "EDIT_ERROR",
        })

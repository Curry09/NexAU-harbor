# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
list_directory tool - Lists files and subdirectories in a directory.

Based on gemini-cli's ls.ts implementation.
"""

import fnmatch
import os
from typing import Any


def _should_ignore(filename: str, patterns: list[str] | None) -> bool:
    """Check if filename matches any ignore pattern."""
    if not patterns:
        return False
    
    for pattern in patterns:
        # Convert glob pattern to fnmatch pattern
        regex_pattern = pattern.replace(".", r"\.").replace("*", ".*").replace("?", ".")
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def list_directory(
    dir_path: str,
    ignore: list[str] | None = None,
    file_filtering_options: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """
    Lists files and subdirectories in a directory.
    
    Results are sorted with directories first, then alphabetically.
    Can optionally ignore entries matching provided glob patterns.
    
    Args:
        dir_path: Path to the directory to list
        ignore: List of glob patterns to ignore
        file_filtering_options: Options for respecting .gitignore/.geminiignore
        
    Returns:
        Dict with llmContent and returnDisplay matching gemini-cli format
    """
    try:
        # Resolve path
        resolved_path = os.path.abspath(dir_path)
        
        # Check if path exists
        if not os.path.exists(resolved_path):
            error_msg = f"Error: Directory not found or inaccessible: {resolved_path}"
            return {
                "llmContent": error_msg,
                "returnDisplay": "Directory not found or inaccessible.",
                "error": {
                    "message": error_msg,
                    "type": "FILE_NOT_FOUND",
                },
            }
        
        # Check if it's a directory
        if not os.path.isdir(resolved_path):
            error_msg = f"Error: Path is not a directory: {resolved_path}"
            return {
                "llmContent": error_msg,
                "returnDisplay": "Path is not a directory.",
                "error": {
                    "message": error_msg,
                    "type": "PATH_IS_NOT_A_DIRECTORY",
                },
            }
        
        # Build ignore patterns
        ignore_patterns = list(ignore) if ignore else []
        
        # Parse file_filtering_options
        respect_git_ignore = True
        respect_gemini_ignore = True
        if file_filtering_options:
            respect_git_ignore = file_filtering_options.get("respect_git_ignore", True)
            respect_gemini_ignore = file_filtering_options.get("respect_gemini_ignore", True)
        
        # Read .gitignore if requested
        if respect_git_ignore:
            gitignore_path = os.path.join(resolved_path, ".gitignore")
            if os.path.exists(gitignore_path):
                try:
                    with open(gitignore_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                ignore_patterns.append(line.rstrip("/"))
                except IOError:
                    pass
        
        # Read .geminiignore if requested
        if respect_gemini_ignore:
            geminiignore_path = os.path.join(resolved_path, ".geminiignore")
            if os.path.exists(geminiignore_path):
                try:
                    with open(geminiignore_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                ignore_patterns.append(line.rstrip("/"))
                except IOError:
                    pass
        
        # List directory contents
        try:
            entries = os.listdir(resolved_path)
        except PermissionError:
            error_msg = f"Error: Permission denied: {dir_path}"
            return {
                "llmContent": error_msg,
                "returnDisplay": "Permission denied.",
                "error": {
                    "message": error_msg,
                    "type": "PERMISSION_DENIED",
                },
            }
        
        if not entries:
            return {
                "llmContent": f"Directory {resolved_path} is empty.",
                "returnDisplay": "Directory is empty.",
            }
        
        # Process entries
        directories = []
        files = []
        ignored_count = 0
        
        for entry in entries:
            # Check ignore patterns
            if _should_ignore(entry, ignore_patterns):
                ignored_count += 1
                continue
            
            full_path = os.path.join(resolved_path, entry)
            
            try:
                if os.path.isdir(full_path):
                    directories.append(entry)
                else:
                    files.append(entry)
            except (OSError, PermissionError):
                # Skip entries we can't access
                continue
        
        # Sort: directories first, then files, both alphabetically
        directories.sort(key=str.lower)
        files.sort(key=str.lower)
        
        # Build formatted list
        formatted_entries = []
        for d in directories:
            formatted_entries.append(f"[DIR] {d}")
        for f in files:
            formatted_entries.append(f)
        
        # Create formatted content for LLM (matching gemini-cli format)
        directory_content = "\n".join(formatted_entries)
        
        result_message = f"Directory listing for {resolved_path}:\n{directory_content}"
        if ignored_count > 0:
            result_message += f"\n\n({ignored_count} ignored)"
        
        display_message = f"Listed {len(formatted_entries)} item(s)."
        if ignored_count > 0:
            display_message += f" ({ignored_count} ignored)"
        
        return {
            "llmContent": result_message,
            "returnDisplay": display_message,
        }
        
    except Exception as e:
        error_msg = f"Error listing directory: {str(e)}"
        return {
            "llmContent": error_msg,
            "returnDisplay": "Failed to list directory.",
            "error": {
                "message": error_msg,
                "type": "LS_EXECUTION_ERROR",
            },
        }

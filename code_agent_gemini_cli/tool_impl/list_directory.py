# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
list_directory tool - Lists files and subdirectories in a directory.

Based on gemini-cli's ls.ts implementation.
"""

import fnmatch
import json
import os
from typing import Any


def _should_ignore(filename: str, patterns: list[str] | None) -> bool:
    """Check if filename matches any ignore pattern."""
    if not patterns:
        return False
    
    for pattern in patterns:
        # Convert glob pattern to fnmatch pattern
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def list_directory(
    dir_path: str,
    ignore: list[str] | None = None,
    file_filtering_options: dict[str, bool] | None = None,
) -> str:
    """
    Lists files and subdirectories in a directory.
    
    Results are sorted with directories first, then alphabetically.
    
    Args:
        dir_path: Path to the directory to list
        ignore: List of glob patterns to ignore
        file_filtering_options: Options for respecting .gitignore/.geminiignore
        
    Returns:
        JSON string with directory contents
    """
    try:
        # Resolve path
        resolved_path = os.path.abspath(dir_path)
        
        # Check if path exists
        if not os.path.exists(resolved_path):
            return json.dumps({
                "error": f"Directory not found: {dir_path}",
                "type": "DIRECTORY_NOT_FOUND",
            })
        
        # Check if it's a directory
        if not os.path.isdir(resolved_path):
            return json.dumps({
                "error": f"Path is not a directory: {dir_path}",
                "type": "NOT_A_DIRECTORY",
            })
        
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
            return json.dumps({
                "error": f"Permission denied: {dir_path}",
                "type": "PERMISSION_DENIED",
            })
        
        if not entries:
            return json.dumps({
                "message": f"Directory {dir_path} is empty.",
                "path": dir_path,
                "entries": [],
                "count": 0,
            })
        
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
        
        # Build result
        result: dict[str, Any] = {
            "path": dir_path,
            "entries": formatted_entries,
            "directories": len(directories),
            "files": len(files),
            "count": len(directories) + len(files),
        }
        
        if ignored_count > 0:
            result["ignored"] = ignored_count
            result["message"] = f"Listed {result['count']} item(s). ({ignored_count} ignored)"
        else:
            result["message"] = f"Listed {result['count']} item(s)."
        
        # Add content as formatted string for LLM
        result["content"] = f"Directory listing for {resolved_path}:\n" + "\n".join(formatted_entries)
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error listing directory: {str(e)}",
            "type": "LS_ERROR",
        })

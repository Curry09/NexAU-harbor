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

# Default limit to prevent context overflow (9898 files caused 276K tokens!)
DEFAULT_MAX_ENTRIES = 100
ABSOLUTE_MAX_ENTRIES = 500  # Hard limit even if user requests more


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
    limit: int | None = None,
    offset: int = 0,
) -> str:
    """
    Lists files and subdirectories in a directory.
    
    Results are sorted with directories first, then alphabetically.
    Output is truncated to prevent context overflow.
    
    Args:
        dir_path: Path to the directory to list
        ignore: List of glob patterns to ignore
        file_filtering_options: Options for respecting .gitignore/.geminiignore
        limit: Maximum number of entries to return (default: 100, max: 500)
        offset: Number of entries to skip for pagination (default: 0)
        
    Returns:
        JSON string with directory contents
    """
    # Apply limits to prevent context overflow
    effective_limit = min(
        limit if limit is not None else DEFAULT_MAX_ENTRIES,
        ABSOLUTE_MAX_ENTRIES
    )
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
        
        # Build formatted list (all entries before truncation)
        all_formatted_entries = []
        for d in directories:
            all_formatted_entries.append(f"[DIR] {d}")
        for f in files:
            all_formatted_entries.append(f)
        
        total_count = len(all_formatted_entries)
        
        # Apply pagination/truncation
        start_idx = min(offset, total_count)
        end_idx = min(start_idx + effective_limit, total_count)
        formatted_entries = all_formatted_entries[start_idx:end_idx]
        
        is_truncated = end_idx < total_count
        
        # Build result
        result: dict[str, Any] = {
            "path": dir_path,
            "entries": formatted_entries,
            "directories": len(directories),
            "files": len(files),
            "total_count": total_count,
            "returned_count": len(formatted_entries),
            "offset": start_idx,
            "limit": effective_limit,
        }
        
        if is_truncated:
            result["truncated"] = True
            result["remaining"] = total_count - end_idx
            result["next_offset"] = end_idx
            truncation_msg = f" (showing {start_idx+1}-{end_idx} of {total_count}, use offset={end_idx} to see more)"
        else:
            result["truncated"] = False
            truncation_msg = ""
        
        if ignored_count > 0:
            result["ignored"] = ignored_count
            result["message"] = f"Listed {len(formatted_entries)} of {total_count} item(s).{truncation_msg} ({ignored_count} ignored)"
        else:
            result["message"] = f"Listed {len(formatted_entries)} of {total_count} item(s).{truncation_msg}"
        
        # Add content as formatted string for LLM
        content_lines = [f"Directory listing for {resolved_path}:"]
        content_lines.extend(formatted_entries)
        if is_truncated:
            content_lines.append(f"\n... and {total_count - end_idx} more entries (use offset={end_idx} to continue)")
        result["content"] = "\n".join(content_lines)
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error listing directory: {str(e)}",
            "type": "LS_ERROR",
        })

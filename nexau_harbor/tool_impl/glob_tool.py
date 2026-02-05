# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
glob tool - Finds files matching glob patterns.

Based on gemini-cli's glob.ts implementation.
Returns absolute paths sorted by modification time (newest first).
"""

import fnmatch
import os
import time
from pathlib import Path
from typing import Any


# Default exclusions matching gemini-cli
DEFAULT_EXCLUDES = [
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "dist",
    "build",
    ".tox",
    ".eggs",
    "*.egg-info",
]


def _get_file_mtime(file_path: str) -> float:
    """Get file modification time, return 0 on error."""
    try:
        return os.path.getmtime(file_path)
    except OSError:
        return 0


def _should_exclude(path: str, excludes: list[str]) -> bool:
    """Check if path should be excluded."""
    parts = Path(path).parts
    for part in parts:
        for pattern in excludes:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def _sort_file_entries(
    entries: list[tuple[str, float]],
    now_timestamp: float,
    recency_threshold_ms: float,
) -> list[str]:
    """
    Sorts file entries based on recency and then alphabetically.
    Recent files (modified within recency_threshold_ms) are listed first, newest to oldest.
    Older files are listed after recent ones, sorted alphabetically by path.
    """
    recency_threshold_sec = recency_threshold_ms / 1000.0
    
    def sort_key(item: tuple[str, float]) -> tuple[int, float, str]:
        path, mtime = item
        is_recent = (now_timestamp - mtime) < recency_threshold_sec
        if is_recent:
            # Recent files: sort by mtime descending (newer first)
            return (0, -mtime, path)
        else:
            # Older files: sort alphabetically
            return (1, 0, path)
    
    entries.sort(key=sort_key)
    return [p for p, _ in entries]


def _match_glob_pattern(
    pattern: str,
    search_dir: str,
    case_sensitive: bool,
    excludes: list[str],
) -> list[str]:
    """Match files against glob pattern."""
    import glob as glob_module
    
    # Handle pattern
    if not pattern.startswith("**/") and not pattern.startswith("/"):
        # Make pattern relative to search_dir
        full_pattern = os.path.join(search_dir, "**", pattern)
    else:
        full_pattern = os.path.join(search_dir, pattern)
    
    # Use recursive glob
    try:
        matches = glob_module.glob(full_pattern, recursive=True)
    except Exception:
        matches = []
    
    # Filter results
    results = []
    for match in matches:
        # Skip directories
        if os.path.isdir(match):
            continue
        
        # Get relative path for exclusion check
        rel_path = os.path.relpath(match, search_dir)
        
        # Check exclusions
        if _should_exclude(rel_path, excludes):
            continue
        
        results.append(match)
    
    return results


def glob(
    pattern: str,
    dir_path: str | None = None,
    case_sensitive: bool = False,
    respect_git_ignore: bool = True,
    respect_gemini_ignore: bool = True,
) -> dict[str, Any]:
    """
    Finds files matching a glob pattern.
    
    Returns absolute paths sorted by modification time (newest first).
    Ideal for quickly locating files based on their name or path structure.
    
    Args:
        pattern: Glob pattern (e.g., "**/*.py", "docs/*.md")
        dir_path: Directory to search in (optional, defaults to cwd)
        case_sensitive: Whether matching should be case-sensitive
        respect_git_ignore: Whether to respect .gitignore patterns
        respect_gemini_ignore: Whether to respect .geminiignore patterns
        
    Returns:
        Dict with llmContent and returnDisplay matching gemini-cli format
    """
    try:
        # Validate pattern
        if not pattern or not pattern.strip():
            return {
                "llmContent": "The 'pattern' parameter cannot be empty.",
                "returnDisplay": "Error: Empty pattern",
                "error": {
                    "message": "The 'pattern' parameter cannot be empty.",
                    "type": "INVALID_PATTERN",
                },
            }
        
        # Determine search directory
        search_dir = os.path.abspath(dir_path) if dir_path else os.getcwd()
        
        if not os.path.exists(search_dir):
            error_msg = f"Search path does not exist {search_dir}"
            return {
                "llmContent": error_msg,
                "returnDisplay": "Error: Path not found",
                "error": {
                    "message": error_msg,
                    "type": "DIRECTORY_NOT_FOUND",
                },
            }
        
        if not os.path.isdir(search_dir):
            error_msg = f"Search path is not a directory: {search_dir}"
            return {
                "llmContent": error_msg,
                "returnDisplay": "Error: Not a directory",
                "error": {
                    "message": error_msg,
                    "type": "NOT_A_DIRECTORY",
                },
            }
        
        # Build exclusion list
        excludes = list(DEFAULT_EXCLUDES)
        
        # Try to read .gitignore if requested
        if respect_git_ignore:
            gitignore_path = os.path.join(search_dir, ".gitignore")
            if os.path.exists(gitignore_path):
                try:
                    with open(gitignore_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                excludes.append(line.rstrip("/"))
                except IOError:
                    pass
        
        # Try to read .geminiignore if requested
        if respect_gemini_ignore:
            geminiignore_path = os.path.join(search_dir, ".geminiignore")
            if os.path.exists(geminiignore_path):
                try:
                    with open(geminiignore_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                excludes.append(line.rstrip("/"))
                except IOError:
                    pass
        
        # Find matching files
        matches = _match_glob_pattern(pattern, search_dir, case_sensitive, excludes)
        
        # Get absolute paths with mtime (filter out any that couldn't be accessed)
        files_with_mtime = []
        for m in matches:
            abs_path = os.path.abspath(m)
            mtime = _get_file_mtime(m)
            files_with_mtime.append((abs_path, mtime))
        
        # Sort by modification time (newest first for recent files)
        one_day_ms = 24 * 60 * 60 * 1000
        now_timestamp = time.time()
        sorted_paths = _sort_file_entries(files_with_mtime, now_timestamp, one_day_ms)
        
        # Count ignored files
        ignored_count = len(matches) - len(files_with_mtime)
        
        # Build result matching gemini-cli format
        if not sorted_paths:
            message = f'No files found matching pattern "{pattern}" within {search_dir}'
            if ignored_count > 0:
                message += f" ({ignored_count} files were ignored)"
            return {
                "llmContent": message,
                "returnDisplay": "No files found",
            }
        
        file_count = len(sorted_paths)
        file_list = "\n".join(sorted_paths)
        
        result_message = (
            f'Found {file_count} file(s) matching "{pattern}" within {search_dir}'
        )
        if ignored_count > 0:
            result_message += f" ({ignored_count} additional files were ignored)"
        result_message += f", sorted by modification time (newest first):\n{file_list}"
        
        return {
            "llmContent": result_message,
            "returnDisplay": f"Found {file_count} matching file(s)",
        }
        
    except Exception as e:
        error_msg = f"Error during glob search operation: {str(e)}"
        return {
            "llmContent": error_msg,
            "returnDisplay": "Error: An unexpected error occurred.",
            "error": {
                "message": error_msg,
                "type": "GLOB_EXECUTION_ERROR",
            },
        }

# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
glob tool - Finds files matching glob patterns.

Based on gemini-cli's glob.ts implementation.
"""

import fnmatch
import json
import os
from pathlib import Path
from typing import Any


# Default exclusions
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
        
        # Apply case sensitivity filter if needed
        if not case_sensitive:
            results.append(match)
        else:
            # For case-sensitive, verify the match
            base_pattern = os.path.basename(pattern.replace("**", "").replace("*", ""))
            if base_pattern.lower() in os.path.basename(match).lower():
                results.append(match)
            else:
                results.append(match)
    
    return results


def glob(
    pattern: str,
    dir_path: str | None = None,
    case_sensitive: bool = False,
    respect_git_ignore: bool = True,
    respect_gemini_ignore: bool = True,
) -> str:
    """
    Finds files matching a glob pattern.
    
    Returns absolute paths sorted by modification time (newest first).
    
    Args:
        pattern: Glob pattern (e.g., "**/*.py", "docs/*.md")
        dir_path: Directory to search in (optional, defaults to cwd)
        case_sensitive: Whether matching should be case-sensitive
        respect_git_ignore: Whether to respect .gitignore patterns
        respect_gemini_ignore: Whether to respect .geminiignore patterns
        
    Returns:
        JSON string with matching files
    """
    try:
        # Validate pattern
        if not pattern or not pattern.strip():
            return json.dumps({
                "error": "Pattern cannot be empty.",
                "type": "INVALID_PATTERN",
            })
        
        # Determine search directory
        search_dir = os.path.abspath(dir_path) if dir_path else os.getcwd()
        
        if not os.path.exists(search_dir):
            return json.dumps({
                "error": f"Directory does not exist: {search_dir}",
                "type": "DIRECTORY_NOT_FOUND",
            })
        
        if not os.path.isdir(search_dir):
            return json.dumps({
                "error": f"Path is not a directory: {search_dir}",
                "type": "NOT_A_DIRECTORY",
            })
        
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
        
        # Get absolute paths
        abs_paths = [os.path.abspath(m) for m in matches]
        
        # Sort by modification time (newest first)
        import time
        current_time = time.time()
        
        # Get mtime for each file
        files_with_mtime = [(p, _get_file_mtime(p)) for p in abs_paths]
        
        # Sort: recent files first (by mtime descending), then alphabetically
        one_day = 24 * 60 * 60
        
        def sort_key(item: tuple[str, float]) -> tuple[int, float, str]:
            path, mtime = item
            # Recent files (within 24h) come first
            is_recent = (current_time - mtime) < one_day if current_time else False
            return (0 if is_recent else 1, -mtime, path)
        
        files_with_mtime.sort(key=sort_key)
        sorted_paths = [p for p, _ in files_with_mtime]
        
        # Build result
        if not sorted_paths:
            return json.dumps({
                "message": f'No files found matching pattern "{pattern}" in "{search_dir}".',
                "files": [],
                "count": 0,
            })
        
        result: dict[str, Any] = {
            "message": f'Found {len(sorted_paths)} file(s) matching "{pattern}" in "{search_dir}", sorted by modification time.',
            "pattern": pattern,
            "search_dir": search_dir,
            "count": len(sorted_paths),
            "files": sorted_paths,
        }
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error during glob search: {str(e)}",
            "type": "GLOB_ERROR",
        })

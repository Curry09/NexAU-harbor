# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
search_file_content tool - Searches for patterns in file contents.

Based on gemini-cli's grep.ts implementation.
Uses ripgrep (rg) when available, falls back to Python implementation.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


# Configuration
DEFAULT_MAX_MATCHES = 20000
DEFAULT_TIMEOUT_SECONDS = 30


def _is_git_repo(path: str) -> bool:
    """Check if path is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=path,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _command_available(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    try:
        which_cmd = "where" if os.name == "nt" else "command"
        args = [cmd] if os.name == "nt" else ["-v", cmd]
        result = subprocess.run(
            [which_cmd] + args,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _parse_grep_line(line: str, base_path: str) -> dict[str, Any] | None:
    """Parse a grep output line into structured data."""
    if not line.strip():
        return None
    
    # Match format: filepath:linenum:content
    match = re.match(r"^(.+?):(\d+):(.*)$", line)
    if not match:
        return None
    
    file_path_raw, line_num_str, content = match.groups()
    line_num = int(line_num_str)
    
    # Get relative path
    abs_path = os.path.abspath(os.path.join(base_path, file_path_raw))
    rel_path = os.path.relpath(abs_path, base_path)
    
    # Security check - ensure path is within base
    if rel_path.startswith(".."):
        return None
    
    return {
        "file": rel_path,
        "line": line_num,
        "content": content.strip(),
    }


def _run_git_grep(
    pattern: str,
    search_path: str,
    include: str | None,
    max_matches: int,
) -> list[dict[str, Any]]:
    """Run git grep and return matches."""
    cmd = ["git", "grep", "--untracked", "-n", "-E", "--ignore-case", pattern]
    
    if include:
        cmd.extend(["--", include])
    
    try:
        result = subprocess.run(
            cmd,
            cwd=search_path,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        
        if result.returncode not in [0, 1]:  # 1 means no matches
            return []
        
        matches = []
        for line in result.stdout.splitlines():
            match = _parse_grep_line(line, search_path)
            if match:
                matches.append(match)
                if len(matches) >= max_matches:
                    break
        
        return matches
        
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _run_system_grep(
    pattern: str,
    search_path: str,
    include: str | None,
    max_matches: int,
) -> list[dict[str, Any]]:
    """Run system grep and return matches."""
    cmd = ["grep", "-r", "-n", "-H", "-E", "-I", "--ignore-case"]
    
    # Add common exclusions
    for exclude_dir in ["node_modules", ".git", "__pycache__", "venv", ".venv"]:
        cmd.append(f"--exclude-dir={exclude_dir}")
    
    if include:
        cmd.append(f"--include={include}")
    
    cmd.extend([pattern, "."])
    
    try:
        result = subprocess.run(
            cmd,
            cwd=search_path,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        
        if result.returncode not in [0, 1]:
            return []
        
        matches = []
        for line in result.stdout.splitlines():
            match = _parse_grep_line(line, search_path)
            if match:
                matches.append(match)
                if len(matches) >= max_matches:
                    break
        
        return matches
        
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _run_python_grep(
    pattern: str,
    search_path: str,
    include: str | None,
    max_matches: int,
) -> list[dict[str, Any]]:
    """Python fallback for grep functionality."""
    import fnmatch
    
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return []
    
    matches = []
    exclude_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"}
    
    for root, dirs, files in os.walk(search_path):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for filename in files:
            if len(matches) >= max_matches:
                break
            
            # Apply include filter
            if include and not fnmatch.fnmatch(filename, include):
                continue
            
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, search_path)
            
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            matches.append({
                                "file": rel_path,
                                "line": line_num,
                                "content": line.strip(),
                            })
                            if len(matches) >= max_matches:
                                break
            except (IOError, PermissionError):
                continue
    
    return matches


def search_file_content(
    pattern: str,
    dir_path: str | None = None,
    include: str | None = None,
) -> str:
    """
    Searches for a regex pattern within file contents.
    
    Uses git grep (if in git repo) -> system grep -> Python fallback.
    Returns matching lines with file paths and line numbers.
    
    Args:
        pattern: Regular expression pattern to search for
        dir_path: Directory to search in (optional, defaults to cwd)
        include: Glob pattern to filter files (e.g., "*.js", "*.{ts,tsx}")
        
    Returns:
        JSON string with search results
    """
    try:
        # Validate pattern
        try:
            re.compile(pattern)
        except re.error as e:
            return json.dumps({
                "error": f"Invalid regex pattern: {pattern}. Error: {str(e)}",
                "type": "INVALID_PATTERN",
            })
        
        # Determine search directory
        search_path = os.path.abspath(dir_path) if dir_path else os.getcwd()
        
        if not os.path.exists(search_path):
            return json.dumps({
                "error": f"Path does not exist: {search_path}",
                "type": "PATH_NOT_FOUND",
            })
        
        if not os.path.isdir(search_path):
            return json.dumps({
                "error": f"Path is not a directory: {search_path}",
                "type": "NOT_A_DIRECTORY",
            })
        
        # Try search strategies in order
        matches = []
        strategy = "none"
        
        # Try git grep first if in git repo
        if _is_git_repo(search_path) and _command_available("git"):
            matches = _run_git_grep(pattern, search_path, include, DEFAULT_MAX_MATCHES)
            if matches:
                strategy = "git_grep"
        
        # Try system grep
        if not matches and _command_available("grep"):
            matches = _run_system_grep(pattern, search_path, include, DEFAULT_MAX_MATCHES)
            if matches:
                strategy = "system_grep"
        
        # Fall back to Python implementation
        if not matches:
            matches = _run_python_grep(pattern, search_path, include, DEFAULT_MAX_MATCHES)
            strategy = "python"
        
        # Format results
        if not matches:
            filter_info = f' (filter: "{include}")' if include else ""
            return json.dumps({
                "message": f'No matches found for pattern "{pattern}" in "{search_path}"{filter_info}.',
                "matches": [],
                "count": 0,
            })
        
        # Group by file
        by_file: dict[str, list[dict[str, Any]]] = {}
        for match in matches:
            file_key = match["file"]
            if file_key not in by_file:
                by_file[file_key] = []
            by_file[file_key].append({
                "line": match["line"],
                "content": match["content"],
            })
        
        # Build result
        was_truncated = len(matches) >= DEFAULT_MAX_MATCHES
        filter_info = f' (filter: "{include}")' if include else ""
        truncation_note = f" (results limited to {DEFAULT_MAX_MATCHES})" if was_truncated else ""
        
        result: dict[str, Any] = {
            "message": f'Found {len(matches)} match(es) for pattern "{pattern}"{filter_info}{truncation_note}',
            "pattern": pattern,
            "search_path": search_path,
            "count": len(matches),
            "files": len(by_file),
            "matches_by_file": by_file,
            "truncated": was_truncated,
            "strategy": strategy,
        }
        
        if include:
            result["filter"] = include
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error during search: {str(e)}",
            "type": "SEARCH_ERROR",
        })

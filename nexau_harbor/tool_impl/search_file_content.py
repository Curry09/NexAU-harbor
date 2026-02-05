# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
search_file_content tool (grep) - Searches for regex patterns in file contents.

Based on gemini-cli's grep.ts implementation.
Uses prioritized strategies: git grep -> system grep -> JavaScript fallback.
"""

import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


# Configuration constants
DEFAULT_TOTAL_MAX_MATCHES = 500
DEFAULT_SEARCH_TIMEOUT_MS = 30000
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
]


def _is_command_available(command: str) -> bool:
    """Check if a command is available in the system PATH."""
    return shutil.which(command) is not None


def _is_git_repository(path: str) -> bool:
    """Check if the path is within a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def _parse_grep_line(line: str, base_path: str) -> dict | None:
    """
    Parse a single line of grep-like output.
    Expects format: filePath:lineNumber:lineContent
    """
    if not line.strip():
        return None
    
    # Use regex to locate the first occurrence of :<digits>:
    match = re.match(r"^(.+?):(\d+):(.*)$", line)
    if not match:
        return None
    
    file_path_raw, line_number_str, line_content = match.groups()
    
    try:
        line_number = int(line_number_str)
    except ValueError:
        return None
    
    # Resolve and validate path
    absolute_path = os.path.abspath(os.path.join(base_path, file_path_raw))
    relative_path = os.path.relpath(absolute_path, base_path)
    
    # Security check - ensure path doesn't escape base
    if relative_path.startswith("..") or os.path.isabs(relative_path):
        return None
    
    return {
        "filePath": relative_path or os.path.basename(absolute_path),
        "lineNumber": line_number,
        "line": line_content,
    }


def _git_grep(
    pattern: str,
    search_path: str,
    include: str | None,
    max_matches: int,
) -> list[dict] | None:
    """
    Execute git grep search.
    Returns list of matches or None if git grep fails/unavailable.
    """
    if not _is_command_available("git"):
        return None
    
    if not _is_git_repository(search_path):
        return None
    
    args = ["git", "grep", "--untracked", "-n", "-E", "--ignore-case", pattern]
    if include:
        args.extend(["--", include])
    
    try:
        result = subprocess.run(
            args,
            cwd=search_path,
            capture_output=True,
            text=True,
            timeout=DEFAULT_SEARCH_TIMEOUT_MS / 1000,
        )
        
        # Exit code 0 = matches found, 1 = no matches, other = error
        if result.returncode not in (0, 1):
            return None
        
        matches = []
        for line in result.stdout.splitlines():
            parsed = _parse_grep_line(line, search_path)
            if parsed:
                matches.append(parsed)
                if len(matches) >= max_matches:
                    break
        
        return matches
        
    except (subprocess.TimeoutExpired, Exception):
        return None


def _system_grep(
    pattern: str,
    search_path: str,
    include: str | None,
    max_matches: int,
    excludes: list[str],
) -> list[dict] | None:
    """
    Execute system grep search.
    Returns list of matches or None if grep fails/unavailable.
    """
    if not _is_command_available("grep"):
        return None
    
    args = ["grep", "-r", "-n", "-H", "-E", "-I"]
    
    # Add exclude directories
    for exclude in excludes:
        # Only use directory excludes
        if not exclude.startswith("*"):
            args.append(f"--exclude-dir={exclude}")
    
    # Add include pattern
    if include:
        args.append(f"--include={include}")
    
    args.append(pattern)
    args.append(".")
    
    try:
        result = subprocess.run(
            args,
            cwd=search_path,
            capture_output=True,
            text=True,
            timeout=DEFAULT_SEARCH_TIMEOUT_MS / 1000,
        )
        
        # Exit code 0 = matches found, 1 = no matches
        if result.returncode not in (0, 1):
            return None
        
        matches = []
        for line in result.stdout.splitlines():
            parsed = _parse_grep_line(line, search_path)
            if parsed:
                matches.append(parsed)
                if len(matches) >= max_matches:
                    break
        
        return matches
        
    except (subprocess.TimeoutExpired, Exception):
        return None


def _python_grep(
    pattern: str,
    search_path: str,
    include: str | None,
    max_matches: int,
    excludes: list[str],
) -> list[dict]:
    """
    Pure Python grep implementation as fallback.
    """
    matches = []
    
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return matches
    
    def should_exclude(path: str) -> bool:
        """Check if path should be excluded."""
        parts = Path(path).parts
        for part in parts:
            for exclude in excludes:
                if fnmatch.fnmatch(part, exclude):
                    return True
        return False
    
    def matches_include(filename: str) -> bool:
        """Check if filename matches include pattern."""
        if not include:
            return True
        return fnmatch.fnmatch(filename, include)
    
    for root, dirs, files in os.walk(search_path):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in excludes]
        
        rel_root = os.path.relpath(root, search_path)
        if should_exclude(rel_root):
            continue
        
        for filename in files:
            if len(matches) >= max_matches:
                return matches
            
            if not matches_include(filename):
                continue
            
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, search_path)
            
            if should_exclude(rel_path):
                continue
            
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        if len(matches) >= max_matches:
                            return matches
                        
                        if regex.search(line):
                            matches.append({
                                "filePath": rel_path,
                                "lineNumber": line_num,
                                "line": line.rstrip("\n\r"),
                            })
            except (IOError, PermissionError):
                continue
    
    return matches


def search_file_content(
    pattern: str,
    dir_path: str | None = None,
    include: str | None = None,
) -> dict[str, Any]:
    """
    Searches for a regular expression pattern within file contents.
    
    Uses a prioritized strategy:
    1. git grep (if in git repository)
    2. System grep (if available)
    3. Pure Python fallback
    
    Returns lines containing matches with file paths and line numbers.
    
    Args:
        pattern: The regular expression pattern to search for
        dir_path: Directory to search in (optional, defaults to cwd)
        include: Glob pattern to filter files (e.g., "*.js", "*.{ts,tsx}")
        
    Returns:
        Dict with llmContent and returnDisplay matching gemini-cli format
    """
    try:
        # Validate pattern
        try:
            re.compile(pattern)
        except re.error as e:
            error_msg = f"Invalid regular expression pattern: {pattern}. Error: {str(e)}"
            return {
                "llmContent": error_msg,
                "returnDisplay": "Error: Invalid regex pattern.",
                "error": {
                    "message": error_msg,
                    "type": "INVALID_PATTERN",
                },
            }
        
        # Determine search directory
        if dir_path:
            search_path = os.path.abspath(dir_path)
            
            if not os.path.exists(search_path):
                error_msg = f"Path does not exist: {search_path}"
                return {
                    "llmContent": error_msg,
                    "returnDisplay": "Error: Path does not exist.",
                    "error": {
                        "message": error_msg,
                        "type": "FILE_NOT_FOUND",
                    },
                }
            
            if not os.path.isdir(search_path):
                error_msg = f"Path is not a directory: {search_path}"
                return {
                    "llmContent": error_msg,
                    "returnDisplay": "Error: Path is not a directory.",
                    "error": {
                        "message": error_msg,
                        "type": "PATH_IS_NOT_A_DIRECTORY",
                    },
                }
        else:
            search_path = os.getcwd()
        
        search_dir_display = dir_path or "."
        
        # Try search strategies in order
        max_matches = DEFAULT_TOTAL_MAX_MATCHES
        matches = None
        strategy_used = "none"
        
        # Strategy 1: git grep
        matches = _git_grep(pattern, search_path, include, max_matches)
        if matches is not None:
            strategy_used = "git grep"
        
        # Strategy 2: system grep
        if matches is None:
            matches = _system_grep(
                pattern, search_path, include, max_matches, DEFAULT_EXCLUDES
            )
            if matches is not None:
                strategy_used = "system grep"
        
        # Strategy 3: Python fallback
        if matches is None:
            matches = _python_grep(
                pattern, search_path, include, max_matches, DEFAULT_EXCLUDES
            )
            strategy_used = "python fallback"
        
        # Build location description
        search_location = f'in path "{search_dir_display}"'
        filter_desc = f' (filter: "{include}")' if include else ""
        
        # No matches found
        if not matches:
            no_match_msg = (
                f'No matches found for pattern "{pattern}" {search_location}{filter_desc}.'
            )
            return {
                "llmContent": no_match_msg,
                "returnDisplay": "No matches found",
            }
        
        # Check if results were truncated
        was_truncated = len(matches) >= max_matches
        
        # Group matches by file
        matches_by_file: dict[str, list[dict]] = {}
        for match in matches:
            file_key = match["filePath"]
            if file_key not in matches_by_file:
                matches_by_file[file_key] = []
            matches_by_file[file_key].append(match)
        
        # Sort matches within each file by line number
        for file_matches in matches_by_file.values():
            file_matches.sort(key=lambda m: m["lineNumber"])
        
        # Build result
        match_count = len(matches)
        match_term = "match" if match_count == 1 else "matches"
        
        truncation_note = (
            f" (results limited to {max_matches} matches for performance)"
            if was_truncated
            else ""
        )
        
        llm_content = (
            f'Found {match_count} {match_term} for pattern "{pattern}" '
            f'{search_location}{filter_desc}{truncation_note}:\n---\n'
        )
        
        for file_path, file_matches in matches_by_file.items():
            llm_content += f"File: {file_path}\n"
            for match in file_matches:
                trimmed_line = match["line"].strip()
                llm_content += f"L{match['lineNumber']}: {trimmed_line}\n"
            llm_content += "---\n"
        
        return {
            "llmContent": llm_content.strip(),
            "returnDisplay": f"Found {match_count} {match_term}{' (limited)' if was_truncated else ''}",
        }
        
    except Exception as e:
        error_msg = f"Error during grep search operation: {str(e)}"
        return {
            "llmContent": error_msg,
            "returnDisplay": f"Error: {str(e)}",
            "error": {
                "message": error_msg,
                "type": "GREP_EXECUTION_ERROR",
            },
        }

# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
read_many_files tool - Reads multiple files matching glob patterns.

Based on gemini-cli's read-many-files.ts implementation.
"""

import fnmatch
import json
import os
from pathlib import Path
from typing import Any
import glob as glob_module


# Configuration
DEFAULT_EXCLUDES = [
    "node_modules/**",
    ".git/**",
    "__pycache__/**",
    "*.pyc",
    "venv/**",
    ".venv/**",
    "dist/**",
    "build/**",
    ".tox/**",
    "*.egg-info/**",
]

MAX_FILE_SIZE = 1024 * 1024  # 1MB per file
MAX_TOTAL_SIZE = 10 * 1024 * 1024  # 10MB total
FILE_SEPARATOR = "--- {filepath} ---"


def _should_exclude(rel_path: str, excludes: list[str]) -> bool:
    """Check if path matches any exclusion pattern."""
    for pattern in excludes:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # Also check path components
        parts = Path(rel_path).parts
        for part in parts:
            if fnmatch.fnmatch(part, pattern.rstrip("/**").rstrip("/*")):
                return True
    return False


def _read_file_content(file_path: str) -> tuple[str, str | None]:
    """Read file content. Returns (content, error)."""
    try:
        # Check file size
        size = os.path.getsize(file_path)
        if size > MAX_FILE_SIZE:
            return "", f"File too large ({size} bytes, max {MAX_FILE_SIZE})"
        
        # Detect if binary
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return "", "Binary file"
        
        # Read as text
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read()
        
        return content, None
        
    except PermissionError:
        return "", "Permission denied"
    except IOError as e:
        return "", f"Read error: {str(e)}"


def read_many_files(
    include: list[str],
    exclude: list[str] | None = None,
    recursive: bool = True,
    useDefaultExcludes: bool = True,
    file_filtering_options: dict[str, bool] | None = None,
) -> str:
    """
    Reads content from multiple files matching glob patterns.
    
    Concatenates text file contents with separators.
    Useful for getting an overview of a codebase or reading related files.
    
    Args:
        include: Array of glob patterns or file paths to include
        exclude: Optional array of patterns to exclude
        recursive: Whether to search recursively (default True)
        useDefaultExcludes: Whether to use default exclusions (default True)
        file_filtering_options: Options for .gitignore/.geminiignore
        
    Returns:
        JSON string with concatenated file contents
    """
    try:
        # Validate input
        if not include or not isinstance(include, list):
            return json.dumps({
                "error": "'include' must be a non-empty array of patterns.",
                "type": "INVALID_INPUT",
            })
        
        # Build exclusion list
        excludes = list(DEFAULT_EXCLUDES) if useDefaultExcludes else []
        if exclude:
            excludes.extend(exclude)
        
        # Get current directory as base
        base_dir = os.getcwd()
        
        # Find all matching files
        all_files: set[str] = set()
        
        for pattern in include:
            # Normalize pattern
            pattern = pattern.replace("\\", "/")
            
            # Make pattern relative to base_dir
            if not os.path.isabs(pattern):
                full_pattern = os.path.join(base_dir, pattern)
            else:
                full_pattern = pattern
            
            # Check if it's an exact file path
            if os.path.isfile(full_pattern):
                all_files.add(full_pattern)
            else:
                # Use glob to find matching files
                matches = glob_module.glob(full_pattern, recursive=recursive)
                for match in matches:
                    if os.path.isfile(match):
                        all_files.add(match)
        
        # Filter out excluded files
        filtered_files = []
        skipped = []
        
        for file_path in sorted(all_files):
            rel_path = os.path.relpath(file_path, base_dir)
            
            if _should_exclude(rel_path, excludes):
                skipped.append({"path": rel_path, "reason": "excluded by pattern"})
                continue
            
            filtered_files.append(file_path)
        
        if not filtered_files:
            return json.dumps({
                "success": False,
                "message": "No files found matching the patterns.",
                "patterns": include,
                "skipped": skipped[:10] if skipped else [],
            })
        
        # Read files
        contents = []
        total_size = 0
        processed = []
        
        for file_path in filtered_files:
            rel_path = os.path.relpath(file_path, base_dir)
            
            # Check total size limit
            if total_size >= MAX_TOTAL_SIZE:
                skipped.append({"path": rel_path, "reason": "total size limit reached"})
                continue
            
            content, error = _read_file_content(file_path)
            
            if error:
                skipped.append({"path": rel_path, "reason": error})
                continue
            
            # Add to contents
            separator = FILE_SEPARATOR.replace("{filepath}", file_path)
            file_content = f"{separator}\n\n{content}\n\n"
            contents.append(file_content)
            total_size += len(content)
            processed.append(rel_path)
        
        if not contents:
            return json.dumps({
                "success": False,
                "message": "No files could be read.",
                "patterns": include,
                "skipped": skipped[:10],
            })
        
        # Combine contents
        combined = "".join(contents)
        combined += "\n--- END OF FILES ---\n"
        
        # Build result
        result: dict[str, Any] = {
            "success": True,
            "files_read": len(processed),
            "total_bytes": total_size,
            "content": combined,
            "processed_files": processed[:20] if len(processed) > 20 else processed,
        }
        
        if len(processed) > 20:
            result["more_files"] = len(processed) - 20
        
        if skipped:
            result["skipped"] = skipped[:10]
            if len(skipped) > 10:
                result["more_skipped"] = len(skipped) - 10
        
        result["message"] = f"Successfully read {len(processed)} file(s), {total_size} bytes total."
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error reading files: {str(e)}",
            "type": "READ_ERROR",
        })

# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
read_file tool - Reads and returns the content of a specified file.

Based on gemini-cli's read-file.ts implementation.
"""

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any


# Configuration constants
DEFAULT_LINE_LIMIT = 2000
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

# Supported media types for binary files
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aiff", ".aac", ".ogg", ".flac"}
PDF_EXTENSION = ".pdf"


def _add_line_numbers(content: str, start_line: int = 1) -> str:
    """Add line numbers to content."""
    lines = content.splitlines()
    if not lines:
        return content
    
    max_line_num = start_line + len(lines) - 1
    width = len(str(max_line_num))
    
    numbered_lines = []
    for i, line in enumerate(lines):
        line_num = start_line + i
        numbered_lines.append(f"{line_num:>{width}}| {line}")
    
    return "\n".join(numbered_lines)


def _detect_encoding(file_path: str) -> str:
    """Detect file encoding with fallback to utf-8."""
    try:
        import chardet
        with open(file_path, "rb") as f:
            raw_data = f.read(10000)
            result = chardet.detect(raw_data)
            if result["encoding"] and result["confidence"] > 0.7:
                return result["encoding"]
    except (ImportError, Exception):
        pass
    return "utf-8"


def _is_binary_file(file_path: str) -> bool:
    """Check if file is a binary file based on extension."""
    ext = Path(file_path).suffix.lower()
    return ext in IMAGE_EXTENSIONS or ext in AUDIO_EXTENSIONS or ext == PDF_EXTENSION


def _read_binary_file(file_path: str) -> dict[str, Any]:
    """Read binary file and return base64 encoded content."""
    ext = Path(file_path).suffix.lower()
    
    with open(file_path, "rb") as f:
        content = f.read()
    
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        if ext in IMAGE_EXTENSIONS:
            mime_type = f"image/{ext[1:]}"
        elif ext in AUDIO_EXTENSIONS:
            mime_type = f"audio/{ext[1:]}"
        elif ext == PDF_EXTENSION:
            mime_type = "application/pdf"
        else:
            mime_type = "application/octet-stream"
    
    return {
        "type": "binary",
        "media_type": mime_type,
        "base64": base64.b64encode(content).decode("utf-8"),
        "size": len(content),
    }


def read_file(
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """
    Reads and returns the content of a specified file.
    
    If the file is large, the content will be truncated. The tool's response
    will clearly indicate if truncation has occurred and will provide details
    on how to read more of the file using the 'offset' and 'limit' parameters.
    
    Handles text, images (PNG, JPG, GIF, WEBP, SVG, BMP), audio files
    (MP3, WAV, AIFF, AAC, OGG, FLAC), and PDF files.
    
    Args:
        file_path: The path to the file to read
        offset: Optional 0-based line number to start reading from
        limit: Optional maximum number of lines to read
        
    Returns:
        JSON string with file content or error
    """
    try:
        # Resolve path
        resolved_path = os.path.abspath(file_path)
        
        # Check if file exists
        if not os.path.exists(resolved_path):
            return json.dumps({
                "error": f"File not found: {file_path}",
                "type": "FILE_NOT_FOUND",
            })
        
        # Check if it's a directory
        if os.path.isdir(resolved_path):
            return json.dumps({
                "error": f"Path is a directory, not a file: {file_path}",
                "type": "PATH_IS_DIRECTORY",
            })
        
        # Check file size
        file_size = os.path.getsize(resolved_path)
        if file_size > MAX_FILE_SIZE_BYTES:
            return json.dumps({
                "error": f"File too large ({file_size} bytes). Maximum size is {MAX_FILE_SIZE_BYTES} bytes.",
                "type": "FILE_TOO_LARGE",
            })
        
        # Handle binary files
        if _is_binary_file(resolved_path):
            result = _read_binary_file(resolved_path)
            result["file_path"] = file_path
            return json.dumps(result)
        
        # Read text file
        encoding = _detect_encoding(resolved_path)
        
        try:
            with open(resolved_path, encoding=encoding) as f:
                all_lines = f.readlines()
        except UnicodeDecodeError:
            # Fallback to latin-1
            with open(resolved_path, encoding="latin-1") as f:
                all_lines = f.readlines()
        
        total_lines = len(all_lines)
        
        # Apply offset and limit
        start_line = offset if offset is not None and offset >= 0 else 0
        end_line = start_line + (limit if limit is not None and limit > 0 else DEFAULT_LINE_LIMIT)
        
        selected_lines = all_lines[start_line:end_line]
        content = "".join(selected_lines)
        lines_shown = len(selected_lines)
        
        # Check if truncated
        is_truncated = end_line < total_lines
        
        # Add line numbers
        content_with_lines = _add_line_numbers(content, start_line + 1)
        
        result: dict[str, Any] = {
            "type": "text",
            "file_path": file_path,
            "content": content_with_lines,
            "lines_shown": [start_line + 1, start_line + lines_shown],
            "total_lines": total_lines,
        }
        
        if is_truncated:
            next_offset = start_line + lines_shown
            result["truncated"] = True
            result["next_offset"] = next_offset
            result["message"] = (
                f"File content has been truncated. "
                f"Showing lines {start_line + 1}-{start_line + lines_shown} of {total_lines} total lines. "
                f"To read more, use offset: {next_offset}."
            )
        
        return json.dumps(result, ensure_ascii=False)
        
    except PermissionError:
        return json.dumps({
            "error": f"Permission denied: {file_path}",
            "type": "PERMISSION_DENIED",
        })
    except Exception as e:
        return json.dumps({
            "error": f"Error reading file: {str(e)}",
            "type": "READ_ERROR",
        })

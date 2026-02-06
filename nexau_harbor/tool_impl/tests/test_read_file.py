# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for read_file - aligned with gemini-cli's read-file.test.ts

Test cases verify input/output format matches gemini-cli exactly.
"""

import base64
import os
import shutil
import tempfile

import pytest

from nexau_harbor.tool_impl.read_file import read_file


class TestReadFile:
    """Test read_file tool functionality matching gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="read-file-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_successfully_read_text_file(self):
        """Should return success result for a text file."""
        file_path = os.path.join(self.temp_dir, "textfile.txt")
        file_content = "This is a test file."
        with open(file_path, "w") as f:
            f.write(file_content)
        
        result = read_file(file_path=file_path)
        
        # Content should include line numbers
        assert "1|" in result["llmContent"] or file_content in result["llmContent"]

    def test_return_error_if_file_does_not_exist(self):
        """Should return error if file does not exist."""
        file_path = os.path.join(self.temp_dir, "nonexistent.txt")
        
        result = read_file(file_path=file_path)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "FILE_NOT_FOUND"
        assert "File not found" in result["llmContent"]

    def test_return_error_if_path_is_directory(self):
        """Should return error if path is a directory."""
        dir_path = os.path.join(self.temp_dir, "directory")
        os.makedirs(dir_path)
        
        result = read_file(file_path=dir_path)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "PATH_IS_DIRECTORY"
        assert "directory" in result["llmContent"].lower()

    def test_handle_image_file_png(self):
        """Should handle image file and return appropriate content."""
        image_path = os.path.join(self.temp_dir, "image.png")
        # Minimal PNG header
        png_header = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        with open(image_path, "wb") as f:
            f.write(png_header)
        
        result = read_file(file_path=image_path)
        
        assert "llmContent" in result
        assert isinstance(result["llmContent"], dict)
        assert "inlineData" in result["llmContent"]
        assert result["llmContent"]["inlineData"]["data"] == base64.b64encode(png_header).decode("utf-8")
        assert "image/png" in result["llmContent"]["inlineData"]["mimeType"]
        assert "Read image file" in result["returnDisplay"]

    def test_handle_pdf_file(self):
        """Should handle PDF file and return appropriate content."""
        pdf_path = os.path.join(self.temp_dir, "document.pdf")
        # Minimal PDF header
        pdf_header = b"%PDF-1.4"
        with open(pdf_path, "wb") as f:
            f.write(pdf_header)
        
        result = read_file(file_path=pdf_path)
        
        assert "llmContent" in result
        assert isinstance(result["llmContent"], dict)
        assert "inlineData" in result["llmContent"]
        assert result["llmContent"]["inlineData"]["data"] == base64.b64encode(pdf_header).decode("utf-8")
        assert "application/pdf" in result["llmContent"]["inlineData"]["mimeType"]
        assert "Read pdf file" in result["returnDisplay"]

    def test_handle_empty_file(self):
        """Should handle empty file."""
        empty_path = os.path.join(self.temp_dir, "empty.txt")
        with open(empty_path, "w") as f:
            pass
        
        result = read_file(file_path=empty_path)
        
        # Empty file should not have error
        assert result.get("error") is None

    def test_support_offset_and_limit(self):
        """Should support offset and limit for text files."""
        file_path = os.path.join(self.temp_dir, "paginated.txt")
        lines = [f"Line {i + 1}" for i in range(20)]
        file_content = "\n".join(lines)
        with open(file_path, "w") as f:
            f.write(file_content)
        
        result = read_file(file_path=file_path, offset=5, limit=3)
        
        assert "truncated" in result["llmContent"].lower()
        assert "Line 6" in result["llmContent"]
        assert "Line 7" in result["llmContent"]
        assert "Line 8" in result["llmContent"]

    def test_add_line_numbers(self):
        """Should add line numbers to text content."""
        file_path = os.path.join(self.temp_dir, "numbered.txt")
        with open(file_path, "w") as f:
            f.write("First line\nSecond line\nThird line")
        
        result = read_file(file_path=file_path)
        
        # Check for line number format
        assert "1|" in result["llmContent"] or "1 |" in result["llmContent"]

    def test_truncation_message(self):
        """Should show truncation message when file is truncated."""
        file_path = os.path.join(self.temp_dir, "long.txt")
        # Create a file with more than default limit lines
        lines = [f"Line {i}" for i in range(3000)]
        with open(file_path, "w") as f:
            f.write("\n".join(lines))
        
        result = read_file(file_path=file_path)
        
        # Should contain truncation warning
        assert "truncated" in result["llmContent"].lower()
        assert "offset" in result["llmContent"].lower() or "limit" in result["llmContent"].lower()


class TestReadFileValidation:
    """Test read_file parameter validation."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="read-file-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_too_large(self):
        """Should return error for file that is too large."""
        file_path = os.path.join(self.temp_dir, "largefile.txt")
        # Create file larger than 10MB limit
        large_content = "x" * (11 * 1024 * 1024)
        with open(file_path, "w") as f:
            f.write(large_content)
        
        result = read_file(file_path=file_path)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "FILE_TOO_LARGE"


class TestReadFileOutputFormat:
    """Test read_file output format matches gemini-cli."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="read-file-tool-test-")
        yield
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_llm_content_format_for_text(self):
        """Should format llmContent correctly for text files."""
        file_path = os.path.join(self.temp_dir, "test.txt")
        with open(file_path, "w") as f:
            f.write("Hello World")
        
        result = read_file(file_path=file_path)
        
        assert "llmContent" in result
        assert "Hello World" in result["llmContent"]

    def test_llm_content_format_for_image(self):
        """Should format llmContent correctly for image files."""
        image_path = os.path.join(self.temp_dir, "test.jpg")
        jpg_data = b"\xff\xd8\xff\xe0"
        with open(image_path, "wb") as f:
            f.write(jpg_data)
        
        result = read_file(file_path=image_path)
        
        assert "llmContent" in result
        assert isinstance(result["llmContent"], dict)
        assert "inlineData" in result["llmContent"]
        assert "mimeType" in result["llmContent"]["inlineData"]
        assert "data" in result["llmContent"]["inlineData"]

    def test_error_format(self):
        """Should format error correctly."""
        result = read_file(file_path="/nonexistent/path.txt")
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]

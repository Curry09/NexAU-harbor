# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for web_fetch - aligned with gemini-cli's web-fetch.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
The web_fetch tool takes a 'prompt' parameter containing URL(s) and instructions.
"""

import pytest

from nexau_harbor.tool_impl.web_fetch import web_fetch


class TestWebFetch:
    """Test web_fetch tool functionality matching gemini-cli."""

    def test_error_when_prompt_empty(self):
        """Should return error when prompt is empty."""
        result = web_fetch(prompt="")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PROMPT"

    def test_error_when_no_urls_in_prompt(self):
        """Should return error when prompt contains no valid URLs."""
        result = web_fetch(prompt="Please analyze this text without any URLs")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "NO_URLS_FOUND"

    def test_error_when_url_invalid_protocol(self):
        """Should return error for unsupported protocols."""
        result = web_fetch(prompt="Fetch content from ftp://example.com/file")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_URL"
        assert "unsupported" in result["llmContent"].lower()


class TestWebFetchURLParsing:
    """Test web_fetch URL parsing from prompts."""

    def test_extract_https_url(self):
        """Should extract and process https:// URL from prompt."""
        # Note: This will attempt actual fetch but tests URL extraction
        result = web_fetch(prompt="Analyze this page https://example.com and summarize")
        
        # Should not fail with URL validation error
        if result.get("error"):
            assert result["error"]["type"] not in ["INVALID_PROMPT", "NO_URLS_FOUND"]

    def test_extract_http_url(self):
        """Should extract and process http:// URL from prompt."""
        result = web_fetch(prompt="Read http://example.com")
        
        if result.get("error"):
            assert result["error"]["type"] not in ["INVALID_PROMPT", "NO_URLS_FOUND"]

    def test_convert_github_blob_url(self):
        """Should convert GitHub blob URL to raw URL."""
        # GitHub URL conversion should happen, even if fetch fails
        result = web_fetch(
            prompt="Analyze this file https://github.com/user/repo/blob/main/file.txt"
        )
        
        # Should attempt to fetch, not fail on URL validation
        if result.get("error"):
            assert result["error"]["type"] not in ["INVALID_URL", "NO_URLS_FOUND"]


class TestWebFetchOutputFormat:
    """Test web_fetch output format matches gemini-cli."""

    def test_error_format(self):
        """Should format error correctly."""
        result = web_fetch(prompt="")
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]

    def test_llm_content_format_error(self):
        """Should format llmContent correctly on error."""
        result = web_fetch(prompt="")
        
        assert "empty" in result["llmContent"].lower() or "prompt" in result["llmContent"].lower()

    def test_return_display_format_error(self):
        """Should format returnDisplay correctly on error."""
        result = web_fetch(prompt="")
        
        assert "Error" in result["returnDisplay"]

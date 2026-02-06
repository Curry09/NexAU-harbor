# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for google_web_search - aligned with gemini-cli's web-search.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
"""

import pytest

from nexau_harbor.tool_impl.google_web_search import google_web_search


class TestGoogleWebSearch:
    """Test google_web_search tool functionality matching gemini-cli."""

    def test_error_when_query_empty(self):
        """Should return error when query is empty."""
        result = google_web_search(query="")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_QUERY"

    def test_error_when_query_whitespace_only(self):
        """Should return error when query is only whitespace."""
        result = google_web_search(query="   ")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_QUERY"

    def test_search_without_function_returns_not_configured(self):
        """Should return not configured error when no search function provided."""
        result = google_web_search(query="test query")
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "WEB_SEARCH_NOT_CONFIGURED"


class TestGoogleWebSearchOutputFormat:
    """Test google_web_search output format matches gemini-cli."""

    def test_error_format(self):
        """Should format error correctly."""
        result = google_web_search(query="")
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]

    def test_llm_content_format_error(self):
        """Should format llmContent correctly on error."""
        result = google_web_search(query="")
        
        assert "query" in result["llmContent"].lower() or "empty" in result["llmContent"].lower()

    def test_return_display_format_error(self):
        """Should format returnDisplay correctly on error."""
        result = google_web_search(query="")
        
        display = result["returnDisplay"]
        assert "Error" in display or "empty" in display.lower()


class TestGoogleWebSearchWithFunction:
    """Test google_web_search with mock search function."""

    def test_successful_search_with_function(self):
        """Should process search results correctly."""
        def mock_search(query):
            return {
                "text": "Python is a programming language.",
                "sources": [],
                "groundingSupports": [],
            }
        
        result = google_web_search(query="python", search_function=mock_search)
        
        assert result.get("error") is None
        assert "Python" in result["llmContent"]

    def test_search_with_sources(self):
        """Should format sources correctly."""
        def mock_search(query):
            return {
                "text": "Python is popular.",
                "sources": [
                    {"web": {"title": "Python.org", "uri": "https://python.org"}},
                ],
                "groundingSupports": [],
            }
        
        result = google_web_search(query="python", search_function=mock_search)
        
        assert result.get("error") is None
        assert "Sources" in result["llmContent"]
        assert "Python.org" in result["llmContent"]

    def test_search_function_error(self):
        """Should handle search function errors gracefully."""
        def mock_search(query):
            raise Exception("Network error")
        
        result = google_web_search(query="test", search_function=mock_search)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "WEB_SEARCH_FAILED"

    def test_empty_search_results(self):
        """Should handle empty search results."""
        def mock_search(query):
            return {"text": "", "sources": [], "groundingSupports": []}
        
        result = google_web_search(query="obscure query", search_function=mock_search)
        
        # Should indicate no results found
        assert "No" in result["llmContent"] or "no" in result["llmContent"]

# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
google_web_search tool - Performs web searches.

Based on gemini-cli's web-search.ts implementation.
Uses external search API or falls back to simulated response.
"""

import json
import os
from typing import Any

# Try to import requests for web searches
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def _search_with_serper(query: str, api_key: str) -> dict[str, Any] | None:
    """Search using Serper API (Google Search API)."""
    if not REQUESTS_AVAILABLE:
        return None
    
    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": 10},
            timeout=30,
        )
        
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    
    return None


def _search_with_duckduckgo(query: str) -> dict[str, Any] | None:
    """Search using DuckDuckGo Instant Answer API."""
    if not REQUESTS_AVAILABLE:
        return None
    
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
            timeout=30,
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("AbstractText") or data.get("RelatedTopics"):
                return data
    except Exception:
        pass
    
    return None


def _format_serper_results(data: dict[str, Any], query: str) -> str:
    """Format Serper API results."""
    parts = [f'Web search results for "{query}":\n']
    
    # Answer box
    if "answerBox" in data:
        ab = data["answerBox"]
        if "answer" in ab:
            parts.append(f"**Answer:** {ab['answer']}\n")
        elif "snippet" in ab:
            parts.append(f"**Snippet:** {ab['snippet']}\n")
    
    # Organic results
    organic = data.get("organic", [])
    if organic:
        parts.append("\n**Search Results:**")
        for i, result in enumerate(organic[:5], 1):
            title = result.get("title", "Untitled")
            link = result.get("link", "")
            snippet = result.get("snippet", "")
            parts.append(f"\n[{i}] {title}")
            if snippet:
                parts.append(f"    {snippet}")
            if link:
                parts.append(f"    URL: {link}")
    
    # Sources
    if organic:
        parts.append("\n\n**Sources:**")
        for i, result in enumerate(organic[:5], 1):
            title = result.get("title", "Untitled")
            link = result.get("link", "")
            parts.append(f"[{i}] {title} ({link})")
    
    return "\n".join(parts)


def _format_duckduckgo_results(data: dict[str, Any], query: str) -> str:
    """Format DuckDuckGo API results."""
    parts = [f'Web search results for "{query}":\n']
    
    # Abstract
    if data.get("AbstractText"):
        parts.append(f"**Summary:** {data['AbstractText']}")
        if data.get("AbstractURL"):
            parts.append(f"Source: {data['AbstractURL']}")
    
    # Related topics
    related = data.get("RelatedTopics", [])
    if related:
        parts.append("\n**Related Information:**")
        for i, topic in enumerate(related[:5], 1):
            if isinstance(topic, dict):
                text = topic.get("Text", "")
                url = topic.get("FirstURL", "")
                if text:
                    parts.append(f"\n[{i}] {text}")
                    if url:
                        parts.append(f"    URL: {url}")
    
    return "\n".join(parts)


def google_web_search(query: str) -> str:
    """
    Performs a web search using Google Search.
    
    Returns search results with sources and citations.
    
    Args:
        query: The search query
        
    Returns:
        JSON string with search results
    """
    try:
        # Validate query
        if not query or not query.strip():
            return json.dumps({
                "error": "Query cannot be empty.",
                "type": "INVALID_QUERY",
            })
        
        # Try Serper API first (requires API key)
        serper_key = os.environ.get("SERPER_API_KEY")
        if serper_key:
            result = _search_with_serper(query, serper_key)
            if result:
                formatted = _format_serper_results(result, query)
                return json.dumps({
                    "success": True,
                    "query": query,
                    "content": formatted,
                    "source": "serper",
                }, ensure_ascii=False)
        
        # Try DuckDuckGo as fallback
        result = _search_with_duckduckgo(query)
        if result:
            formatted = _format_duckduckgo_results(result, query)
            return json.dumps({
                "success": True,
                "query": query,
                "content": formatted,
                "source": "duckduckgo",
            }, ensure_ascii=False)
        
        # No search results available
        return json.dumps({
            "success": False,
            "query": query,
            "message": (
                f'No search results available for "{query}". '
                "Web search requires either SERPER_API_KEY environment variable "
                "or a working internet connection for DuckDuckGo."
            ),
            "type": "NO_RESULTS",
        })
        
    except Exception as e:
        return json.dumps({
            "error": f"Error during web search: {str(e)}",
            "type": "SEARCH_ERROR",
        })

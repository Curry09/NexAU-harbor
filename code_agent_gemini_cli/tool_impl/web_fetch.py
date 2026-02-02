# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
web_fetch tool - Fetches and processes content from URLs.

Based on gemini-cli's web-fetch.ts implementation.
"""

import json
import re
from typing import Any
from urllib.parse import urlparse

# Try to import required packages
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# Configuration
URL_FETCH_TIMEOUT = 30
MAX_CONTENT_LENGTH = 100000


def _parse_urls_from_prompt(prompt: str) -> tuple[list[str], list[str]]:
    """Parse valid URLs and errors from a prompt."""
    tokens = prompt.split()
    valid_urls = []
    errors = []
    
    for token in tokens:
        if "://" in token:
            try:
                parsed = urlparse(token)
                if parsed.scheme in ["http", "https"]:
                    valid_urls.append(token)
                else:
                    errors.append(f"Unsupported protocol: {token}")
            except Exception:
                errors.append(f"Malformed URL: {token}")
    
    return valid_urls, errors


def _convert_github_url(url: str) -> str:
    """Convert GitHub blob URL to raw content URL."""
    if "github.com" in url and "/blob/" in url:
        return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return url


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    if BS4_AVAILABLE:
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()
        
        # Get text
        text = soup.get_text(separator="\n", strip=True)
        
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
        
        return text
    else:
        # Simple fallback: remove HTML tags
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


def _fetch_url(url: str) -> tuple[str, str | None]:
    """Fetch content from URL. Returns (content, error)."""
    if not REQUESTS_AVAILABLE:
        return "", "requests library not available. Install with: pip install requests"
    
    try:
        # Convert GitHub URLs
        fetch_url = _convert_github_url(url)
        
        response = requests.get(
            fetch_url,
            timeout=URL_FETCH_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; GeminiCLI/1.0)",
            },
        )
        
        if response.status_code != 200:
            return "", f"HTTP {response.status_code}: {response.reason}"
        
        content_type = response.headers.get("content-type", "").lower()
        
        # Handle different content types
        if "text/html" in content_type:
            text = _html_to_text(response.text)
        else:
            text = response.text
        
        # Truncate if too long
        if len(text) > MAX_CONTENT_LENGTH:
            text = text[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated...]"
        
        return text, None
        
    except requests.Timeout:
        return "", f"Request timed out after {URL_FETCH_TIMEOUT} seconds"
    except requests.RequestException as e:
        return "", f"Request error: {str(e)}"
    except Exception as e:
        return "", f"Error fetching URL: {str(e)}"


def web_fetch(prompt: str) -> str:
    """
    Fetches and processes content from URLs in the prompt.
    
    Supports up to 20 URLs. Includes instructions for processing
    (e.g., "summarize", "extract key points").
    
    Args:
        prompt: A prompt containing URL(s) and processing instructions
        
    Returns:
        JSON string with fetched content or error
    """
    try:
        # Validate prompt
        if not prompt or not prompt.strip():
            return json.dumps({
                "error": "Prompt cannot be empty. Include URL(s) and instructions.",
                "type": "INVALID_PROMPT",
            })
        
        # Parse URLs from prompt
        urls, parse_errors = _parse_urls_from_prompt(prompt)
        
        if parse_errors:
            return json.dumps({
                "error": f"Error(s) in prompt URLs:\n- " + "\n- ".join(parse_errors),
                "type": "INVALID_URLS",
            })
        
        if not urls:
            return json.dumps({
                "error": "No valid URLs found in prompt. URLs must start with http:// or https://",
                "type": "NO_URLS",
            })
        
        if len(urls) > 20:
            return json.dumps({
                "error": f"Too many URLs ({len(urls)}). Maximum is 20.",
                "type": "TOO_MANY_URLS",
            })
        
        # Fetch each URL
        results = []
        errors = []
        
        for url in urls:
            content, error = _fetch_url(url)
            if error:
                errors.append({"url": url, "error": error})
            else:
                results.append({
                    "url": url,
                    "content": content,
                })
        
        # Build response
        if not results and errors:
            return json.dumps({
                "success": False,
                "errors": errors,
                "message": "Failed to fetch all URLs.",
            })
        
        # Format content for LLM
        formatted_parts = []
        for result in results:
            formatted_parts.append(f"--- Content from {result['url']} ---\n{result['content']}")
        
        formatted_content = "\n\n".join(formatted_parts)
        
        response: dict[str, Any] = {
            "success": True,
            "urls_fetched": len(results),
            "content": formatted_content,
        }
        
        if errors:
            response["errors"] = errors
            response["message"] = f"Fetched {len(results)} URL(s), {len(errors)} failed."
        else:
            response["message"] = f"Successfully fetched {len(results)} URL(s)."
        
        return json.dumps(response, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error processing web fetch: {str(e)}",
            "type": "FETCH_ERROR",
        })

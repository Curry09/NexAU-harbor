# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
google_web_search tool - Performs web searches using Google Search.

Based on gemini-cli's web-search.ts implementation.
Uses the Gemini API with grounding to provide search results with sources.
"""

from typing import Any


def google_web_search(
    query: str,
    search_function: Any | None = None,
) -> dict[str, Any]:
    """
    Performs a web search using Google Search (via the Gemini API).
    
    Returns search results with source citations when available.
    
    Args:
        query: The search query to find information on the web
        search_function: Optional external search function for testing/mocking
        
    Returns:
        Dict with llmContent and returnDisplay matching gemini-cli format
    """
    try:
        # Validate query
        if not query or not query.strip():
            return {
                "llmContent": "The 'query' parameter cannot be empty.",
                "returnDisplay": "Error: Empty search query.",
                "error": {
                    "message": "The 'query' parameter cannot be empty.",
                    "type": "INVALID_QUERY",
                },
            }
        
        # If a search function is provided (for testing/external integration), use it
        if search_function:
            try:
                result = search_function(query)
                
                # Handle result format
                if isinstance(result, dict):
                    response_text = result.get("text", "")
                    sources = result.get("sources", [])
                    grounding_supports = result.get("groundingSupports", [])
                else:
                    response_text = str(result)
                    sources = []
                    grounding_supports = []
                
            except Exception as e:
                error_msg = f"Error during web search for query \"{query}\": {str(e)}"
                return {
                    "llmContent": f"Error: {error_msg}",
                    "returnDisplay": "Error performing web search.",
                    "error": {
                        "message": error_msg,
                        "type": "WEB_SEARCH_FAILED",
                    },
                }
        else:
            # Placeholder for when no search function is provided
            # In actual usage, this would call the Gemini API
            return {
                "llmContent": f"Web search for \"{query}\" requires a configured search backend. "
                             "Please ensure the Gemini API client is properly configured.",
                "returnDisplay": "Web search backend not configured.",
                "error": {
                    "message": "No search function provided.",
                    "type": "WEB_SEARCH_NOT_CONFIGURED",
                },
            }
        
        # Check if we got results
        if not response_text or not response_text.strip():
            return {
                "llmContent": f'No search results or information found for query: "{query}"',
                "returnDisplay": "No information found.",
            }
        
        # Process sources and grounding if available
        modified_response = response_text
        source_list_formatted = []
        
        if sources:
            for idx, source in enumerate(sources):
                title = source.get("web", {}).get("title", "Untitled")
                uri = source.get("web", {}).get("uri", "No URI")
                source_list_formatted.append(f"[{idx + 1}] {title} ({uri})")
            
            # Insert citation markers if grounding supports are available
            if grounding_supports:
                insertions = []
                for support in grounding_supports:
                    segment = support.get("segment", {})
                    chunk_indices = support.get("groundingChunkIndices", [])
                    
                    if segment and chunk_indices:
                        citation_marker = "".join(
                            f"[{idx + 1}]" for idx in chunk_indices
                        )
                        insertions.append({
                            "index": segment.get("endIndex", 0),
                            "marker": citation_marker,
                        })
                
                # Sort insertions by index in descending order
                insertions.sort(key=lambda x: x["index"], reverse=True)
                
                # Insert markers into response text
                response_chars = list(modified_response)
                for insertion in insertions:
                    idx = min(insertion["index"], len(response_chars))
                    response_chars.insert(idx, insertion["marker"])
                
                modified_response = "".join(response_chars)
            
            # Append source list
            if source_list_formatted:
                modified_response += "\n\nSources:\n" + "\n".join(source_list_formatted)
        
        return {
            "llmContent": f'Web search results for "{query}":\n\n{modified_response}',
            "returnDisplay": f'Search results for "{query}" returned.',
            "sources": sources if sources else None,
        }
        
    except Exception as e:
        error_msg = f"Error during web search for query \"{query}\": {str(e)}"
        return {
            "llmContent": f"Error: {error_msg}",
            "returnDisplay": "Error performing web search.",
            "error": {
                "message": error_msg,
                "type": "WEB_SEARCH_FAILED",
            },
        }

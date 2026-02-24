"""AgenLang Tool Registry - verified tools with capability declarations."""

from typing import Dict, Any

TOOLS: Dict[str, Dict[str, Any]] = {
    "web_search": {
        "capabilities": ["net:read"],
        "function": lambda args: f"Dummy search result for query: {args['query']}",  # Safe placeholder
        "description": "Perform a web search."
    },
    "summarize": {
        "capabilities": ["compute:read"],
        "function": lambda args: f"Dummy summary of {args['text'][:50]}...",  # Dummy summarize
        "description": "Summarize text."
    }
}

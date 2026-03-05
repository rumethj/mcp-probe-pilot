"""
Common LLM client for non-MCP tasks (test generation, evaluation, etc.).

Usage:
    from mcp_probe_pilot.core.llm_client import LLMClient

    with LLMClient() as llm:
        structured = llm.with_structured_output(MyModel)
        result = (prompt | structured).invoke({})
"""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI
import os

DEFAULT_CONFIG = {
    "model": "gemini-2.5-flash",
    "temperature": 0.2,
    "max_output_tokens": 65536,
    "api_key": os.getenv("GEMINI_API_KEY"),
}


class LLMClient:
    """Context-managed wrapper around ChatGoogleGenerativeAI."""

    def __init__(self, **overrides):
        config = {**DEFAULT_CONFIG, **overrides}
        self._llm = ChatGoogleGenerativeAI(**config)

    def __enter__(self) -> ChatGoogleGenerativeAI:
        return self._llm

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Ensure the underlying client session is closed."""
        if hasattr(self._llm, "close"):
            self._llm.close()
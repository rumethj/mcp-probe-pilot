"""Test Generators module.

This module provides LLM-powered Gherkin test generation capabilities:
- Unit test generation (one feature file per tool/resource/prompt)
- Integration test generation (workflow scenarios in a single feature file)

The generators combine MCP discovery results with AST-indexed codebase
context (via ChromaDB) to produce comprehensive BDD Gherkin test scenarios.
"""

from .base_generator import BaseTestGenerator, GeneratorError
from .integration_test_generator import IntegrationTestGenerator
from .llm_client import (
    AnthropicClient,
    BaseLLMClient,
    LLMClientError,
    LLMResponse,
    MockLLMClient,
    OpenAIClient,
    create_llm_client,
)
from .models import GeneratedFeatureFile, GenerationResult, WorkflowType
from .unit_test_generator import UnitTestGenerator

__all__ = [
    # Base generator
    "BaseTestGenerator",
    "GeneratorError",
    # Unit test generator
    "UnitTestGenerator",
    # Integration test generator
    "IntegrationTestGenerator",
    # LLM clients
    "BaseLLMClient",
    "OpenAIClient",
    "AnthropicClient",
    "MockLLMClient",
    "LLMResponse",
    "LLMClientError",
    "create_llm_client",
    # Models
    "GeneratedFeatureFile",
    "GenerationResult",
    "WorkflowType",
]

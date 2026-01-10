"""Test Generators module.

This module provides LLM-powered test generation capabilities:
- Client discovery-based test generation
- Ground truth specification generation
- BDD Gherkin scenario generation
- Executable Behave test implementation

The generation follows a multi-phase approach:
1. Ground truth generation (isolated context - no scenario information)
2. Scenario generation (references ground truth by ID only)
3. Test implementation (converts Gherkin to executable Behave tests)

This separation prevents ground truth poisoning by ensuring ground truth
is derived purely from capability definitions.
"""

from .client_generator import ClientTestGenerator, GeneratorError
from .llm_client import (
    AnthropicClient,
    BaseLLMClient,
    LLMClientError,
    LLMResponse,
    MockLLMClient,
    OpenAIClient,
    create_llm_client,
)
from .models import (
    FeatureFile,
    GeneratedScenario,
    GroundTruthSpec,
    ScenarioCategory,
    ScenarioSet,
    TargetType,
    WorkflowGroundTruth,
    WorkflowScenario,
    WorkflowStep,
)
from .test_implementor import TestImplementation, TestImplementor, TestImplementorError

__all__ = [
    # Main generator
    "ClientTestGenerator",
    "GeneratorError",
    # Test implementor
    "TestImplementor",
    "TestImplementorError",
    "TestImplementation",
    # LLM clients
    "BaseLLMClient",
    "OpenAIClient",
    "AnthropicClient",
    "MockLLMClient",
    "LLMResponse",
    "LLMClientError",
    "create_llm_client",
    # Models
    "TargetType",
    "ScenarioCategory",
    "GroundTruthSpec",
    "GeneratedScenario",
    "FeatureFile",
    "ScenarioSet",
    # Workflow models
    "WorkflowStep",
    "WorkflowGroundTruth",
    "WorkflowScenario",
]

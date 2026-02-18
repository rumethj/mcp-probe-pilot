"""Data models for test generation.

This module defines Pydantic models for representing generated Gherkin
feature files, generation results, and workflow type classifications.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    """Types of integration test workflows.

    Attributes:
        PROMPT_DRIVEN: Prompt -> Fill Args -> LLM -> Tool workflow.
        RESOURCE_AUGMENTED: Tool -> Resource URI -> Read Resource workflow.
        CHAIN_OF_THOUGHT: Tool A output -> Tool B input chaining workflow.
    """

    PROMPT_DRIVEN = "prompt-driven"
    RESOURCE_AUGMENTED = "resource-augmented"
    CHAIN_OF_THOUGHT = "chain-of-thought"


class GeneratedFeatureFile(BaseModel):
    """A generated Gherkin feature file.

    Represents a single .feature file produced by a test generator,
    containing one or more BDD scenarios.

    Attributes:
        filename: The filename for the feature file (e.g., 'tool_auth_login.feature').
        content: The full Gherkin feature file content.
        target_name: The name of the MCP capability being tested.
        target_type: The type of MCP capability ('tool', 'resource', 'prompt', 'integration').
        scenario_count: Number of scenarios in the feature file.
        workflow_type: Optional workflow type for integration test scenarios.
    """

    filename: str = Field(..., description="Filename for the feature file")
    content: str = Field(..., description="Full Gherkin feature file content")
    target_name: str = Field(
        ...,
        description="Name of the MCP capability being tested",
    )
    target_type: str = Field(
        ...,
        description="Type of capability: 'tool', 'resource', 'prompt', 'integration'",
    )
    scenario_count: int = Field(
        0,
        ge=0,
        description="Number of scenarios in the feature file",
    )
    workflow_type: Optional[WorkflowType] = Field(
        None,
        description="Workflow type for integration test scenarios",
    )


class GenerationResult(BaseModel):
    """Result of a test generation run.

    Contains all generated feature files along with metadata about the
    generation process.

    Attributes:
        feature_files: List of generated feature files.
        total_scenarios: Total number of scenarios across all feature files.
        tools_covered: Number of tools with generated tests.
        resources_covered: Number of resources with generated tests.
        prompts_covered: Number of prompts with generated tests.
        workflows_identified: Number of integration workflow patterns identified.
        errors: List of error messages from generation failures.
    """

    feature_files: list[GeneratedFeatureFile] = Field(
        default_factory=list,
        description="List of generated feature files",
    )
    total_scenarios: int = Field(
        0,
        ge=0,
        description="Total number of generated scenarios",
    )
    tools_covered: int = Field(
        0,
        ge=0,
        description="Number of tools with generated tests",
    )
    resources_covered: int = Field(
        0,
        ge=0,
        description="Number of resources with generated tests",
    )
    prompts_covered: int = Field(
        0,
        ge=0,
        description="Number of prompts with generated tests",
    )
    workflows_identified: int = Field(
        0,
        ge=0,
        description="Number of integration workflow patterns identified",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages from generation failures",
    )

    @property
    def total_feature_files(self) -> int:
        """Get the total number of generated feature files."""
        return len(self.feature_files)

    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred during generation."""
        return len(self.errors) > 0

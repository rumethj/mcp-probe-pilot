"""Data models for test generation.

This module defines Pydantic models for representing generated test scenarios,
ground truth specifications, and scenario collections.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TargetType(str, Enum):
    """Type of MCP capability being tested."""

    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"


class ScenarioCategory(str, Enum):
    """Category of test scenario."""

    HAPPY_PATH = "happy_path"
    ERROR_CASE = "error_case"
    EDGE_CASE = "edge_case"
    WORKFLOW = "workflow"  # Multi-step scenarios chaining multiple features


class WorkflowStep(BaseModel):
    """A single step in a workflow scenario.

    Attributes:
        step_number: The order of this step in the workflow.
        action_type: Type of MCP action (tool_call, resource_read, prompt_get, sampling, elicitation).
        target_name: Name of the tool/resource/prompt being used.
        description: Description of what this step does.
        input_source: Where input comes from ("literal", "previous_step", "context").
        output_variable: Variable name to store the result for later steps.
        dependencies: List of step numbers this step depends on.
    """

    step_number: int = Field(..., description="Order of this step in the workflow")
    action_type: str = Field(
        ...,
        description="Type of MCP action: tool_call, resource_read, prompt_get, sampling, elicitation",
    )
    target_name: str = Field(..., description="Name of the tool/resource/prompt")
    description: str = Field(..., description="What this step does")
    input_source: str = Field(
        default="literal",
        description="Where input comes from: literal, previous_step, context",
    )
    output_variable: Optional[str] = Field(
        None,
        description="Variable name to store result for later steps",
    )
    dependencies: list[int] = Field(
        default_factory=list,
        description="Step numbers this step depends on",
    )


class WorkflowGroundTruth(BaseModel):
    """Ground truth for a workflow scenario.

    Attributes:
        id: Unique identifier for this workflow ground truth.
        workflow_name: Name describing the workflow.
        expected_flow: Description of the expected execution flow.
        step_expectations: Expected behavior for each step.
        final_outcome: Expected final outcome of the workflow.
        error_scenarios: Expected behavior when steps fail.
    """

    id: str = Field(..., description="Unique identifier for workflow ground truth")
    workflow_name: str = Field(..., description="Name describing the workflow")
    expected_flow: str = Field(..., description="Description of expected execution flow")
    step_expectations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Expected behavior for each step",
    )
    final_outcome: str = Field(..., description="Expected final outcome")
    error_scenarios: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Expected behavior when steps fail",
    )

    @classmethod
    def generate_id(cls, workflow_name: str) -> str:
        """Generate a unique workflow ground truth ID."""
        safe_name = workflow_name.replace("-", "_").replace(" ", "_").lower()
        return f"gt_workflow_{safe_name}"


class WorkflowScenario(BaseModel):
    """A workflow scenario that chains multiple MCP features.

    Attributes:
        id: Unique scenario identifier.
        name: Human-readable scenario name.
        description: What this workflow tests.
        steps: Ordered list of workflow steps.
        gherkin: Raw Gherkin text for the scenario.
        ground_truth_id: Reference to WorkflowGroundTruth.id.
        involved_features: List of feature types involved (tools, resources, etc.).
    """

    id: str = Field(..., description="Unique scenario identifier")
    name: str = Field(..., description="Human-readable scenario name")
    description: str = Field(..., description="What this workflow tests")
    steps: list[WorkflowStep] = Field(..., description="Ordered list of workflow steps")
    gherkin: str = Field(..., description="Raw Gherkin text for the scenario")
    ground_truth_id: str = Field(..., description="Reference to WorkflowGroundTruth.id")
    involved_features: list[str] = Field(
        default_factory=list,
        description="Feature types involved: tools, resources, prompts, sampling, elicitation",
    )

    @classmethod
    def generate_id(cls, workflow_name: str, index: int = 0) -> str:
        """Generate a unique workflow scenario ID."""
        safe_name = workflow_name.replace("-", "_").replace(" ", "_").lower()
        return f"sc_workflow_{safe_name}_{index}"


class GroundTruthSpec(BaseModel):
    """Ground truth specification for a capability.

    Generated FIRST and in isolation from test scenarios to prevent
    ground truth poisoning. Derived purely from capability definitions
    (schema, description) without any scenario context.

    Attributes:
        id: Unique identifier for reference (e.g., "gt_tool_auth_login").
        target_type: Type of capability (tool, resource, prompt).
        target_name: Name of the capability being tested.
        expected_behavior: Natural language description of what the capability should do.
        expected_output_schema: JSON schema describing expected response structure.
        valid_input_examples: List of sample valid inputs with expected outcomes.
        invalid_input_examples: List of sample invalid inputs with expected error behavior.
        semantic_reference: Concise semantic description for LLM oracle evaluation.
    """

    id: str = Field(..., description="Unique identifier for ground truth reference")
    target_type: TargetType = Field(..., description="Type of MCP capability")
    target_name: str = Field(..., description="Name of the capability")
    expected_behavior: str = Field(
        ...,
        description="Natural language description of expected behavior",
    )
    expected_output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON schema for expected response structure",
    )
    valid_input_examples: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Sample valid inputs with expected outcomes",
    )
    invalid_input_examples: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Sample invalid inputs with expected error behavior",
    )
    semantic_reference: str = Field(
        ...,
        description="Concise semantic description for oracle evaluation",
    )

    @classmethod
    def generate_id(cls, target_type: TargetType, target_name: str) -> str:
        """Generate a unique ground truth ID.

        Args:
            target_type: The type of capability.
            target_name: The name of the capability.

        Returns:
            A unique identifier string.
        """
        safe_name = target_name.replace("-", "_").replace(" ", "_").lower()
        return f"gt_{target_type.value}_{safe_name}"


class GeneratedScenario(BaseModel):
    """A generated Gherkin test scenario.

    Generated SECOND, after ground truth. References ground truth by ID
    rather than embedding it to maintain separation of concerns.

    Attributes:
        id: Unique scenario identifier.
        name: Human-readable scenario name.
        gherkin: Raw Gherkin text for the scenario.
        target_type: Type of capability being tested.
        target_name: Name of the capability being tested.
        category: Category of the scenario (happy_path, error_case, edge_case).
        ground_truth_id: Reference to the associated GroundTruthSpec.id.
        description: Optional description of what the scenario tests.
    """

    id: str = Field(..., description="Unique scenario identifier")
    name: str = Field(..., description="Human-readable scenario name")
    gherkin: str = Field(..., description="Raw Gherkin text for the scenario")
    target_type: TargetType = Field(..., description="Type of MCP capability")
    target_name: str = Field(..., description="Name of the capability")
    category: ScenarioCategory = Field(..., description="Category of test scenario")
    ground_truth_id: str = Field(
        ...,
        description="Reference to GroundTruthSpec.id (NOT embedded)",
    )
    description: Optional[str] = Field(
        None,
        description="Optional description of what the scenario tests",
    )

    @classmethod
    def generate_id(
        cls,
        target_type: TargetType,
        target_name: str,
        category: ScenarioCategory,
        index: int = 0,
    ) -> str:
        """Generate a unique scenario ID.

        Args:
            target_type: The type of capability.
            target_name: The name of the capability.
            category: The scenario category.
            index: Index for multiple scenarios of same type.

        Returns:
            A unique identifier string.
        """
        safe_name = target_name.replace("-", "_").replace(" ", "_").lower()
        return f"sc_{target_type.value}_{safe_name}_{category.value}_{index}"


class FeatureFile(BaseModel):
    """A Gherkin feature file containing multiple scenarios.

    Attributes:
        name: Feature name.
        target_type: Type of capability being tested.
        target_name: Name of the capability being tested.
        ground_truth_id: Reference to the associated ground truth.
        scenarios: List of scenarios in this feature.
        gherkin: Complete Gherkin text for the feature file.
    """

    name: str = Field(..., description="Feature name")
    target_type: TargetType = Field(..., description="Type of MCP capability")
    target_name: str = Field(..., description="Name of the capability")
    ground_truth_id: str = Field(..., description="Reference to ground truth")
    scenarios: list[GeneratedScenario] = Field(
        default_factory=list,
        description="List of scenarios in this feature",
    )
    gherkin: str = Field(..., description="Complete Gherkin text for the feature")


class ScenarioSet(BaseModel):
    """Collection of generated scenarios and their ground truths.

    Attributes:
        ground_truths: Dictionary of ground truth specs keyed by ID.
        scenarios: List of all generated scenarios.
        features: List of feature files (grouped scenarios).
        workflow_ground_truths: Dictionary of workflow ground truths keyed by ID.
        workflow_scenarios: List of workflow scenarios.
    """

    ground_truths: dict[str, GroundTruthSpec] = Field(
        default_factory=dict,
        description="Ground truth specs keyed by ID",
    )
    scenarios: list[GeneratedScenario] = Field(
        default_factory=list,
        description="All generated scenarios",
    )
    features: list[FeatureFile] = Field(
        default_factory=list,
        description="Feature files grouping scenarios",
    )
    workflow_ground_truths: dict[str, WorkflowGroundTruth] = Field(
        default_factory=dict,
        description="Workflow ground truths keyed by ID",
    )
    workflow_scenarios: list[WorkflowScenario] = Field(
        default_factory=list,
        description="Workflow scenarios chaining multiple features",
    )

    def add_ground_truth(self, ground_truth: GroundTruthSpec) -> None:
        """Add a ground truth specification.

        Args:
            ground_truth: The ground truth to add.
        """
        self.ground_truths[ground_truth.id] = ground_truth

    def add_scenario(self, scenario: GeneratedScenario) -> None:
        """Add a scenario to the collection.

        Args:
            scenario: The scenario to add.
        """
        self.scenarios.append(scenario)

    def add_feature(self, feature: FeatureFile) -> None:
        """Add a feature file to the collection.

        Args:
            feature: The feature file to add.
        """
        self.features.append(feature)
        for scenario in feature.scenarios:
            if scenario not in self.scenarios:
                self.scenarios.append(scenario)

    def add_workflow_ground_truth(self, ground_truth: WorkflowGroundTruth) -> None:
        """Add a workflow ground truth specification.

        Args:
            ground_truth: The workflow ground truth to add.
        """
        self.workflow_ground_truths[ground_truth.id] = ground_truth

    def add_workflow_scenario(self, scenario: WorkflowScenario) -> None:
        """Add a workflow scenario to the collection.

        Args:
            scenario: The workflow scenario to add.
        """
        self.workflow_scenarios.append(scenario)

    def get_workflow_ground_truth(self, ground_truth_id: str) -> Optional[WorkflowGroundTruth]:
        """Get a workflow ground truth by ID.

        Args:
            ground_truth_id: The workflow ground truth ID to look up.

        Returns:
            The WorkflowGroundTruth if found, None otherwise.
        """
        return self.workflow_ground_truths.get(ground_truth_id)

    def get_ground_truth(self, ground_truth_id: str) -> Optional[GroundTruthSpec]:
        """Get a ground truth by ID.

        Args:
            ground_truth_id: The ground truth ID to look up.

        Returns:
            The GroundTruthSpec if found, None otherwise.
        """
        return self.ground_truths.get(ground_truth_id)

    def get_scenarios_by_target(
        self,
        target_type: TargetType,
        target_name: str,
    ) -> list[GeneratedScenario]:
        """Get all scenarios for a specific target.

        Args:
            target_type: The type of capability.
            target_name: The name of the capability.

        Returns:
            List of scenarios matching the target.
        """
        return [
            s
            for s in self.scenarios
            if s.target_type == target_type and s.target_name == target_name
        ]

    def get_scenarios_by_category(
        self,
        category: ScenarioCategory,
    ) -> list[GeneratedScenario]:
        """Get all scenarios of a specific category.

        Args:
            category: The scenario category to filter by.

        Returns:
            List of scenarios matching the category.
        """
        return [s for s in self.scenarios if s.category == category]

    @property
    def tool_count(self) -> int:
        """Count of unique tools with scenarios."""
        return len(
            {s.target_name for s in self.scenarios if s.target_type == TargetType.TOOL}
        )

    @property
    def resource_count(self) -> int:
        """Count of unique resources with scenarios."""
        return len(
            {
                s.target_name
                for s in self.scenarios
                if s.target_type == TargetType.RESOURCE
            }
        )

    @property
    def prompt_count(self) -> int:
        """Count of unique prompts with scenarios."""
        return len(
            {
                s.target_name
                for s in self.scenarios
                if s.target_type == TargetType.PROMPT
            }
        )

    @property
    def total_scenarios(self) -> int:
        """Total number of scenarios (including workflows)."""
        return len(self.scenarios) + len(self.workflow_scenarios)

    @property
    def workflow_count(self) -> int:
        """Count of workflow scenarios."""
        return len(self.workflow_scenarios)

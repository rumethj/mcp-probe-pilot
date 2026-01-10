"""Client-based test generator for MCP servers.

This module provides the ClientTestGenerator class which generates Gherkin
BDD test scenarios from MCP server discovery results. It implements a
two-phase generation process:

Phase 1: Ground Truth Generation (isolated context)
    - Generates ground truth purely from capability definitions
    - No scenario context to prevent ground truth poisoning

Phase 2: Scenario Generation (references ground truth)
    - Generates Gherkin scenarios that reference ground truth by ID
    - Covers happy path, error cases, and edge cases
"""

import logging
from typing import Optional

from ..config import LLMConfig
from ..discovery.models import DiscoveryResult, PromptInfo, ResourceInfo, ToolInfo
from .llm_client import BaseLLMClient, LLMClientError, create_llm_client
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
from .prompts import (
    GROUND_TRUTH_SYSTEM_PROMPT,
    SCENARIO_SYSTEM_PROMPT,
    WORKFLOW_ANALYSIS_SYSTEM_PROMPT,
    WORKFLOW_GROUND_TRUTH_SYSTEM_PROMPT,
    WORKFLOW_SCENARIO_SYSTEM_PROMPT,
    build_ground_truth_prompt,
    build_scenario_prompt,
    build_workflow_analysis_prompt,
    build_workflow_ground_truth_prompt,
    build_workflow_scenario_prompt,
)

logger = logging.getLogger(__name__)


class GeneratorError(Exception):
    """Exception raised when test generation fails."""

    pass


class ClientTestGenerator:
    """Generates BDD test scenarios from MCP discovery results.

    This generator implements a two-phase approach:
    1. Generate ground truth specifications (isolated context)
    2. Generate Gherkin scenarios (referencing ground truth by ID)

    Example:
        ```python
        config = LLMConfig(provider="openai", model="gpt-4")
        generator = ClientTestGenerator(config)

        async with MCPDiscoveryClient("python -m my_server") as client:
            discovery = await client.discover_all()

        scenarios = await generator.generate_scenarios(discovery)
        print(f"Generated {scenarios.total_scenarios} scenarios")
        ```

    Attributes:
        llm_client: The LLM client for generation.
    """

    def __init__(
        self,
        llm_config: LLMConfig,
        llm_client: Optional[BaseLLMClient] = None,
    ):
        """Initialize the test generator.

        Args:
            llm_config: Configuration for the LLM provider.
            llm_client: Optional pre-configured LLM client. If not provided,
                one will be created from the config.
        """
        self.llm_config = llm_config
        self._llm_client = llm_client

    @property
    def llm_client(self) -> BaseLLMClient:
        """Get the LLM client, creating it if necessary."""
        if self._llm_client is None:
            self._llm_client = create_llm_client(self.llm_config)
        return self._llm_client

    async def generate_scenarios(
        self,
        discovery: DiscoveryResult,
        include_tools: bool = True,
        include_resources: bool = True,
        include_prompts: bool = True,
        include_workflows: bool = True,
    ) -> ScenarioSet:
        """Generate test scenarios from discovery results.

        This is the main entry point for test generation. It performs
        multi-phase generation:
        1. Generate ground truth for all capabilities
        2. Generate scenarios referencing the ground truth
        3. Analyze and generate workflow scenarios (chained multi-step tests)

        Args:
            discovery: The discovery results from an MCP server.
            include_tools: Whether to generate tests for tools.
            include_resources: Whether to generate tests for resources.
            include_prompts: Whether to generate tests for prompts.
            include_workflows: Whether to generate workflow tests that chain features.

        Returns:
            ScenarioSet containing all generated scenarios and ground truths.

        Raises:
            GeneratorError: If generation fails.
        """
        scenario_set = ScenarioSet()

        # Phase 1: Generate ground truth for all capabilities
        logger.info("Phase 1: Generating ground truth specifications...")

        if include_tools:
            for tool in discovery.tools:
                try:
                    ground_truth = await self._generate_tool_ground_truth(tool)
                    scenario_set.add_ground_truth(ground_truth)
                    logger.debug(f"Generated ground truth for tool: {tool.name}")
                except Exception as e:
                    logger.warning(f"Failed to generate ground truth for tool {tool.name}: {e}")

        if include_resources:
            for resource in discovery.resources:
                try:
                    ground_truth = await self._generate_resource_ground_truth(resource)
                    scenario_set.add_ground_truth(ground_truth)
                    logger.debug(f"Generated ground truth for resource: {resource.uri}")
                except Exception as e:
                    logger.warning(
                        f"Failed to generate ground truth for resource {resource.uri}: {e}"
                    )

        if include_prompts:
            for prompt in discovery.prompts:
                try:
                    ground_truth = await self._generate_prompt_ground_truth(prompt)
                    scenario_set.add_ground_truth(ground_truth)
                    logger.debug(f"Generated ground truth for prompt: {prompt.name}")
                except Exception as e:
                    logger.warning(f"Failed to generate ground truth for prompt {prompt.name}: {e}")

        # Phase 2: Generate scenarios referencing ground truth
        logger.info("Phase 2: Generating test scenarios...")

        if include_tools:
            for tool in discovery.tools:
                ground_truth_id = GroundTruthSpec.generate_id(TargetType.TOOL, tool.name)
                if ground_truth_id in scenario_set.ground_truths:
                    try:
                        feature = await self._generate_tool_scenarios(tool, ground_truth_id)
                        scenario_set.add_feature(feature)
                        logger.debug(f"Generated scenarios for tool: {tool.name}")
                    except Exception as e:
                        logger.warning(f"Failed to generate scenarios for tool {tool.name}: {e}")

        if include_resources:
            for resource in discovery.resources:
                ground_truth_id = GroundTruthSpec.generate_id(
                    TargetType.RESOURCE, self._resource_name(resource)
                )
                if ground_truth_id in scenario_set.ground_truths:
                    try:
                        feature = await self._generate_resource_scenarios(resource, ground_truth_id)
                        scenario_set.add_feature(feature)
                        logger.debug(f"Generated scenarios for resource: {resource.uri}")
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate scenarios for resource {resource.uri}: {e}"
                        )

        if include_prompts:
            for prompt in discovery.prompts:
                ground_truth_id = GroundTruthSpec.generate_id(TargetType.PROMPT, prompt.name)
                if ground_truth_id in scenario_set.ground_truths:
                    try:
                        feature = await self._generate_prompt_scenarios(prompt, ground_truth_id)
                        scenario_set.add_feature(feature)
                        logger.debug(f"Generated scenarios for prompt: {prompt.name}")
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate scenarios for prompt {prompt.name}: {e}"
                        )

        # Phase 3: Generate workflow scenarios (chained multi-step tests)
        if include_workflows:
            await self._generate_workflow_scenarios(discovery, scenario_set)

        logger.info(
            f"Generation complete: {len(scenario_set.ground_truths)} ground truths, "
            f"{scenario_set.total_scenarios} scenarios "
            f"({scenario_set.workflow_count} workflows)"
        )

        return scenario_set

    # =========================================================================
    # Phase 1: Ground Truth Generation (Isolated Context)
    # =========================================================================

    async def _generate_tool_ground_truth(self, tool: ToolInfo) -> GroundTruthSpec:
        """Generate ground truth for a tool.

        Args:
            tool: The tool information from discovery.

        Returns:
            GroundTruthSpec for the tool.

        Raises:
            TestGeneratorError: If generation fails.
        """
        return await self._generate_ground_truth(TargetType.TOOL, tool, tool.name)

    async def _generate_resource_ground_truth(self, resource: ResourceInfo) -> GroundTruthSpec:
        """Generate ground truth for a resource.

        Args:
            resource: The resource information from discovery.

        Returns:
            GroundTruthSpec for the resource.

        Raises:
            TestGeneratorError: If generation fails.
        """
        name = self._resource_name(resource)
        return await self._generate_ground_truth(TargetType.RESOURCE, resource, name)

    async def _generate_prompt_ground_truth(self, prompt: PromptInfo) -> GroundTruthSpec:
        """Generate ground truth for a prompt.

        Args:
            prompt: The prompt information from discovery.

        Returns:
            GroundTruthSpec for the prompt.

        Raises:
            TestGeneratorError: If generation fails.
        """
        return await self._generate_ground_truth(TargetType.PROMPT, prompt, prompt.name)

    async def _generate_ground_truth(
        self,
        target_type: TargetType,
        target: ToolInfo | ResourceInfo | PromptInfo,
        target_name: str,
    ) -> GroundTruthSpec:
        """Generate ground truth for any capability type.

        Args:
            target_type: The type of capability.
            target: The capability information.
            target_name: The name of the capability.

        Returns:
            GroundTruthSpec for the capability.

        Raises:
            TestGeneratorError: If generation fails.
        """
        try:
            prompt = build_ground_truth_prompt(target_type, target)
            response = await self.llm_client.generate_json(
                prompt,
                system_prompt=GROUND_TRUTH_SYSTEM_PROMPT,
            )

            ground_truth_id = GroundTruthSpec.generate_id(target_type, target_name)

            return GroundTruthSpec(
                id=ground_truth_id,
                target_type=target_type,
                target_name=target_name,
                expected_behavior=response.get("expected_behavior", ""),
                expected_output_schema=response.get("expected_output_schema", {}),
                valid_input_examples=response.get("valid_input_examples", []),
                invalid_input_examples=response.get("invalid_input_examples", []),
                semantic_reference=response.get("semantic_reference", ""),
            )

        except LLMClientError as e:
            raise GeneratorError(
                f"Failed to generate ground truth for {target_type.value} '{target_name}': {e}"
            ) from e

    # =========================================================================
    # Phase 2: Scenario Generation (References Ground Truth)
    # =========================================================================

    async def _generate_tool_scenarios(
        self,
        tool: ToolInfo,
        ground_truth_id: str,
    ) -> FeatureFile:
        """Generate scenarios for a tool.

        Args:
            tool: The tool information from discovery.
            ground_truth_id: The ID of the pre-generated ground truth.

        Returns:
            FeatureFile containing the generated scenarios.

        Raises:
            TestGeneratorError: If generation fails.
        """
        return await self._generate_feature(
            TargetType.TOOL,
            tool,
            tool.name,
            ground_truth_id,
        )

    async def _generate_resource_scenarios(
        self,
        resource: ResourceInfo,
        ground_truth_id: str,
    ) -> FeatureFile:
        """Generate scenarios for a resource.

        Args:
            resource: The resource information from discovery.
            ground_truth_id: The ID of the pre-generated ground truth.

        Returns:
            FeatureFile containing the generated scenarios.

        Raises:
            TestGeneratorError: If generation fails.
        """
        name = self._resource_name(resource)
        return await self._generate_feature(
            TargetType.RESOURCE,
            resource,
            name,
            ground_truth_id,
        )

    async def _generate_prompt_scenarios(
        self,
        prompt: PromptInfo,
        ground_truth_id: str,
    ) -> FeatureFile:
        """Generate scenarios for a prompt.

        Args:
            prompt: The prompt information from discovery.
            ground_truth_id: The ID of the pre-generated ground truth.

        Returns:
            FeatureFile containing the generated scenarios.

        Raises:
            TestGeneratorError: If generation fails.
        """
        return await self._generate_feature(
            TargetType.PROMPT,
            prompt,
            prompt.name,
            ground_truth_id,
        )

    async def _generate_feature(
        self,
        target_type: TargetType,
        target: ToolInfo | ResourceInfo | PromptInfo,
        target_name: str,
        ground_truth_id: str,
    ) -> FeatureFile:
        """Generate a feature file for any capability type.

        Args:
            target_type: The type of capability.
            target: The capability information.
            target_name: The name of the capability.
            ground_truth_id: The ID of the pre-generated ground truth.

        Returns:
            FeatureFile containing the generated scenarios.

        Raises:
            TestGeneratorError: If generation fails.
        """
        try:
            prompt = build_scenario_prompt(target_type, target, ground_truth_id)
            response = await self.llm_client.generate_json(
                prompt,
                system_prompt=SCENARIO_SYSTEM_PROMPT,
            )

            scenarios_data = response.get("scenarios", [])
            scenarios = []
            category_counts: dict[str, int] = {}

            for scenario_data in scenarios_data:
                category_str = scenario_data.get("category", "happy_path")
                try:
                    category = ScenarioCategory(category_str)
                except ValueError:
                    category = ScenarioCategory.HAPPY_PATH

                # Track count per category for unique IDs
                category_counts[category.value] = category_counts.get(category.value, 0)
                index = category_counts[category.value]
                category_counts[category.value] += 1

                scenario_id = GeneratedScenario.generate_id(
                    target_type, target_name, category, index
                )

                scenario = GeneratedScenario(
                    id=scenario_id,
                    name=scenario_data.get("name", f"{target_name} scenario"),
                    gherkin=scenario_data.get("gherkin", ""),
                    target_type=target_type,
                    target_name=target_name,
                    category=category,
                    ground_truth_id=ground_truth_id,
                    description=scenario_data.get("description"),
                )
                scenarios.append(scenario)

            # Build complete feature file Gherkin
            feature_gherkin = self._build_feature_gherkin(
                target_type, target_name, ground_truth_id, scenarios
            )

            return FeatureFile(
                name=f"{target_type.value.title()} - {target_name}",
                target_type=target_type,
                target_name=target_name,
                ground_truth_id=ground_truth_id,
                scenarios=scenarios,
                gherkin=feature_gherkin,
            )

        except LLMClientError as e:
            raise GeneratorError(
                f"Failed to generate scenarios for {target_type.value} '{target_name}': {e}"
            ) from e

    def _build_feature_gherkin(
        self,
        target_type: TargetType,
        target_name: str,
        ground_truth_id: str,
        scenarios: list[GeneratedScenario],
    ) -> str:
        """Build complete Gherkin text for a feature file.

        Args:
            target_type: The type of capability.
            target_name: The name of the capability.
            ground_truth_id: The ground truth ID reference.
            scenarios: List of scenarios to include.

        Returns:
            Complete Gherkin feature file text.
        """
        lines = [
            f"Feature: {target_type.value.title()} - {target_name}",
            f"  # Ground Truth ID: {ground_truth_id}",
            "",
        ]

        for scenario in scenarios:
            # Indent the scenario gherkin properly
            scenario_lines = scenario.gherkin.strip().split("\n")
            for line in scenario_lines:
                # Ensure proper indentation
                if line.strip().startswith("Scenario"):
                    lines.append(f"  {line.strip()}")
                elif line.strip():
                    lines.append(f"    {line.strip()}")
                else:
                    lines.append("")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _resource_name(resource: ResourceInfo) -> str:
        """Get a safe name for a resource.

        Args:
            resource: The resource information.

        Returns:
            A safe name string for the resource.
        """
        # Use the resource name if available, otherwise derive from URI
        if resource.name:
            return resource.name

        # Extract a name from the URI
        uri = resource.uri
        # Remove protocol prefix
        if "://" in uri:
            uri = uri.split("://", 1)[1]
        # Replace path separators and special chars
        name = uri.replace("/", "_").replace("{", "").replace("}", "")
        return name or "unnamed_resource"

    # =========================================================================
    # Phase 3: Workflow Generation (Multi-step Chained Scenarios)
    # =========================================================================

    async def _generate_workflow_scenarios(
        self,
        discovery: DiscoveryResult,
        scenario_set: ScenarioSet,
    ) -> None:
        """Generate workflow scenarios that chain multiple MCP features.

        This method:
        1. Analyzes capabilities to identify potential workflows
        2. Generates ground truth for each workflow (isolated context)
        3. Generates Gherkin scenarios for each workflow

        Args:
            discovery: The complete discovery results.
            scenario_set: The ScenarioSet to add workflows to.
        """
        # Skip if server has very few capabilities
        total_capabilities = (
            len(discovery.tools) + len(discovery.resources) + len(discovery.prompts)
        )
        if total_capabilities < 2:
            logger.debug("Skipping workflow generation - too few capabilities")
            return

        logger.info("Phase 3: Generating workflow scenarios...")

        # Step 1: Analyze capabilities to identify workflows
        try:
            workflows = await self._analyze_workflows(discovery)
            logger.debug(f"Identified {len(workflows)} potential workflows")
        except Exception as e:
            logger.warning(f"Failed to analyze workflows: {e}")
            return

        # Step 2 & 3: For each workflow, generate ground truth then scenarios
        for workflow in workflows:
            workflow_name = workflow.get("name", "unnamed_workflow")
            try:
                # Generate workflow ground truth (isolated context)
                ground_truth = await self._generate_workflow_ground_truth(workflow)
                scenario_set.add_workflow_ground_truth(ground_truth)
                logger.debug(f"Generated ground truth for workflow: {workflow_name}")

                # Generate workflow scenarios
                scenarios = await self._generate_workflow_scenario(workflow, ground_truth.id)
                for scenario in scenarios:
                    scenario_set.add_workflow_scenario(scenario)
                logger.debug(f"Generated {len(scenarios)} scenarios for workflow: {workflow_name}")

            except Exception as e:
                logger.warning(f"Failed to generate workflow '{workflow_name}': {e}")

    async def _analyze_workflows(
        self,
        discovery: DiscoveryResult,
    ) -> list[dict]:
        """Analyze server capabilities to identify potential workflows.

        Args:
            discovery: The complete discovery results.

        Returns:
            List of workflow definitions.
        """
        prompt = build_workflow_analysis_prompt(discovery)
        response = await self.llm_client.generate_json(
            prompt,
            system_prompt=WORKFLOW_ANALYSIS_SYSTEM_PROMPT,
        )

        return response.get("workflows", [])

    async def _generate_workflow_ground_truth(
        self,
        workflow: dict,
    ) -> WorkflowGroundTruth:
        """Generate ground truth for a workflow.

        Args:
            workflow: The workflow definition from analysis.

        Returns:
            WorkflowGroundTruth for the workflow.
        """
        workflow_name = workflow.get("name", "unnamed_workflow")
        workflow_description = workflow.get("description", "")
        steps = workflow.get("steps", [])
        involved_features = workflow.get("involved_features", [])

        prompt = build_workflow_ground_truth_prompt(
            workflow_name,
            workflow_description,
            steps,
            involved_features,
        )

        response = await self.llm_client.generate_json(
            prompt,
            system_prompt=WORKFLOW_GROUND_TRUTH_SYSTEM_PROMPT,
        )

        ground_truth_id = WorkflowGroundTruth.generate_id(workflow_name)

        return WorkflowGroundTruth(
            id=ground_truth_id,
            workflow_name=workflow_name,
            expected_flow=response.get("expected_flow", ""),
            step_expectations=response.get("step_expectations", []),
            final_outcome=response.get("final_outcome", ""),
            error_scenarios=response.get("error_scenarios", []),
        )

    async def _generate_workflow_scenario(
        self,
        workflow: dict,
        ground_truth_id: str,
    ) -> list[WorkflowScenario]:
        """Generate test scenarios for a workflow.

        Args:
            workflow: The workflow definition from analysis.
            ground_truth_id: The ID of the pre-generated workflow ground truth.

        Returns:
            List of WorkflowScenario objects.
        """
        workflow_name = workflow.get("name", "unnamed_workflow")
        workflow_description = workflow.get("description", "")
        steps_data = workflow.get("steps", [])
        involved_features = workflow.get("involved_features", [])

        prompt = build_workflow_scenario_prompt(
            workflow_name,
            workflow_description,
            steps_data,
            ground_truth_id,
            involved_features,
        )

        response = await self.llm_client.generate_json(
            prompt,
            system_prompt=WORKFLOW_SCENARIO_SYSTEM_PROMPT,
        )

        scenarios = []
        scenarios_data = response.get("scenarios", [])

        for idx, scenario_data in enumerate(scenarios_data):
            # Parse steps from workflow definition
            steps = []
            for step_data in steps_data:
                step = WorkflowStep(
                    step_number=step_data.get("step_number", 0),
                    action_type=step_data.get("action_type", "tool_call"),
                    target_name=step_data.get("target_name", ""),
                    description=step_data.get("description", ""),
                    input_source=step_data.get("input_source", "literal"),
                    output_variable=step_data.get("output_variable"),
                    dependencies=step_data.get("dependencies", []),
                )
                steps.append(step)

            scenario_id = WorkflowScenario.generate_id(workflow_name, idx)

            scenario = WorkflowScenario(
                id=scenario_id,
                name=scenario_data.get("name", f"{workflow_name} scenario {idx}"),
                description=scenario_data.get("description", ""),
                steps=steps,
                gherkin=scenario_data.get("gherkin", ""),
                ground_truth_id=ground_truth_id,
                involved_features=involved_features,
            )
            scenarios.append(scenario)

        return scenarios

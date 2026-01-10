"""Test Implementor for generating executable Behave tests.

This module provides the TestImplementor class which converts generated
Gherkin scenarios into executable Behave BDD tests. It generates:
- .feature files from ScenarioSet
- Python step definitions (LLM-generated)
- environment.py for Behave hooks and setup
- ground_truth_client.py for runtime ground truth access
"""

import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..config import LLMConfig
from .llm_client import BaseLLMClient, LLMClientError, create_llm_client
from .models import FeatureFile, ScenarioSet, WorkflowScenario
from .prompts import (
    ENVIRONMENT_PY_TEMPLATE,
    GROUND_TRUTH_CLIENT_TEMPLATE,
    STEP_DEFINITION_SYSTEM_PROMPT,
    build_combined_step_definition_prompt,
    build_step_definition_prompt,
    build_workflow_step_definition_prompt,
)

logger = logging.getLogger(__name__)


class TestImplementorError(Exception):
    """Exception raised when test implementation fails."""

    pass


class TestImplementation(BaseModel):
    """Result of test implementation generation.

    Attributes:
        output_dir: Directory where tests were generated.
        feature_files: List of generated .feature file paths.
        step_definitions_file: Path to the generated step definitions.
        environment_file: Path to the generated environment.py.
        ground_truth_client_file: Path to the generated ground_truth_client.py.
    """

    model_config = {"arbitrary_types_allowed": True}

    output_dir: Path
    feature_files: list[Path] = Field(default_factory=list)
    step_definitions_file: Optional[Path] = None
    environment_file: Optional[Path] = None
    ground_truth_client_file: Optional[Path] = None

    @property
    def feature_count(self) -> int:
        """Number of feature files generated."""
        return len(self.feature_files)

    @property
    def is_complete(self) -> bool:
        """Check if all required files were generated."""
        return (
            len(self.feature_files) > 0
            and self.step_definitions_file is not None
            and self.environment_file is not None
            and self.ground_truth_client_file is not None
        )


class TestImplementor:
    """Generates executable Behave tests from Gherkin scenarios.

    This class converts ScenarioSet (containing Gherkin scenarios and ground truths)
    into executable Behave BDD tests. It uses LLM to generate Python step definitions
    that implement the test logic.

    Example:
        ```python
        config = LLMConfig(provider="openai", model="gpt-4")
        implementor = TestImplementor(config)

        # Generate tests from scenario set
        result = await implementor.implement_tests(
            scenario_set=scenario_set,
            output_dir=Path(".mcp-probe/tests"),
            project_code="my-project",
            service_url="http://localhost:8000",
            server_command="python -m my_server",
        )

        print(f"Generated {result.feature_count} feature files")
        ```

    Attributes:
        llm_client: The LLM client for step definition generation.
    """

    def __init__(
        self,
        llm_config: LLMConfig,
        llm_client: Optional[BaseLLMClient] = None,
    ):
        """Initialize the test implementor.

        Args:
            llm_config: Configuration for the LLM provider.
            llm_client: Optional pre-configured LLM client.
        """
        self.llm_config = llm_config
        self._llm_client = llm_client

    @property
    def llm_client(self) -> BaseLLMClient:
        """Get the LLM client, creating it if necessary."""
        if self._llm_client is None:
            self._llm_client = create_llm_client(self.llm_config)
        return self._llm_client

    async def implement_tests(
        self,
        scenario_set: ScenarioSet,
        output_dir: Path,
        project_code: str,
        service_url: str,
        server_command: str,
    ) -> TestImplementation:
        """Generate complete executable Behave tests from scenarios.

        This is the main entry point that orchestrates all test generation:
        1. Creates directory structure
        2. Generates .feature files
        3. Generates step definitions via LLM
        4. Generates environment.py and ground_truth_client.py

        Args:
            scenario_set: The ScenarioSet containing scenarios and ground truths.
            output_dir: Directory to write generated tests.
            project_code: Project code for ground truth lookups.
            service_url: URL of the mcp-probe-service.
            server_command: Command to start the MCP server.

        Returns:
            TestImplementation with paths to all generated files.

        Raises:
            TestImplementorError: If generation fails.
        """
        result = TestImplementation(output_dir=output_dir)

        try:
            # Create directory structure
            self._create_directories(output_dir)

            # Step 1: Generate feature files
            logger.info("Generating feature files...")
            result.feature_files = await self.generate_feature_files(
                scenario_set, output_dir
            )
            logger.info(f"Generated {len(result.feature_files)} feature files")

            # Step 2: Generate step definitions
            logger.info("Generating step definitions...")
            result.step_definitions_file = await self.generate_step_definitions(
                scenario_set, output_dir
            )
            logger.info(f"Generated step definitions: {result.step_definitions_file}")

            # Step 3: Generate environment.py
            logger.info("Generating environment.py...")
            result.environment_file = await self.generate_environment(
                project_code=project_code,
                service_url=service_url,
                server_command=server_command,
                output_dir=output_dir,
            )
            logger.info(f"Generated environment: {result.environment_file}")

            # Step 4: Generate ground_truth_client.py
            logger.info("Generating ground_truth_client.py...")
            result.ground_truth_client_file = self._generate_ground_truth_client(
                output_dir
            )
            logger.info(
                f"Generated ground truth client: {result.ground_truth_client_file}"
            )

            return result

        except Exception as e:
            raise TestImplementorError(f"Failed to implement tests: {e}") from e

    def _create_directories(self, output_dir: Path) -> None:
        """Create the directory structure for Behave tests.

        Args:
            output_dir: Base output directory.
        """
        # Create main directories
        output_dir.mkdir(parents=True, exist_ok=True)

        # Features directory for .feature files
        features_dir = output_dir / "features"
        features_dir.mkdir(exist_ok=True)

        # Steps directory for step definitions
        steps_dir = output_dir / "features" / "steps"
        steps_dir.mkdir(exist_ok=True)

    async def generate_feature_files(
        self,
        scenario_set: ScenarioSet,
        output_dir: Path,
    ) -> list[Path]:
        """Generate .feature files from scenario set.

        Args:
            scenario_set: The ScenarioSet containing features and workflows.
            output_dir: Directory to write feature files.

        Returns:
            List of paths to generated feature files.
        """
        features_dir = output_dir / "features"
        generated_files = []

        # Generate feature files for regular features
        for feature in scenario_set.features:
            feature_path = self._write_feature_file(feature, features_dir)
            generated_files.append(feature_path)
            logger.debug(f"Generated feature: {feature_path}")

        # Generate feature files for workflow scenarios
        for workflow in scenario_set.workflow_scenarios:
            workflow_path = self._write_workflow_feature_file(workflow, features_dir)
            generated_files.append(workflow_path)
            logger.debug(f"Generated workflow feature: {workflow_path}")

        return generated_files

    def _write_feature_file(
        self,
        feature: FeatureFile,
        features_dir: Path,
    ) -> Path:
        """Write a single feature file.

        Args:
            feature: The feature to write.
            features_dir: Directory to write the file.

        Returns:
            Path to the written file.
        """
        # Generate safe filename
        safe_name = (
            feature.target_name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "_")
            .lower()
        )
        filename = f"{feature.target_type.value}_{safe_name}.feature"
        filepath = features_dir / filename

        with open(filepath, "w") as f:
            f.write(feature.gherkin)

        return filepath

    def _write_workflow_feature_file(
        self,
        workflow: WorkflowScenario,
        features_dir: Path,
    ) -> Path:
        """Write a workflow feature file.

        Args:
            workflow: The workflow scenario.
            features_dir: Directory to write the file.

        Returns:
            Path to the written file.
        """
        # Generate safe filename
        safe_name = (
            workflow.name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "_")
            .lower()
        )
        filename = f"workflow_{safe_name}.feature"
        filepath = features_dir / filename

        # Build complete feature file content
        content = f"""Feature: Workflow - {workflow.name}
  # Ground Truth ID: {workflow.ground_truth_id}
  # Involved Features: {', '.join(workflow.involved_features)}

{workflow.gherkin}
"""

        with open(filepath, "w") as f:
            f.write(content)

        return filepath

    async def generate_step_definitions(
        self,
        scenario_set: ScenarioSet,
        output_dir: Path,
    ) -> Path:
        """Generate Python step definitions via LLM.

        Args:
            scenario_set: The ScenarioSet to generate steps for.
            output_dir: Directory to write step definitions.

        Returns:
            Path to the generated step definitions file.

        Raises:
            TestImplementorError: If LLM generation fails.
        """
        steps_dir = output_dir / "features" / "steps"
        steps_file = steps_dir / "mcp_steps.py"

        try:
            # Build prompt for combined step definitions
            prompt = build_combined_step_definition_prompt(scenario_set)

            # Generate step definitions via LLM
            response = await self.llm_client.generate(
                prompt,
                system_prompt=STEP_DEFINITION_SYSTEM_PROMPT,
            )

            # Extract Python code from response
            code = self._extract_python_code(response.content)

            # Write step definitions file
            with open(steps_file, "w") as f:
                f.write(code)

            # Create __init__.py in steps directory
            init_file = steps_dir / "__init__.py"
            init_file.touch()

            return steps_file

        except LLMClientError as e:
            raise TestImplementorError(
                f"Failed to generate step definitions: {e}"
            ) from e

    def _extract_python_code(self, content: str) -> str:
        """Extract Python code from LLM response.

        The LLM may wrap code in markdown code blocks.

        Args:
            content: The LLM response content.

        Returns:
            Extracted Python code.
        """
        # Check if content is wrapped in markdown code blocks
        if "```python" in content:
            # Extract code between ```python and ```
            start = content.find("```python") + len("```python")
            end = content.rfind("```")
            if end > start:
                return content[start:end].strip()

        if "```" in content:
            # Generic code block
            start = content.find("```") + 3
            # Skip language identifier if present
            newline = content.find("\n", start)
            if newline != -1:
                start = newline + 1
            end = content.rfind("```")
            if end > start:
                return content[start:end].strip()

        # Return as-is if no code blocks found
        return content.strip()

    async def generate_environment(
        self,
        project_code: str,
        service_url: str,
        server_command: str,
        output_dir: Path,
    ) -> Path:
        """Generate Behave environment.py file.

        Args:
            project_code: Project code for ground truth lookups.
            service_url: URL of the mcp-probe-service.
            server_command: Command to start the MCP server.
            output_dir: Directory to write the file.

        Returns:
            Path to the generated environment.py file.
        """
        features_dir = output_dir / "features"
        env_file = features_dir / "environment.py"

        # Format the template with actual values
        content = ENVIRONMENT_PY_TEMPLATE.format(
            service_url=service_url,
            project_code=project_code,
            server_command=server_command,
        )

        with open(env_file, "w") as f:
            f.write(content)

        return env_file

    def _generate_ground_truth_client(self, output_dir: Path) -> Path:
        """Generate the ground truth client module.

        Args:
            output_dir: Directory to write the file.

        Returns:
            Path to the generated ground_truth_client.py file.
        """
        features_dir = output_dir / "features"
        client_file = features_dir / "ground_truth_client.py"

        with open(client_file, "w") as f:
            f.write(GROUND_TRUTH_CLIENT_TEMPLATE)

        return client_file

    async def generate_feature_step_definitions(
        self,
        feature: FeatureFile,
        ground_truth: dict[str, Any],
        output_dir: Path,
    ) -> Path:
        """Generate step definitions for a single feature.

        This method generates step definitions specifically for one feature,
        useful when regenerating tests for a specific capability.

        Args:
            feature: The feature file.
            ground_truth: The ground truth specification.
            output_dir: Directory to write the file.

        Returns:
            Path to the generated step definitions file.

        Raises:
            TestImplementorError: If generation fails.
        """
        steps_dir = output_dir / "features" / "steps"
        safe_name = (
            feature.target_name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "_")
            .lower()
        )
        steps_file = steps_dir / f"{feature.target_type.value}_{safe_name}_steps.py"

        try:
            prompt = build_step_definition_prompt(feature, ground_truth)

            response = await self.llm_client.generate(
                prompt,
                system_prompt=STEP_DEFINITION_SYSTEM_PROMPT,
            )

            code = self._extract_python_code(response.content)

            with open(steps_file, "w") as f:
                f.write(code)

            return steps_file

        except LLMClientError as e:
            raise TestImplementorError(
                f"Failed to generate step definitions for {feature.name}: {e}"
            ) from e

    async def generate_workflow_step_definitions(
        self,
        workflow: WorkflowScenario,
        ground_truth: dict[str, Any],
        output_dir: Path,
    ) -> Path:
        """Generate step definitions for a workflow scenario.

        Args:
            workflow: The workflow scenario.
            ground_truth: The workflow ground truth specification.
            output_dir: Directory to write the file.

        Returns:
            Path to the generated step definitions file.

        Raises:
            TestImplementorError: If generation fails.
        """
        steps_dir = output_dir / "features" / "steps"
        safe_name = (
            workflow.name.replace("/", "_")
            .replace(" ", "_")
            .replace("-", "_")
            .lower()
        )
        steps_file = steps_dir / f"workflow_{safe_name}_steps.py"

        try:
            prompt = build_workflow_step_definition_prompt(workflow, ground_truth)

            response = await self.llm_client.generate(
                prompt,
                system_prompt=STEP_DEFINITION_SYSTEM_PROMPT,
            )

            code = self._extract_python_code(response.content)

            with open(steps_file, "w") as f:
                f.write(code)

            return steps_file

        except LLMClientError as e:
            raise TestImplementorError(
                f"Failed to generate step definitions for workflow {workflow.name}: {e}"
            ) from e

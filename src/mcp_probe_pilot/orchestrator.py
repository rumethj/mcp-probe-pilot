"""Pipeline orchestrator for MCP-Probe.

Loads configuration, runs MCP server discovery, indexes the codebase
via AST parsing, and coordinates the full probe pipeline.
"""

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from mcp_probe_pilot.core.models import (
    ProbeConfig,
    CodebaseIndex, 
    DiscoveryResult,
    IntegrationTestPlanResult,
    UnitTestPlanResult,
    GherkinFeatureCollection,
    TestExecutionResult,
    StepImplementationResult,
)
from mcp_probe_pilot.core.llm_client import LLMClient
from mcp_probe_pilot.core.mcp_session import MCPSession
from mcp_probe_pilot.core.service_client import MCPProbeServiceClient, ServiceClientError
from mcp_probe_pilot.discover.discoverer import MCPDiscoverer
from mcp_probe_pilot.discover.ast_indexer import ASTIndexer
from mcp_probe_pilot.generate.gherkin_feature_generator import (
    GenerationResult,
    GherkinFeatureGenerator,
)
from mcp_probe_pilot.generate.gherkin_formatter import GherkinFormatter
from mcp_probe_pilot.generate.step_implementation_generator import (
    StepImplementationGenerator,
)

from mcp_probe_pilot.execute.executor import TestExecutor, ExecutorError
from mcp_probe_pilot.plan.planner import Planner

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "mcp-probe-service-properties.json"


class OrchestratorError(Exception):
    """Base exception for orchestrator failures."""


class ConfigLoadError(OrchestratorError):
    """Raised when the configuration file cannot be loaded or validated."""


class MCPProbeOrchestrator:
    """Coordinates the full MCP-Probe pipeline: config -> discovery -> index -> generate."""

    def __init__(self, repository_root: Path, generate_new: bool = False) -> None:
        self.repository_root = repository_root
        self.generate_new = generate_new
        self.config = self._load_config(repository_root)
        self.config.generate_new = generate_new

        # Discovery Information
        self.discovery_result: DiscoveryResult | None = None
        self.codebase_index: CodebaseIndex | None = None

        # Planning Results
        self.unit_test_plan: UnitTestPlanResult | None = None
        self.integration_test_plan: IntegrationTestPlanResult | None = None

        # Feature Collection (from validation/formatting step)
        self.feature_collection: GherkinFeatureCollection | None = None

        # Accumulated test dependencies (built up across pipeline stages)
        self.test_dependencies: list[str] = []


    @staticmethod
    def _load_config(repo_root: Path) -> ProbeConfig:
        """Load and validate the ProbeConfig from the repository root.

        Raises:
            ConfigLoadError: If the file is missing, malformed, or fails validation.
        """
        config_path = repo_root / CONFIG_FILENAME

        if not config_path.exists():
            raise ConfigLoadError(
                f"Configuration file not found at {config_path}"
            )

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)
            return ProbeConfig(**raw_config)
        except json.JSONDecodeError as exc:
            raise ConfigLoadError(
                f"Invalid JSON in {config_path}: {exc}"
            ) from exc
        except ValidationError as exc:
            field_errors = "; ".join(
                f"{e['loc'][0]}: {e['msg']}" for e in exc.errors()
            )
            raise ConfigLoadError(
                f"Invalid config in {config_path} — {field_errors}"
            ) from exc
    
    
    # ------------------------------------------------------------------
    # Informational Getters
    # ------------------------------------------------------------------

    def get_server_command(self) -> str:
        return self.config.server_command
    
    def get_transport(self) -> str:
        return self.config.transport
    
    def get_service_url(self) -> str:
        return self.config.service_url
    
    def get_generate_new(self) -> bool:
        return self.config.generate_new


    # ------------------------------------------------------------------
    # MCP Probe Pipeline Executors
    # ------------------------------------------------------------------
    
    async def run_discovery(self) -> DiscoveryResult:
        """Connect to the MCP server and discover its capabilities."""
        logger.info("Starting MCP server discovery: %s", self.config.server_command)
        async with MCPSession(self.config.server_command, cwd=self.repository_root) as session:
            discoverer = MCPDiscoverer(session)
            self.discovery_result = await discoverer.discover_all()
        logger.info(
            "Discovery complete: %d tools, %d resources, %d prompts",
            self.discovery_result.tool_count,
            self.discovery_result.resource_count,
            self.discovery_result.prompt_count,
        )
        return self.discovery_result

    def run_ast_indexing(self) -> CodebaseIndex:
        """Index the repository source code via AST parsing."""
        logger.info("Indexing codebase at %s", self.repository_root)
        indexer = ASTIndexer()
        self.codebase_index = indexer.index_directory(self.repository_root)
        logger.info(
            "AST indexing complete: %d entities from %d files",
            self.codebase_index.total_entities,
            self.codebase_index.total_files,
        )
        return self.codebase_index

    async def send_codebase_index(self) -> dict:
        """Send the codebase index to the mcp-probe-service for ChromaDB storage.

        Raises:
            OrchestratorError: If no codebase index is available or the upload fails.
        """
        if self.codebase_index is None:
            raise OrchestratorError(
                "No codebase index available. Run run_ast_indexing() first."
            )

        entities = [
            entity.model_dump() for entity in self.codebase_index.entities
        ]
        logger.info(
            "Sending %d entities to mcp-probe-service at %s",
            len(entities),
            self.config.service_url,
        )

        try:
            async with MCPProbeServiceClient(base_url=self.config.service_url) as client:
                result = await client.index_codebase(entities)
        except ServiceClientError as exc:
            raise OrchestratorError(
                f"Failed to send codebase index to service: {exc}"
            ) from exc

        logger.info("Codebase index sent successfully: %s", result)
        return result

    # ------------------------------------------------------------------
    # Test Planning
    # ------------------------------------------------------------------

    def run_unit_test_planning(self) -> UnitTestPlanResult:
        """Generate unit-test scenario plans for every discovered primitive.

        Raises:
            OrchestratorError: If discovery has not been run yet.
        """
        if self.discovery_result is None:
            raise OrchestratorError(
                "No discovery result available. Run run_discovery() first."
            )

        with LLMClient() as llm:
            planner = Planner(llm)

            tool_scenarios = []
            for tool in self.discovery_result.tools:
                logger.info("Planning unit tests for tool: %s", tool.name)
                tool_scenarios.extend(planner.plan_tool_unit_tests(tool))

            resource_scenarios = []
            for resource in self.discovery_result.resources:
                logger.info("Planning unit tests for resource: %s", resource.uri)
                resource_scenarios.extend(
                    planner.plan_resource_unit_tests(resource)
                )

            prompt_scenarios = []
            for prompt in self.discovery_result.prompts:
                logger.info("Planning unit tests for prompt: %s", prompt.name)
                prompt_scenarios.extend(
                    planner.plan_prompt_unit_tests(prompt)
                )

        self.unit_test_plan = UnitTestPlanResult(
            tool_scenarios=tool_scenarios,
            resource_scenarios=resource_scenarios,
            prompt_scenarios=prompt_scenarios,
        )
        logger.info(
            "Unit test planning complete: %d total scenarios",
            self.unit_test_plan.num_scenarios,
        )
        return self.unit_test_plan

    def run_integration_test_planning(self) -> IntegrationTestPlanResult:
        """Identify cross-primitive integration-test workflow scenarios.

        Raises:
            OrchestratorError: If discovery has not been run yet.
        """
        if self.discovery_result is None:
            raise OrchestratorError(
                "No discovery result available. Run run_discovery() first."
            )

        with LLMClient() as llm:
            planner = Planner(llm)
            self.integration_test_plan = planner.plan_integration_tests(
                self.discovery_result
            )

        logger.info(
            "Integration test planning complete: %d workflow scenarios",
            self.integration_test_plan.num_scenarios,
        )
        return self.integration_test_plan

    # ------------------------------------------------------------------
    # Feature File Generation
    # ------------------------------------------------------------------

    async def generate_feature_files(self) -> GenerationResult:
        """Generate Gherkin .feature files from the test plans.

        Raises:
            OrchestratorError: If discovery or planning has not been run yet.
        """
        # Initial checks
        if self.discovery_result is None:
            raise OrchestratorError(
                "No discovery result available. Run run_discovery() first."
            )
        if self.unit_test_plan is None:
            raise OrchestratorError(
                "No unit test plan available. Run run_unit_test_planning() first."
            )
        if self.integration_test_plan is None:
            raise OrchestratorError(
                "No integration test plan available. "
                "Run run_integration_test_planning() first."
            )

        output_dir = self.repository_root / "features"

        with LLMClient() as llm:
            async with MCPProbeServiceClient(
                base_url=self.config.service_url
            ) as service:
                generator = GherkinFeatureGenerator(
                    llm=llm,
                    service_client=service,
                    output_dir=output_dir,
                    discovery_result=self.discovery_result,
                    server_command=self.config.server_command,
                )
                result = await generator.generate_all(
                    unit_plan=self.unit_test_plan,
                    integration_plan=self.integration_test_plan,
                )

        logger.info(
            "Feature generation complete: %d generated, %d failed",
            result.files_generated,
            result.files_failed,
        )
        return result

    # ------------------------------------------------------------------
    # Feature File Validation and Formatting
    # ------------------------------------------------------------------

    def validate_and_format_feature_files(self) -> GherkinFeatureCollection:
        """Validate and normalize feature files for step consistency.

        Parses all .feature files in the features directory, normalizes step text
        to canonical patterns, and writes the normalized files back to disk.

        Returns:
            GherkinFeatureCollection: The parsed and normalized collection of features,
            ready for use in the step implementation generation stage.

        Raises:
            OrchestratorError: If no feature files exist.
        """
        features_dir = self.repository_root / "features"

        if not features_dir.exists():
            raise OrchestratorError(
                f"Features directory not found at {features_dir}. "
                "Run generate_feature_files() first."
            )

        feature_files = list(features_dir.glob("*.feature"))
        if not feature_files:
            raise OrchestratorError(
                f"No feature files found in {features_dir}. "
                "Run generate_feature_files() first."
            )

        logger.info(
            "Validating and formatting %d feature files in %s",
            len(feature_files),
            features_dir,
        )

        formatter = GherkinFormatter()
        self.feature_collection = formatter.format_directory(features_dir)

        logger.info(
            "Feature file formatting complete: %d features, %d unique steps",
            len(self.feature_collection.features),
            len(self.feature_collection.get_unique_step_texts()),
        )

        return self.feature_collection

    # ------------------------------------------------------------------
    # Step Implementation Generation
    # ------------------------------------------------------------------

    async def generate_step_implementations(self) -> StepImplementationResult:
        """Generate step implementations for the feature files.

        Processes each scenario sequentially, generating missing step
        implementations via LLM and appending them to the prebuilt steps.py.

        Raises:
            OrchestratorError: If feature collection is not available or
                prebuilts cannot be fetched.
        """
        if self.feature_collection is None:
            raise OrchestratorError(
                "No feature collection available. "
                "Run validate_and_format_feature_files() first."
            )

        output_dir = self.repository_root / "features"

        logger.info(
            "Generating step implementations for %d features with %d unique steps",
            len(self.feature_collection.features),
            len(self.feature_collection.get_unique_step_texts()),
        )

        try:
            async with MCPProbeServiceClient(
                base_url=self.config.service_url
            ) as service:
                written_files = await service.download_prebuilts(output_dir)
                logger.info(
                    "Downloaded %d prebuilt files to %s",
                    len(written_files),
                    output_dir,
                )

                prebuilt_data = await service.get_prebuilts()
        except ServiceClientError as exc:
            raise OrchestratorError(
                f"Failed to fetch prebuilts from service: {exc}"
            ) from exc

        prebuilt_files = prebuilt_data.get("files", [])
        self.test_dependencies = list(
            dict.fromkeys(prebuilt_data.get("dependencies", []))
        )
        logger.info(
            "Loaded %d prebuilt dependencies: %s",
            len(self.test_dependencies),
            self.test_dependencies,
        )

        steps_code = next(
            (
                f["content"]
                for f in prebuilt_files
                if f["path"].endswith("steps.py")
            ),
            "",
        )

        if not steps_code:
            logger.warning("No prebuilt steps.py found, starting from scratch")

        with LLMClient() as llm:
            generator = StepImplementationGenerator(
                llm=llm,
                prebuilt_steps_code=steps_code,
                output_dir=output_dir,
            )
            result = await generator.generate_all(self.feature_collection)

        if result.discovered_dependencies:
            new_deps = [
                d for d in result.discovered_dependencies
                if d not in self.test_dependencies
            ]
            self.test_dependencies.extend(new_deps)
            logger.info("Added %d step-generation dependencies: %s", len(new_deps), new_deps)

        logger.info(
            "Step implementation complete: %d generated, %d skipped, %d errors",
            result.steps_generated,
            result.steps_skipped,
            len(result.validation_errors),
        )

        if result.validation_errors:
            for error in result.validation_errors:
                logger.warning("Validation error: %s", error)

        return result

    # ------------------------------------------------------------------
    # Test Execution
    # ------------------------------------------------------------------

    def run_tests(self) -> TestExecutionResult:
        """Set up a test venv, install accumulated dependencies, and run behave.

        Dependencies are collected from earlier pipeline stages:
        - Prebuilt dependencies (fetched during step implementation generation)
        - Discovered dependencies (from step implementation results)
        - Future: healer-discovered dependencies

        Raises:
            OrchestratorError: If the test environment cannot be set up or
                the features directory is missing.
        """
        if not self.test_dependencies:
            logger.warning(
                "No test dependencies accumulated. "
                "Was generate_step_implementations() run?"
            )

        logger.info(
            "Running tests with %d dependencies: %s",
            len(self.test_dependencies),
            self.test_dependencies,
        )

        try:
            executor = TestExecutor(
                repo_root=self.repository_root,
                dependencies=self.test_dependencies,
            )
            executor.setup_environment()
            return executor.run_tests()
        except ExecutorError as exc:
            raise OrchestratorError(
                f"Test execution failed: {exc}"
            ) from exc

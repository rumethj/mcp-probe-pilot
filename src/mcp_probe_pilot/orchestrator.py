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
    UnitTestPlanResult
)
# from mcp_probe_pilot.core.models.discovery import CodebaseIndex, DiscoveryResult
# from mcp_probe_pilot.core.models.plan import (
#     IntegrationTestPlanResult,
#     UnitTestPlanResult,
# )
from mcp_probe_pilot.core.llm_client import LLMClient
from mcp_probe_pilot.core.mcp_session import MCPSession
from mcp_probe_pilot.core.service_client import MCPProbeServiceClient, ServiceClientError
from mcp_probe_pilot.discovery.discoverer import MCPDiscoverer
from mcp_probe_pilot.discovery.ast_indexer import ASTIndexer
from mcp_probe_pilot.generate.gherkin_feature_generator import (
    GenerationResult,
    GherkinFeatureGenerator,
)
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

        output_dir = self.repository_root / ".mcp-probe" / "features"

        with LLMClient() as llm:
            async with MCPProbeServiceClient(
                base_url=self.config.service_url
            ) as service:
                generator = GherkinFeatureGenerator(
                    llm=llm,
                    service_client=service,
                    output_dir=output_dir,
                    discovery_result=self.discovery_result,
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

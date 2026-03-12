"""Pipeline orchestrator for MCP-Probe.

Loads configuration, runs MCP server discovery, indexes the codebase
via AST parsing, and coordinates the full probe pipeline.
"""

import json
import logging
import os
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from mcp_probe_pilot.core.models import (
    ProbeConfig,
    CodebaseIndex,
    DiscoveryResult,
    IntegrationTestPlanResult,
    UnitTestPlanResult,
    GherkinFeature,
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

from mcp_probe_pilot.compliance_engine.models import ComplianceReport
from mcp_probe_pilot.compliance_engine.validator import ComplianceValidator
from mcp_probe_pilot.core.models.report import ProbeReport
from mcp_probe_pilot.execute.executor import TestExecutor, ExecutorError
from mcp_probe_pilot.plan.planner import Planner
from mcp_probe_pilot.report_builder import build_and_push_report
from mcp_probe_pilot.validate.validator import FeatureValidator

TRAFFIC_FILENAME = "mcp-traffic.json"

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
        async with MCPSession(
            self.config.server_command,
            cwd=self.repository_root,
            errlog=open(os.devnull, "w"),
        ) as session:
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

    async def generate_feature_files(
        self,
        on_progress: Callable[[str, str, str], None] | None = None,
    ) -> GenerationResult:
        """Generate Gherkin .feature files from the test plans.

        Args:
            on_progress: Optional callback forwarded to the generator,
                invoked with (event, prim_type, prim_name).

        Raises:
            OrchestratorError: If discovery or planning has not been run yet.
        """
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
                    on_progress=on_progress,
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
        to canonical patterns, writes the normalized files back to disk, then
        runs canonical-compliance validation (auto-fixing where possible).

        Returns:
            GherkinFeatureCollection: The parsed, normalized, and validated
            collection of features.

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

        validator = FeatureValidator()
        self._validation_result = validator.validate_collection(
            self.feature_collection, auto_fix=True,
        )

        if self._validation_result.normalised > 0:
            formatter.write_feature_files(self.feature_collection)

        if self._validation_result.rejected > 0:
            for sr in self._validation_result.rejected_steps:
                logger.warning(
                    "Rejected step: '%s' — %s", sr.original_text, sr.reason,
                )

        logger.info(
            "Canonical validation: %d compliant, %d normalised, %d rejected "
            "(out of %d total)",
            self._validation_result.compliant,
            self._validation_result.normalised,
            self._validation_result.rejected,
            self._validation_result.total_steps,
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

    def run_tests(
        self,
        feature_file: Path | None = None,
    ) -> TestExecutionResult:
        """Set up a test venv, install accumulated dependencies, and run behave.

        Parameters
        ----------
        feature_file:
            Optional path to a single ``.feature`` file.  When provided
            only that feature is executed.

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
            return executor.run_tests(feature_file=feature_file)
        except ExecutorError as exc:
            raise OrchestratorError(
                f"Test execution failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # MCP Compliance Validation
    # ------------------------------------------------------------------

    def run_compliance_validation(self) -> ComplianceReport:
        """Validate captured JSON-RPC traffic against the MCP 2025-11-25 spec.

        Reads ``features/mcp-traffic.json`` (written by the behave
        environment hooks after test execution) and returns a structured
        compliance report.

        Raises:
            OrchestratorError: If the traffic file cannot be found or parsed.
        """
        traffic_path = self.repository_root / "features" / TRAFFIC_FILENAME

        if not traffic_path.exists():
            logger.warning(
                "Traffic file not found at %s — skipping compliance validation",
                traffic_path,
            )
            return ComplianceReport()

        logger.info("Running MCP compliance validation on %s", traffic_path)

        try:
            validator = ComplianceValidator()
            report = validator.validate_file(traffic_path)
        except Exception as exc:
            raise OrchestratorError(
                f"Compliance validation failed: {exc}"
            ) from exc

        logger.info(
            "Compliance validation complete: %d exchanges, %d errors, %d warnings",
            report.total_exchanges,
            report.total_errors,
            report.total_warnings,
        )
        return report

    # ------------------------------------------------------------------
    # Report Generation
    # ------------------------------------------------------------------

    async def generate_and_push_report(
        self,
        compliance_report: ComplianceReport,
    ) -> ProbeReport:
        """Build a ProbeReport from the latest artefacts and push it to the service.

        Should be called after both test execution and compliance validation
        have completed.  The report is pushed to the service but failures
        to reach the service are logged as warnings, not raised.
        """
        features_dir = self.repository_root / "features"
        project_code = self.config.project_code
        logger.info("Building probe report for project_code=%s", project_code)

        report = await build_and_push_report(
            project_code=project_code,
            features_dir=features_dir,
            compliance_report=compliance_report,
            service_url=self.config.service_url,
        )

        logger.info(
            "Report built: %d features, %d/%d scenarios passed, mcp_compliant=%s",
            report.total_features,
            report.passed_scenarios,
            report.total_scenarios,
            report.mcp_compliant,
        )
        return report

    # ------------------------------------------------------------------
    # Features storage (service-backed persistence)
    # ------------------------------------------------------------------

    async def check_previous_features(self) -> bool:
        """Check whether stored features exist in the service for this server_id."""
        try:
            async with MCPProbeServiceClient(
                base_url=self.config.service_url
            ) as client:
                data = await client.get_features(self.config.server_id)
        except ServiceClientError as exc:
            logger.warning(
                "Could not check for previous features: %s", exc,
            )
            return False

        if data is None:
            logger.info(
                "No stored features found for server_id=%s",
                self.config.server_id,
            )
            return False

        file_count = len(data.get("files", []))
        logger.info(
            "Found %d stored feature files for server_id=%s",
            file_count,
            self.config.server_id,
        )
        return file_count > 0

    async def pull_previous_features(self) -> list[Path]:
        """Download previously stored features and prepare for execution.

        Writes all files into ``repo_root/features/``, parses the feature
        collection, and syncs test dependencies so the executor is ready.

        Returns the list of paths written.
        """
        output_dir = self.repository_root / "features"
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with MCPProbeServiceClient(
                base_url=self.config.service_url
            ) as client:
                written = await client.download_features(
                    self.config.server_id, output_dir,
                )
        except ServiceClientError as exc:
            raise OrchestratorError(
                f"Failed to pull stored features from service: {exc}"
            ) from exc

        logger.info(
            "Pulled %d feature files for server_id=%s into %s",
            len(written),
            self.config.server_id,
            output_dir,
        )

        self._sync_requirements_deps()
        return written

    async def upload_features(self) -> dict:
        """Upload the current features/ directory to the service.

        Persists every storable file so future runs can skip generation.
        """
        features_dir = self.repository_root / "features"
        if not features_dir.is_dir():
            logger.warning(
                "Features directory %s does not exist — skipping upload",
                features_dir,
            )
            return {}

        try:
            async with MCPProbeServiceClient(
                base_url=self.config.service_url
            ) as client:
                result = await client.store_features(
                    self.config.server_id, features_dir,
                )
        except ServiceClientError as exc:
            raise OrchestratorError(
                f"Failed to upload features to service: {exc}"
            ) from exc

        logger.info(
            "Uploaded features for server_id=%s: %s",
            self.config.server_id,
            result,
        )
        return result

    # ------------------------------------------------------------------
    # Feature helpers
    # ------------------------------------------------------------------

    def repopulate_single_feature(
        self,
        feature: GherkinFeature,
    ) -> GherkinFeature:
        """Re-parse a single .feature file from disk and update the collection."""
        if feature.file_path is None:
            return feature

        formatter = GherkinFormatter()
        refreshed_collection = formatter.format_directory(
            feature.file_path.parent,
        )

        for f in refreshed_collection.features:
            if f.file_path and f.file_path.resolve() == feature.file_path.resolve():
                if self.feature_collection is not None:
                    self.feature_collection.features = [
                        f if (
                            existing.file_path
                            and existing.file_path.resolve() == f.file_path.resolve()
                        ) else existing
                        for existing in self.feature_collection.features
                    ]
                return f

        return feature

    def get_feature_by_path(self, feature_path: Path) -> GherkinFeature | None:
        """Look up a feature in the current collection by its file path."""
        if self.feature_collection is None:
            return None
        resolved = feature_path.resolve()
        for f in self.feature_collection.features:
            if f.file_path and f.file_path.resolve() == resolved:
                return f
        return None

    def _sync_requirements_deps(self) -> None:
        """Read features/requirements.txt and merge any new packages into
        ``self.test_dependencies`` so the executor picks them up."""
        req_file = self.repository_root / "features" / "requirements.txt"
        if not req_file.exists():
            return
        for line in req_file.read_text(encoding="utf-8").splitlines():
            pkg = line.strip()
            if pkg and not pkg.startswith("#") and pkg not in self.test_dependencies:
                self.test_dependencies.append(pkg)
                logger.info("Synced new dependency from requirements.txt: %s", pkg)

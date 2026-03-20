# mcp-probe-pilot Class Diagram

```mermaid
classDiagram
    direction TB

    %% ──────────────────────────────────────
    %% CLI & Orchestrator
    %% ──────────────────────────────────────

    class CLI {
        <<module: cli.py>>
        +app : Typer
        +main(repo_root, generate_new, debug)
    }

    class MCPProbeOrchestrator {
        +repository_root : Path
        +generate_new : bool
        +config : ProbeConfig
        +discovery_result : DiscoveryResult
        +codebase_index : CodebaseIndex
        +unit_test_plan : UnitTestPlanResult
        +integration_test_plan : IntegrationTestPlanResult
        +feature_collection : GherkinFeatureCollection
        +test_dependencies : list~str~
        +run_discovery() DiscoveryResult
        +run_ast_indexing() CodebaseIndex
        +send_codebase_index() dict
        +run_unit_test_planning() UnitTestPlanResult
        +run_integration_test_planning() IntegrationTestPlanResult
        +generate_feature_files(on_progress) GenerationResult
        +validate_and_format_feature_files() GherkinFeatureCollection
        +generate_step_implementations() StepImplementationResult
        +run_tests(feature_file) TestExecutionResult
        +run_compliance_validation() ComplianceReport
        +generate_and_push_report(compliance_report) ProbeReport
        +check_previous_features() bool
        +pull_previous_features() list~Path~
        +upload_features() dict
        +get_feature_by_path(feature_path) GherkinFeature
    }

    CLI --> MCPProbeOrchestrator : creates

    %% ──────────────────────────────────────
    %% Core Infrastructure
    %% ──────────────────────────────────────

    class MCPSession {
        <<async context manager>>
        -_command : str
        -_args : list~str~
        -_session : ClientSession
        -_timeout : float
        +connect()
        +disconnect()
        +list_tools() ListToolsResult
        +call_tool(name, arguments) CallToolResult
        +list_resources() ListResourcesResult
        +list_resource_templates() ListResourceTemplatesResult
        +read_resource(uri) ReadResourceResult
        +list_prompts() ListPromptsResult
        +get_prompt(name, arguments) GetPromptResult
        +server_info : Any
    }

    class LLMClient {
        <<context manager>>
        -_llm : ChatGoogleGenerativeAI
        +__enter__() ChatGoogleGenerativeAI
        +__exit__()
    }

    class MCPProbeServiceClient {
        <<async context manager>>
        +base_url : str
        +timeout : float
        -_client : AsyncClient
        +health_check() dict
        +index_codebase(entities) dict
        +query_codebase(query, n_results) list~dict~
        +get_prebuilts() dict
        +download_prebuilts(target_dir) list~Path~
        +get_features(server_id) dict
        +store_features(server_id, features_dir) dict
        +download_features(server_id, target_dir) list~Path~
    }

    %% ──────────────────────────────────────
    %% Discovery Module
    %% ──────────────────────────────────────

    class MCPDiscoverer {
        -_session : MCPSession
        +discover_all() DiscoveryResult
        +discover_tools() list~ToolInfo~
        +discover_resources() list~ResourceInfo~
        +discover_prompts() list~PromptInfo~
        +parse_server_info() ServerInfo
    }

    class ASTIndexer {
        +exclude_dirs : set~str~
        +exclude_files : set~str~
        +previous_hashes : dict~str, str~
        +index_directory(path) CodebaseIndex
        -_find_python_files(root) list~Path~
        -_parse_file(file_path, relative_path) list~CodeEntity~
        -_extract_entity(node, entity_type, ...) CodeEntity
    }

    MCPDiscoverer --> MCPSession : uses
    MCPProbeOrchestrator --> MCPDiscoverer : creates
    MCPProbeOrchestrator --> ASTIndexer : creates

    %% ──────────────────────────────────────
    %% Planning Module
    %% ──────────────────────────────────────

    class Planner {
        -_llm : ChatGoogleGenerativeAI
        +plan_tool_unit_tests(tool) list~ScenarioPlan~
        +plan_resource_unit_tests(resource) list~ScenarioPlan~
        +plan_prompt_unit_tests(prompt_info) list~ScenarioPlan~
        +plan_integration_tests(discovery) IntegrationTestPlanResult
    }

    MCPProbeOrchestrator --> Planner : creates
    Planner --> LLMClient : uses (via context manager)

    %% ──────────────────────────────────────
    %% Generation Module
    %% ──────────────────────────────────────

    class GherkinFeatureGenerator {
        -_llm : ChatGoogleGenerativeAI
        -_service_client : MCPProbeServiceClient
        -_output_dir : Path
        -_discovery : DiscoveryResult
        -_server_command : str
        -_semaphore : Semaphore
        -_generated_step_patterns : set~str~
        +generate_all(unit_plan, integration_plan, on_progress) GenerationResult
        -_generate_unit_feature(prim_type, prim_name, scenarios) dict
        -_generate_integration_feature(integration_plan) dict
        -_generate_and_validate(human_content, label) tuple
        -_call_llm(human_content) str
        -_query_code_context(query) str
    }

    class GherkinFormatter {
        -_normalizer : StepNormalizer
        -_parser : GherkinParser
        +parse_feature_files(directory) GherkinFeatureCollection
        +normalize_all_steps(collection) int
        +write_feature_files(collection, output_dir)
        +format_directory(directory) GherkinFeatureCollection
    }

    class GherkinParser {
        -_parser : Parser
        +parse_file(file_path) GherkinFeature
        +parse_directory(directory) GherkinFeatureCollection
    }

    class StepNormalizer {
        -_rules : list
        -_compiled_rules : list
        +normalize_text(text) str
        +normalize_table_header(header) str
        +normalize_step(step)
    }

    class StepImplementationGenerator {
        -_llm : ChatGoogleGenerativeAI
        -_prebuilt_steps_code : str
        -_output_dir : Path
        -_steps_file : Path
        -_implemented_patterns : dict
        -_generated_code_blocks : list~str~
        +generate_all(feature_collection) StepImplementationResult
        -_get_missing_steps(scenario) list~GherkinStep~
        -_generate_for_scenario(scenario, feature_name, missing_steps) str
        -_filter_duplicate_steps(code) str
        -_write_final_steps_file()
        -_validate_final_output(feature_collection) list~str~
    }

    GherkinFeatureGenerator --> MCPProbeServiceClient : queries code context
    GherkinFeatureGenerator --> LLMClient : uses (via context manager)
    GherkinFormatter --> GherkinParser : uses
    GherkinFormatter --> StepNormalizer : uses
    StepImplementationGenerator --> LLMClient : uses (via context manager)

    MCPProbeOrchestrator --> GherkinFeatureGenerator : creates
    MCPProbeOrchestrator --> GherkinFormatter : creates
    MCPProbeOrchestrator --> StepImplementationGenerator : creates
    MCPProbeOrchestrator --> MCPProbeServiceClient : creates
    MCPProbeOrchestrator --> MCPSession : creates
    MCPProbeOrchestrator --> LLMClient : creates

    %% ──────────────────────────────────────
    %% Validation Module
    %% ──────────────────────────────────────

    class FeatureValidator {
        -_registry : CanonicalStepRegistry
        -_normaliser : StepNormaliser
        +validate_collection(collection, auto_fix) ValidationResult
        +validate_feature(feature, auto_fix) FeatureValidationResult
    }

    class CanonicalStepRegistry {
        -_patterns : list~tuple~
        +match(step_text) str
        +match_for_keyword(step_text, keyword) str
    }

    class StepNormaliser {
        <<validate module>>
        -_rules : list
        +normalise(text) str
    }

    FeatureValidator --> CanonicalStepRegistry : uses
    FeatureValidator --> StepNormaliser : uses
    MCPProbeOrchestrator --> FeatureValidator : creates

    %% ──────────────────────────────────────
    %% Execution Module
    %% ──────────────────────────────────────

    class TestExecutor {
        +repo_root : Path
        +dependencies : list~str~
        +timeout : int
        -_venv_path : Path
        -_python : Path
        +setup_environment()
        +run_tests(feature_file) TestExecutionResult
        +cleanup()
    }

    MCPProbeOrchestrator --> TestExecutor : creates

    %% ──────────────────────────────────────
    %% Compliance Engine
    %% ──────────────────────────────────────

    class ComplianceValidator {
        +validate_file(traffic_path) ComplianceReport
        +validate_traffic(data) ComplianceReport
        -_validate_scenario(scenario_data) ScenarioComplianceResult
        -_validate_exchange(idx, exchange) list~ExchangeViolation~
        -_validate_request_response(idx, method, exchange) list~ExchangeViolation~
        -_validate_initialize(idx, result) list~ExchangeViolation~
        -_validate_tools_list(idx, result) list~ExchangeViolation~
        -_validate_tools_call(idx, result) list~ExchangeViolation~
        -_validate_resources_list(idx, result) list~ExchangeViolation~
        -_validate_resources_read(idx, result) list~ExchangeViolation~
        -_validate_prompts_list(idx, result) list~ExchangeViolation~
        -_validate_prompts_get(idx, result) list~ExchangeViolation~
    }

    MCPProbeOrchestrator --> ComplianceValidator : creates

    %% ──────────────────────────────────────
    %% Data Models — Discovery
    %% ──────────────────────────────────────

    class ProbeConfig {
        <<BaseModel>>
        +project_code : str
        +server_command : str
        +transport : str
        +service_url : str
        +generate_new : bool
        +server_id : str «property»
    }

    class DiscoveryResult {
        <<BaseModel>>
        +server_info : ServerInfo
        +tools : list~ToolInfo~
        +resources : list~ResourceInfo~
        +prompts : list~PromptInfo~
        +tool_count : int
        +resource_count : int
        +prompt_count : int
    }

    class ServerInfo {
        <<BaseModel>>
        +name : str
        +version : str
        +protocol_version : str
        +capabilities : ServerCapabilities
    }

    class ServerCapabilities {
        <<BaseModel>>
        +tools : bool
        +resources : bool
        +prompts : bool
        +sampling : bool
        +logging : bool
    }

    class ToolInfo {
        <<BaseModel>>
        +name : str
        +description : str
        +input_schema : dict
    }

    class ResourceInfo {
        <<BaseModel>>
        +uri : str
        +name : str
        +description : str
        +mime_type : str
        +is_template : bool
    }

    class PromptInfo {
        <<BaseModel>>
        +name : str
        +description : str
        +arguments : list~PromptArgument~
    }

    class PromptArgument {
        <<BaseModel>>
        +name : str
        +description : str
        +required : bool
    }

    DiscoveryResult *-- ServerInfo
    DiscoveryResult *-- ToolInfo
    DiscoveryResult *-- ResourceInfo
    DiscoveryResult *-- PromptInfo
    ServerInfo *-- ServerCapabilities
    PromptInfo *-- PromptArgument

    %% ──────────────────────────────────────
    %% Data Models — Codebase Index
    %% ──────────────────────────────────────

    class CodebaseIndex {
        <<BaseModel>>
        +entities : list~CodeEntity~
        +file_hashes : dict~str, str~
        +total_files : int
        +total_entities : int
    }

    class CodeEntity {
        <<BaseModel>>
        +file_path : str
        +entity_type : str
        +name : str
        +code : str
        +start_line : int
        +end_line : int
        +docstring : str
        +decorators : list~str~
        +parent_class : str
        +qualified_name : str
    }

    CodebaseIndex *-- CodeEntity

    %% ──────────────────────────────────────
    %% Data Models — Planning
    %% ──────────────────────────────────────

    class ScenarioPlan {
        <<BaseModel>>
        +scenario : str
        +primitives : list~str~
        +pattern : str
    }

    class UnitTestPlanResult {
        <<BaseModel>>
        +tool_scenarios : list~ScenarioPlan~
        +resource_scenarios : list~ScenarioPlan~
        +prompt_scenarios : list~ScenarioPlan~
        +num_scenarios : int
    }

    class IntegrationTestPlanResult {
        <<BaseModel>>
        +integration_scenarios : list~ScenarioPlan~
        +num_scenarios : int
    }

    UnitTestPlanResult *-- ScenarioPlan
    IntegrationTestPlanResult *-- ScenarioPlan

    %% ──────────────────────────────────────
    %% Data Models — Gherkin
    %% ──────────────────────────────────────

    class GherkinStepType {
        <<Enum>>
        GIVEN
        WHEN
        THEN
    }

    class DataTable {
        <<BaseModel>>
        +headers : list~str~
        +rows : list~list~str~~
        +format(indent) list~str~
    }

    class GherkinStep {
        <<BaseModel>>
        +text : str
        +step_type : GherkinStepType
        +data_table : DataTable
    }

    class GherkinScenario {
        <<BaseModel>>
        +name : str
        +tags : list~str~
        +steps : list~GherkinStep~
        +given_steps : list~GherkinStep~
        +when_steps : list~GherkinStep~
        +then_steps : list~GherkinStep~
    }

    class GherkinFeature {
        <<BaseModel>>
        +name : str
        +description : str
        +file_path : Path
        +background : list~GherkinStep~
        +scenarios : list~GherkinScenario~
        +get_all_steps() list~GherkinStep~
        +write_to_file(file_path)
    }

    class GherkinFeatureCollection {
        <<BaseModel>>
        +features : list~GherkinFeature~
        +get_all_steps() list~GherkinStep~
        +get_unique_step_texts() set~str~
    }

    GherkinStep --> GherkinStepType
    GherkinStep *-- DataTable
    GherkinScenario *-- GherkinStep
    GherkinFeature *-- GherkinStep : background
    GherkinFeature *-- GherkinScenario
    GherkinFeatureCollection *-- GherkinFeature

    %% ──────────────────────────────────────
    %% Data Models — Generation & Execution
    %% ──────────────────────────────────────

    class GenerationResult {
        <<BaseModel>>
        +files_generated : int
        +files_failed : int
        +validation_warnings : list~str~
    }

    class StepImplementationResult {
        <<BaseModel>>
        +steps_generated : int
        +steps_skipped : int
        +output_file : Path
        +validation_errors : list~str~
        +discovered_dependencies : list~str~
    }

    class TestExecutionResult {
        <<BaseModel>>
        +success : bool
        +total_scenarios : int
        +passed : int
        +failed : int
        +errored : int
        +skipped : int
        +duration : float
        +raw_json : list~dict~
        +output_file : Path
    }

    %% ──────────────────────────────────────
    %% Data Models — Compliance
    %% ──────────────────────────────────────

    class ExchangeViolation {
        <<BaseModel>>
        +exchange_index : int
        +method : str
        +rule : str
        +message : str
        +path : str
        +severity : str
    }

    class ScenarioComplianceResult {
        <<BaseModel>>
        +feature_name : str
        +scenario_name : str
        +total_exchanges : int
        +violations : list~ExchangeViolation~
        +passed : bool
        +error_count : int
        +warning_count : int
    }

    class ComplianceReport {
        <<BaseModel>>
        +spec_version : str
        +scenarios : list~ScenarioComplianceResult~
        +passed : bool
        +total_violations : int
        +total_errors : int
        +total_warnings : int
        +total_exchanges : int
    }

    ComplianceReport *-- ScenarioComplianceResult
    ScenarioComplianceResult *-- ExchangeViolation

    %% ──────────────────────────────────────
    %% Report Builder Module
    %% ──────────────────────────────────────

    class ReportBuilder {
        <<module: report_builder.py>>
        +build_report(project_code, features_dir, compliance_report) ProbeReport
        +build_and_push_report(project_code, features_dir, compliance_report, service_url) ProbeReport
        -_derive_scenario_status(steps) str
        -_build_step_results(steps) list~StepResult~
        -_feature_duration(feature_dict) float
        -_build_compliance_detail(compliance_result) ScenarioComplianceDetail
        -_build_exchanges(raw_exchanges) list~Exchange~
    }

    class ReportBuildError {
        <<Exception>>
    }

    ReportBuilder --> ComplianceReport : reads
    ReportBuilder --> MCPProbeServiceClient : pushes report via
    MCPProbeOrchestrator --> ReportBuilder : calls

    %% ──────────────────────────────────────
    %% Data Models — Report
    %% ──────────────────────────────────────

    class ProbeReport {
        <<BaseModel>>
        +project_code : str
        +timestamp : datetime
        +summary_test_passed : bool
        +mcp_compliant : bool
        +code_coverage : float?
        +spec_version : str
        +total_features : int
        +total_scenarios : int
        +passed_scenarios : int
        +failed_scenarios : int
        +feature_reports : list~FeatureReport~
    }

    class FeatureReport {
        <<BaseModel>>
        +feature_name : str
        +summary_test_passed : bool
        +mcp_compliant : bool
        +duration : float
        +total_scenarios : int
        +passed_scenarios : int
        +failed_scenarios : int
        +scenarios : list~ScenarioReport~
    }

    class ScenarioReport {
        <<BaseModel>>
        +scenario_name : str
        +status : str
        +steps : list~StepResult~
        +compliance : ScenarioComplianceDetail
        +exchanges : list~Exchange~
    }

    class StepResult {
        <<BaseModel>>
        +name : str
        +status : str
        +error_message : str?
    }

    class ScenarioComplianceDetail {
        <<BaseModel>>
        +mcp_compliant : bool
        +total_exchanges : int
        +violations : list~ReportViolation~
    }

    class ReportViolation {
        <<BaseModel>>
        +exchange_index : int
        +method : str
        +rule : str
        +message : str
        +path : str
        +severity : str
    }

    class Exchange {
        <<BaseModel>>
        +method : str
        +type : str
        +request : dict?
        +response : dict?
        +message : dict?
    }

    ProbeReport *-- FeatureReport
    FeatureReport *-- ScenarioReport
    ScenarioReport *-- StepResult
    ScenarioReport *-- ScenarioComplianceDetail
    ScenarioReport *-- Exchange
    ScenarioComplianceDetail *-- ReportViolation

    MCPProbeOrchestrator --> ProbeReport : holds

    %% ──────────────────────────────────────
    %% Service-Side — Report Storage & Views
    %% ──────────────────────────────────────

    class ReportSummary {
        <<BaseModel — service>>
        +report_id : str
        +timestamp : datetime
        +summary_test_passed : bool
        +mcp_compliant : bool
        +total_scenarios : int
        +passed_scenarios : int
        +failed_scenarios : int
    }

    class ProjectSummary {
        <<BaseModel — service>>
        +project_code : str
        +latest_report : ReportSummary?
        +total_reports : int
    }

    class ReportsRouter {
        <<module: routes/reports.py>>
        +submit_report(project_code, report) dict
        +list_projects() list~ProjectSummary~
        +list_reports(project_code) list~ReportSummary~
        +get_latest_report(project_code) ProbeReport
        +get_report(project_code, report_id) ProbeReport
    }

    class ViewsRouter {
        <<module: routes/views.py>>
        +dashboard(request) HTMLResponse
        +project_detail(request, project_code) HTMLResponse
        +report_detail(request, project_code, report_id) HTMLResponse
        +feature_detail(request, project_code, report_id, feature_index) HTMLResponse
    }

    ProjectSummary *-- ReportSummary
    ReportsRouter --> ProbeReport : stores / retrieves
    ReportsRouter --> ReportSummary : returns
    ReportsRouter --> ProjectSummary : returns
    ViewsRouter --> ProbeReport : loads for rendering

    %% ──────────────────────────────────────
    %% Data Models — Validation
    %% ──────────────────────────────────────

    class StepStatus {
        <<Enum>>
        COMPLIANT
        NORMALISED
        REJECTED
    }

    class StepComplianceResult {
        <<dataclass>>
        +original_text : str
        +status : StepStatus
        +matched_pattern : str
        +normalised_text : str
        +reason : str
    }

    class ValidationResult {
        <<dataclass>>
        +total_features : int
        +total_steps : int
        +compliant : int
        +normalised : int
        +rejected : int
        +feature_results : list~FeatureValidationResult~
        +rejected_steps : list~StepComplianceResult~
        +is_valid : bool
    }

    StepComplianceResult --> StepStatus
    ValidationResult *-- StepComplianceResult

    %% ──────────────────────────────────────
    %% Orchestrator holds model instances
    %% ──────────────────────────────────────

    MCPProbeOrchestrator --> ProbeConfig : holds
    MCPProbeOrchestrator --> DiscoveryResult : holds
    MCPProbeOrchestrator --> CodebaseIndex : holds
    MCPProbeOrchestrator --> UnitTestPlanResult : holds
    MCPProbeOrchestrator --> IntegrationTestPlanResult : holds
    MCPProbeOrchestrator --> GherkinFeatureCollection : holds
```

import asyncio
import json
import logging
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from mcp_probe_pilot.orchestrator import MCPProbeOrchestrator, OrchestratorError

logger = logging.getLogger(__name__)
app = typer.Typer(
    add_completion=False,
    help="MCP-Probe — automated testing and compliance validation for MCP servers.",
    rich_markup_mode="rich",
)
console = Console()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def format_elapsed_time(seconds: float) -> str:
    """Format elapsed time as 'Xm Ys' or 'Xs'."""
    if seconds >= 60:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    return f"{seconds:.1f}s"


def setup_logging(repo_root: Path, debug: bool = False) -> Path:
    """Configure file-based logging for the pipeline run.

    The log file is truncated on each invocation (mode='w') so that
    its contents always reflect only the current run.
    """
    log_file = repo_root / "mcp-probe.log"
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="w", encoding="utf-8"),
        ],
    )
    return log_file


def _fatal(message: str) -> typer.Exit:
    """Display a prominent error panel and return a ``typer.Exit`` for the caller to raise."""
    console.print(
        Panel(
            f"[bold red]Fatal Error[/bold red]\n\n{message}",
            expand=False,
            border_style="red",
        )
    )
    return typer.Exit(code=1)


# ------------------------------------------------------------------
# Phase: Feature caching
# ------------------------------------------------------------------


def _try_pull_previous_features(
    orchestrator: MCPProbeOrchestrator,
    generate_new: bool,
) -> bool:
    """Check the service for cached features and pull them if available.

    When ``generate_new`` is False, queries the mcp-probe-service for
    previously stored feature files matching this server_id.  If found,
    they are downloaded into the features directory so the full
    generation phase can be skipped entirely.

    Returns True if cached features were successfully pulled.
    """
    if generate_new:
        return False

    with console.status(
        "[bold blue]Checking for previously stored features...[/bold blue]",
        spinner="dots",
    ):
        try:
            start_time = time.time()
            has_previous = asyncio.run(orchestrator.check_previous_features())
            elapsed = format_elapsed_time(time.time() - start_time)
            if has_previous:
                console.print(
                    f"[green]✓[/green] Found stored features for "
                    f"server_id=[bold]{orchestrator.config.server_id}[/bold]. "
                    f"Pulling and skipping to execution. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                pull_start = time.time()
                written = asyncio.run(orchestrator.pull_previous_features())
                pull_elapsed = format_elapsed_time(time.time() - pull_start)
                console.print(
                    f"[green]✓[/green] Pulled {len(written)} feature files. "
                    f"[dim](Ran in {pull_elapsed})[/dim]"
                )
                return True
            else:
                console.print(
                    f"[dim]No stored features found — proceeding with full pipeline.[/dim] "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                return False
        except Exception as exc:
            # Non-fatal: fall back to the full generation pipeline
            console.print(
                f"[yellow]⚠[/yellow] Could not check for stored features: {exc}. "
                f"Proceeding with full pipeline."
            )
            return False


# ------------------------------------------------------------------
# Phase: Discovery
# ------------------------------------------------------------------


def _print_discovery_table(result) -> None:
    """Render discovered MCP primitives (tools, resources, prompts) as a rich table."""
    if not result.tools and not result.resources and not result.prompts:
        return

    table = Table(show_header=True, expand=False, pad_edge=True)
    table.add_column("Type", style="bold")
    table.add_column("Name")
    table.add_column("Description", style="dim")

    for tool in result.tools:
        table.add_row("Tool", tool.name, tool.description or "")
    for res in result.resources:
        table.add_row("Resource", res.name or res.uri, res.description or "")
    for prompt in result.prompts:
        table.add_row("Prompt", prompt.name, prompt.description or "")

    console.print(table)


def _run_discovery_phase(orchestrator: MCPProbeOrchestrator) -> None:
    """Introspect the MCP server, AST-index its codebase, and upload the index.

    Runs three sub-steps under a shared spinner:
      1. Connect to the MCP server and enumerate tools, resources, and prompts.
      2. Parse the server's source files via AST to build a searchable index.
      3. Push the index to the mcp-probe-service for RAG retrieval during
         test generation.
    """
    with console.status(
        "[bold blue]Discovering MCP Server...[/bold blue]", spinner="dots"
    ):
        # 1/3 — MCP server capabilities
        with console.status(
            "[bold blue]    Discovering MCP Server capabilities...[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                result = asyncio.run(orchestrator.run_discovery())
                elapsed = format_elapsed_time(time.time() - start_time)
                console.print(
                    f"[green]✓ \\[Discovery 1/3][/green] Discovery complete! "
                    f"Found {result.tool_count} tools, "
                    f"{result.resource_count} resources, "
                    f"and {result.prompt_count} prompts. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                _print_discovery_table(result)
            except Exception as exc:
                raise _fatal(f"Discovery failed: {exc}")

        # 2/3 — AST codebase indexing
        with console.status(
            "[bold blue]    Discovering MCP Server Codebase...[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                index = orchestrator.run_ast_indexing()
                elapsed = format_elapsed_time(time.time() - start_time)
                console.print(
                    f"[green]✓ \\[Discovery 2/3][/green] AST indexing complete! "
                    f"Indexed {index.total_entities} entities from {index.total_files} files. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
            except Exception as exc:
                raise _fatal(f"AST indexing failed: {exc}")

        # 3/3 — upload index to service for RAG retrieval
        with console.status(
            "[bold blue]    Sending codebase index to mcp-probe-service...[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                result = asyncio.run(orchestrator.send_codebase_index())
                elapsed = format_elapsed_time(time.time() - start_time)
                indexed_count = result.get("indexed_count", "unknown")
                console.print(
                    f"[green]✓ \\[Discovery 3/3][/green] Codebase index sent to service! "
                    f"{indexed_count} entities indexed in ChromaDB. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
            except Exception as exc:
                raise _fatal(f"Failed to send codebase index: {exc}")


# ------------------------------------------------------------------
# Phase: Test generation
# ------------------------------------------------------------------


def _run_generation_phase(orchestrator: MCPProbeOrchestrator, debug: bool) -> None:
    """Plan and generate Gherkin test artefacts.

    Orchestrates five sequential sub-steps:
      1. Unit test planning — LLM creates scenario outlines per primitive.
      2. Integration test planning — LLM identifies cross-primitive workflows.
      3. Feature file generation — Gherkin .feature files written to disk.
      4. Validation & formatting — structural normalisation and step dedup.
      5. Step implementation — Python step definitions generated via LLM.
    """
    with console.status(
        "[bold blue]Generating Tests[/bold blue]", spinner="dots"
    ):
        # 1/5 — Unit test planning
        with console.status(
            "[bold blue]    Planning Unit Test Scenarios[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                result = orchestrator.run_unit_test_planning()
                elapsed = format_elapsed_time(time.time() - start_time)
                msg = (
                    f"[green]✓ \\[Test Generation 1/5][/green] Unit Test Planning complete! "
                    f"Planned {result.num_scenarios} scenarios. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                if debug:
                    scenario_plans_str = "\n".join(
                        str(val) for val in result.scenario_plans
                    )
                    msg += f"\nScenario plans:\n{scenario_plans_str}"
                console.print(msg)
            except Exception as exc:
                raise _fatal(f"Unit Test Planning failed: {exc}")

        # 2/5 — Integration test planning
        with console.status(
            "[bold blue]    Planning Integration Test Scenarios[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                result = orchestrator.run_integration_test_planning()
                elapsed = format_elapsed_time(time.time() - start_time)
                msg = (
                    f"[green]✓ \\[Test Generation 2/5][/green] Integration Test Planning complete! "
                    f"Generated {result.num_scenarios} scenarios. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                if debug:
                    scenario_plans_str = "\n".join(
                        str(val) for val in result.scenario_plans
                    )
                    msg += f"\nScenario plans:\n{scenario_plans_str}"
                console.print(msg)
            except Exception as exc:
                raise _fatal(f"Integration Test Planning failed: {exc}")

        # 3/5 — Feature file generation (uses a progress callback)
        def _on_feature_progress(event: str, prim_type: str, prim_name: str) -> None:
            """Callback invoked by the generator for each MCP primitive.

            ``event`` is one of 'start', 'done', or 'failed'.
            """
            label = f"{prim_type}/{prim_name}"
            if event == "start":
                console.print(f"  [blue]⧗[/blue] Generating [bold]{label}[/bold]...")
            elif event == "done":
                safe_name = prim_name.replace("/", "_").replace(" ", "_").lower()
                filename = f"{prim_type}_{safe_name}.feature"
                console.print(f"  [green]✓[/green] Generated [bold]{filename}[/bold]")
            elif event == "failed":
                console.print(f"  [red]✗[/red] Failed [bold]{label}[/bold]")

        try:
            start_time = time.time()
            console.print("  [bold blue]Generating Feature Files[/bold blue]")
            result = asyncio.run(
                orchestrator.generate_feature_files(on_progress=_on_feature_progress)
            )
            elapsed = format_elapsed_time(time.time() - start_time)
            console.print(
                f"[green]✓ \\[Test Generation 3/5][/green] Feature Files generated! "
                f"{result.files_generated} files written, {result.files_failed} failed. "
                f"[dim](Ran in {elapsed})[/dim]"
            )
            for warning in result.validation_warnings:
                console.print(f"  [yellow]⚠ {warning}[/yellow]")
        except Exception as exc:
            raise _fatal(f"Feature Files generation failed: {exc}")

        # 4/5 — Validate and format feature files
        with console.status(
            "[bold blue]    Validating and Formatting Feature Files[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                result = orchestrator.validate_and_format_feature_files()
                elapsed = format_elapsed_time(time.time() - start_time)
                console.print(
                    f"[green]✓ \\[Test Generation 4/5][/green] Feature Files validated and formatted! "
                    f"{len(result.get_unique_step_texts())} unique steps. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
            except Exception as exc:
                raise _fatal(
                    f"Feature Files validation and formatting failed: {exc}"
                )

        # 5/5 — Generate step implementations
        with console.status(
            "[bold blue]    Generating Step Implementations[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                result = asyncio.run(orchestrator.generate_step_implementations())
                elapsed = format_elapsed_time(time.time() - start_time)
                console.print(
                    f"[green]✓ \\[Test Generation 5/5][/green] Step Implementations generated! "
                    f"{result.steps_generated} steps generated, {result.steps_skipped} skipped. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                if result.output_file:
                    console.print(f"  [dim]Output: {result.output_file}[/dim]")
                for error in result.validation_errors:
                    console.print(f"  [yellow]⚠ {error}[/yellow]")
            except Exception as exc:
                raise _fatal(f"Step Implementations generation failed: {exc}")


# ------------------------------------------------------------------
# Phase: Test execution
# ------------------------------------------------------------------


def _run_execution_phase(
    orchestrator: MCPProbeOrchestrator,
    repo_root: Path,
) -> None:
    """Execute Behave tests per feature and collect JSON results.

    Each feature is run in isolation so a failure in one does not block
    the rest.  Raw JSON reports are accumulated and written to
    ``features/test-results.json`` for the reporting phase.
    """
    # Re-validate to ensure the feature collection is populated,
    # then clear stale traffic so compliance only sees this run's exchanges.
    orchestrator.validate_and_format_feature_files()
    orchestrator.clear_previous_traffic()

    feature_paths = sorted((repo_root / "features").glob("*.feature"))
    total_features = len(feature_paths)

    console.print(
        f"\n[bold]Executing Behave tests for {total_features} feature(s)...[/bold]"
    )

    all_raw_json: list = []
    execution_rows: list[tuple[str, str, str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Running features", total=total_features)

        for feat_idx, feature_path in enumerate(feature_paths, start=1):
            feature_name = feature_path.name
            feature = orchestrator.get_feature_by_path(feature_path)
            if feature is None:
                progress.console.print(
                    f"[yellow]⚠ Could not resolve feature model for "
                    f"{feature_name}, skipping.[/yellow]"
                )
                progress.advance(task_id)
                continue

            progress.update(
                task_id,
                description=f"Running [bold]{feature_name}[/bold]",
            )

            try:
                start_time = time.time()
                test_result = orchestrator.run_tests(feature_file=feature_path)
                elapsed = format_elapsed_time(time.time() - start_time)

                if test_result.success:
                    status = "[green]PASS[/green]"
                    detail = f"{test_result.passed}/{test_result.total_scenarios} passed"
                    progress.console.print(
                        f"  [green]✓[/green] {feature_name}: {detail} "
                        f"[dim]({elapsed})[/dim]"
                    )
                else:
                    status = "[red]FAIL[/red]"
                    detail = (
                        f"{test_result.passed} passed, {test_result.failed} failed, "
                        f"{test_result.errored} errored, {test_result.skipped} skipped"
                    )
                    progress.console.print(
                        f"  [yellow]⚠[/yellow] {feature_name}: {detail} "
                        f"[dim]({elapsed})[/dim]"
                    )

                execution_rows.append((feature_name, status, detail, elapsed))
            except Exception as exc:
                raise _fatal(f"Test execution failed for {feature_name}: {exc}")

            if test_result.raw_json:
                all_raw_json.extend(test_result.raw_json)
            else:
                progress.console.print(
                    f"  [yellow]⚠ Test runner crashed for {feature_name} (no JSON report).[/yellow]"
                )

            progress.advance(task_id)

    # Execution summary table
    if execution_rows:
        table = Table(title="Test Execution Summary", expand=False, show_lines=True)
        table.add_column("Feature", style="bold")
        table.add_column("Status")
        table.add_column("Details")
        table.add_column("Time", style="dim")
        for row in execution_rows:
            table.add_row(*row)
        console.print(table)

    results_file = repo_root / "features" / "test-results.json"
    if all_raw_json:
        results_file.write_text(
            json.dumps(all_raw_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ------------------------------------------------------------------
# Phase: Compliance validation
# ------------------------------------------------------------------


def _run_compliance_phase(orchestrator: MCPProbeOrchestrator):
    """Validate captured JSON-RPC traffic against the MCP specification.

    Reads the ``mcp-traffic.json`` file written by Behave environment
    hooks and checks each request/response exchange for spec conformance.

    Non-fatal: compliance failures are reported but do not abort the
    pipeline.  Returns the compliance report, or None if validation
    could not run.
    """
    console.print("\n[bold]Running MCP Compliance Validation...[/bold]")
    with console.status(
        "[bold blue]Validating JSON-RPC traffic against MCP 2025-11-25 spec...[/bold blue]",
        spinner="dots",
    ):
        try:
            start_time = time.time()
            compliance_report = orchestrator.run_compliance_validation()
            elapsed = format_elapsed_time(time.time() - start_time)

            if compliance_report.total_exchanges == 0:
                console.print(
                    f"[yellow]⚠[/yellow] No JSON-RPC traffic captured "
                    f"(mcp-traffic.json missing or empty). "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
            elif compliance_report.passed:
                console.print(
                    f"[green]✓[/green] MCP compliance: all "
                    f"{compliance_report.total_exchanges} exchanges passed! "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
            else:
                console.print(
                    f"[red]✗[/red] MCP compliance: "
                    f"{compliance_report.total_errors} error(s), "
                    f"{compliance_report.total_warnings} warning(s) "
                    f"across {compliance_report.total_exchanges} exchanges. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                for scenario_result in compliance_report.scenarios:
                    if not scenario_result.violations:
                        continue
                    console.print(
                        f"\n  [bold]{scenario_result.feature_name} / "
                        f"{scenario_result.scenario_name}[/bold]"
                    )
                    for v in scenario_result.violations:
                        severity_tag = (
                            "[red]ERROR[/red]"
                            if v.severity == "error"
                            else "[yellow]WARN[/yellow]"
                        )
                        console.print(
                            f"    {severity_tag} [{v.method}] "
                            f"{v.rule}: {v.message}"
                        )
            return compliance_report
        except Exception as exc:
            console.print(f"[red]✗[/red] Compliance validation failed: {exc}")
            return None


# ------------------------------------------------------------------
# Phase: Reporting
# ------------------------------------------------------------------


def _run_reporting_phase(orchestrator: MCPProbeOrchestrator, compliance_report) -> None:
    """Build and push the probe report to the mcp-probe-service.

    Combines test execution results with compliance data into a unified
    report.  Non-fatal: a push failure is logged as a warning so the
    pipeline can still complete.
    """
    console.print("\n[bold]Building and pushing report to service...[/bold]")
    with console.status(
        "[bold blue]Assembling probe report...[/bold blue]",
        spinner="dots",
    ):
        try:
            start_time = time.time()
            report, report_id = asyncio.run(
                orchestrator.generate_and_push_report(compliance_report)
            )
            elapsed = format_elapsed_time(time.time() - start_time)
            status_label = (
                "[green]PASS[/green]" if report.summary_test_passed
                else "[red]FAIL[/red]"
            )
            compliant_label = (
                "[green]Compliant[/green]" if report.mcp_compliant
                else "[red]Non-compliant[/red]"
            )
            console.print(
                f"[green]✓[/green] Report pushed: "
                f"{report.passed_scenarios}/{report.total_scenarios} scenarios passed "
                f"({status_label}), MCP {compliant_label}. "
                f"[dim](Ran in {elapsed})[/dim]"
            )
            if report_id:
                service_url = orchestrator.get_service_url().rstrip("/")
                project_code = orchestrator.config.project_code
                report_url = f"{service_url}/project/{project_code}/report/{report_id}"
                console.print(
                    f"[bold blue]View report:[/bold blue] {report_url}"
                )
        except Exception as exc:
            logger.warning("Failed to build/push report: %s", exc, exc_info=True)
            console.print(
                f"[yellow]⚠[/yellow] Failed to build/push report: {exc}"
            )


# ------------------------------------------------------------------
# Phase: Feature upload
# ------------------------------------------------------------------


def _run_upload_phase(orchestrator: MCPProbeOrchestrator) -> None:
    """Upload generated features to the service for caching.

    Persists feature files so subsequent runs with the same server_id
    can skip the generation phase entirely.  Non-fatal.
    """
    console.print("\n[bold]Uploading features to service...[/bold]")
    with console.status(
        "[bold blue]Storing features for future runs...[/bold blue]",
        spinner="dots",
    ):
        try:
            start_time = time.time()
            upload_result = asyncio.run(orchestrator.upload_features())
            elapsed = format_elapsed_time(time.time() - start_time)
            stored_count = upload_result.get("stored_count", 0)
            console.print(
                f"[green]✓[/green] Stored {stored_count} feature files for "
                f"server_id=[bold]{orchestrator.config.server_id}[/bold]. "
                f"[dim](Ran in {elapsed})[/dim]"
            )
        except Exception as exc:
            console.print(
                f"[yellow]⚠[/yellow] Failed to upload features: {exc}"
            )


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------


@app.command()
def main(
    repo_root: Path = typer.Argument(
        ...,
        help="Path to the repository root containing mcp-probe-service-properties.json",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    generate_new: bool = typer.Option(
        False,
        "--generate-new",
        help="Force regeneration of test files, ignoring any cached features",
        rich_help_panel="Generation Options",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable verbose debug logging to mcp-probe.log",
        rich_help_panel="Troubleshooting",
    ),
):
    """Run the full MCP-Probe pipeline: discover, generate, execute, validate, and report.

    Expects a repository directory containing an
    ``mcp-probe-service-properties.json`` configuration file.  The pipeline
    introspects the configured MCP server, generates Gherkin tests,
    executes them via Behave, validates MCP spec compliance from the
    captured JSON-RPC traffic, and pushes a report to the service.
    """
    log_file = setup_logging(repo_root, debug=debug)

    try:
        orchestrator = MCPProbeOrchestrator(
            repository_root=repo_root, generate_new=generate_new
        )
    except OrchestratorError as exc:
        raise _fatal(str(exc))

    console.print(
        Panel(
            f"[bold blue]MCP-Probe Configuration[/bold blue]\n\n"
            f"[bold]Server Command:[/bold] [dim]{orchestrator.get_server_command()}[/dim]\n"
            f"[bold]Transport:[/bold]      {orchestrator.get_transport()}\n"
            f"[bold]Service URL:[/bold]    {orchestrator.get_service_url()}\n"
            f"[bold]Generate New:[/bold]   {'[yellow]Yes[/yellow]' if orchestrator.get_generate_new() else 'No'}",
            expand=False,
            border_style="blue",
        )
    )

    console.print("\n[bold]Starting MCP-Probe Pipeline...[/bold]\n")
    pipeline_start_time = time.time()

    # Attempt to reuse cached features to skip the generation phase
    pulled_previous = _try_pull_previous_features(orchestrator, generate_new)

    if not pulled_previous:
        _run_discovery_phase(orchestrator)
        _run_generation_phase(orchestrator, debug)

    _run_execution_phase(orchestrator, repo_root)

    compliance_report = _run_compliance_phase(orchestrator)
    if compliance_report is not None:
        _run_reporting_phase(orchestrator, compliance_report)

    _run_upload_phase(orchestrator)

    total_elapsed = format_elapsed_time(time.time() - pipeline_start_time)
    console.print(
        Panel(
            f"[bold green]Pipeline finished![/bold green]  [dim](Total: {total_elapsed})[/dim]\n"
            f"[dim]Detailed logs: {log_file}[/dim]",
            expand=False,
            border_style="green",
        )
    )


if __name__ == "__main__":
    app()

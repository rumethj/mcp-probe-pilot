import asyncio
import logging
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from mcp_probe_pilot.orchestrator import MCPProbeOrchestrator, OrchestratorError

app = typer.Typer(add_completion=False, help="MCP-Probe CLI")
console = Console()


def format_elapsed_time(seconds: float) -> str:
    """Format elapsed time as 'Xm Ys' or 'Xs'."""
    if seconds >= 60:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    return f"{seconds:.1f}s"


def setup_logging(repo_root: Path, debug: bool = False) -> Path:
    """Configure logging to write to a file in the repository."""
    log_file = repo_root / "mcp-probe.log"
    
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="w", encoding="utf-8"),
        ],
    )
    return log_file


@app.command()
def main(
    repo_root: Path = typer.Argument(
        ...,
        help="Path to the repository root directory",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    generate_new: bool = typer.Option(
        False,
        "--generate-new",
        help="Generate new test files, overwriting any that already exist",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging",
    ),
):
    """
    Run the MCP-Probe pipeline using the configuration found in the repository root.
    """
    # Set up logging to file
    log_file = setup_logging(repo_root, debug=debug)
    
    try:
        orchestrator = MCPProbeOrchestrator(
            repository_root=repo_root, generate_new=generate_new
        )
    except OrchestratorError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(
        Panel(
            f"[bold red]MCP-Probe Configuration Loaded[/bold red]\n\n"
            f"[bold]Server Command:[/bold] [dim]{orchestrator.get_server_command()}[/dim]\n"
            f"[bold]Transport:[/bold]      {orchestrator.get_transport()}\n"
            f"[bold]Service URL:[/bold]    {orchestrator.get_service_url()}\n"
            f"[bold]Generate New Tests:[/bold]   {'[yellow]Yes[/yellow]' if orchestrator.get_generate_new() else 'No'}",
            expand=False,
        )
    )

    console.print("\n[bold]Starting MCP-Probe Pipeline...[/bold]")
    pipeline_start_time = time.time()

    # ------------------------------------------------------------------
    # Check for previously stored features (skip generation when possible)
    # ------------------------------------------------------------------
    pulled_previous = False
    if not generate_new:
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
                    pulled_previous = True
                else:
                    console.print(
                        f"[dim]No stored features found — proceeding with full pipeline.[/dim] "
                        f"[dim](Ran in {elapsed})[/dim]"
                    )
            except Exception as exc:
                console.print(
                    f"[yellow]⚠[/yellow] Could not check for stored features: {exc}. "
                    f"Proceeding with full pipeline."
                )

    # ------------------------------------------------------------------
    # Full generation pipeline (skipped when pulled_previous is True)
    # ------------------------------------------------------------------
    if not pulled_previous:
        # Step 1: MCP Server Discovery
        with console.status(
            "[bold blue]Discovering MCP Server...[/bold blue]", spinner="dots"
        ):
            # Step 1.1: Discover MCP Server capabilities
            with console.status(
                "[bold blue]    Discovering MCP Server capabilities...[/bold blue]", spinner="line"
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
                    if result.tools:
                        console.print("  [bold]Tools:[/bold]")
                        for tool in result.tools:
                            desc = f": [dim]{tool.description}[/dim]" if tool.description else ""
                            console.print(f"    - {tool.name}{desc}")
                    if result.resources:
                        console.print("  [bold]Resources:[/bold]")
                        for res in result.resources:
                            label = res.name or res.uri
                            desc = f": [dim]{res.description}[/dim]" if res.description else ""
                            console.print(f"    - {label}{desc}")
                    if result.prompts:
                        console.print("  [bold]Prompts:[/bold]")
                        for prompt in result.prompts:
                            desc = f": [dim]{prompt.description}[/dim]" if prompt.description else ""
                            console.print(f"    - {prompt.name}{desc}")
                except Exception as exc:
                    console.print(f"[red]✗[/red] Discovery failed: {exc}")
                    raise typer.Exit(code=1)

            # Step 1.2: AST Codebase Indexing
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
                    console.print(f"[red]✗[/red] AST indexing failed: {exc}")
                    raise typer.Exit(code=1)

            # Step 1.3: Send codebase index to mcp-probe-service
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
                    console.print(f"[red]✗[/red] Failed to send codebase index: {exc}")
                    raise typer.Exit(code=1)


        # Step 2: Test Generation Pipeline
        with console.status(
            "[bold blue]Generating Tests[/bold blue]",
            spinner="dots",
        ):
            # Step 2.1: Planning Unit Test Scenarios
            with console.status(
                "[bold blue]    Planning Unit Test Scenarios[/bold blue]",
                spinner="line",
            ):
                try:
                    start_time = time.time()
                    result = orchestrator.run_unit_test_planning()
                    elapsed = format_elapsed_time(time.time() - start_time)

                    msg = (
                        f"[green]✓ \\[Test Generation 1/6][/green] Unit Test Planning complete! "
                        f"Planned {result.num_scenarios} scenarios. "
                        f"[dim](Ran in {elapsed})[/dim]"
                    )
                    
                    if debug:
                        scenario_plans_str = '\n'.join(str(val) for val in result.scenario_plans)
                        msg += f"\nScenario plans:\n{scenario_plans_str}"
                    
                    console.print(msg)
                    
                except Exception as exc:
                    console.print(f"[red]✗[/red] Unit Test Planning failed: {exc}")
                    raise typer.Exit(code=1)
            
            # Step 2.2: Planning Integration Test Scenarios
            with console.status(
                "[bold blue]    Planning Integration Test Scenarios[/bold blue]",
                spinner="line",
            ):
                try:
                    start_time = time.time()
                    result = orchestrator.run_integration_test_planning()
                    elapsed = format_elapsed_time(time.time() - start_time)
                    
                    msg = (
                        f"[green]✓ \\[Test Generation 2/6][/green] Integration Test Planning complete! "
                        f"Generated {result.num_scenarios} scenarios. "
                        f"[dim](Ran in {elapsed})[/dim]"
                    )
                    
                    if debug:
                        scenario_plans_str = '\n'.join(str(val) for val in result.scenario_plans)
                        msg += f"\nScenario plans:\n{scenario_plans_str}"
                    
                    console.print(msg)
                except Exception as exc:
                    console.print(f"[red]✗[/red] Integration Test Planning failed: {exc}")
                    raise typer.Exit(code=1)

            # Step 2.3: Generating Feature Files
            def _on_feature_progress(event: str, prim_type: str, prim_name: str) -> None:
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
                    f"[green]✓ \\[Test Generation 3/6][/green] Feature Files generated! "
                    f"{result.files_generated} files written, {result.files_failed} failed. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                for warning in result.validation_warnings:
                    console.print(f"  [yellow]⚠ {warning}[/yellow]")
            except Exception as exc:
                console.print(f"[red]✗[/red] Feature Files generation failed: {exc}")
                raise typer.Exit(code=1)


            # Step 2.4: Validating and Formatting Feature Files
            with console.status(
                "[bold blue]    Validating and Formatting Feature Files[/bold blue]",
                spinner="line",
            ):
                try:
                    start_time = time.time()
                    result = orchestrator.validate_and_format_feature_files()
                    elapsed = format_elapsed_time(time.time() - start_time)
                    console.print(f"[green]✓ \\[Test Generation 4/6][/green] Feature Files validated and formatted! {len(result.get_unique_step_texts())} unique steps. [dim](Ran in {elapsed})[/dim]")
                except Exception as exc:
                    console.print(f"[red]✗[/red] Feature Files validation and formatting failed: {exc}")
                    raise typer.Exit(code=1)


            # Step 2.5: Generating Step Implementations
            with console.status(
                "[bold blue]    Generating Step Implementations[/bold blue]",
                spinner="line",
            ):
                try:
                    start_time = time.time()
                    result = asyncio.run(orchestrator.generate_step_implementations())
                    elapsed = format_elapsed_time(time.time() - start_time)
                    console.print(
                        f"[green]✓ \\[Test Generation 5/6][/green] Step Implementations generated! "
                        f"{result.steps_generated} steps generated, {result.steps_skipped} skipped. "
                        f"[dim](Ran in {elapsed})[/dim]"
                    )
                    if result.output_file:
                        console.print(f"  [dim]Output: {result.output_file}[/dim]")
                    for error in result.validation_errors:
                        console.print(f"  [yellow]⚠ {error}[/yellow]")
                except Exception as exc:
                    console.print(f"[red]✗[/red] Step Implementations generation failed: {exc}")
                    raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # Execution (always runs — either from fresh generation or pulled features)
    # ------------------------------------------------------------------
    orchestrator.validate_and_format_feature_files()
    feature_paths = sorted(
        (repo_root / "features").glob("*.feature")
    )
    total_features = len(feature_paths)

    console.print(
        f"\n[bold]Executing Behave tests for "
        f"{total_features} feature(s)...[/bold]"
    )

    for feat_idx, feature_path in enumerate(feature_paths, start=1):
        feature_name = feature_path.name
        feature = orchestrator.get_feature_by_path(feature_path)
        if feature is None:
            console.print(
                f"[yellow]⚠ Could not resolve feature model for "
                f"{feature_name}, skipping.[/yellow]"
            )
            continue

        console.print(
            f"\n[bold cyan]--- Feature {feat_idx}/{total_features}: "
            f"{feature_name} ---[/bold cyan]"
        )

        with console.status(
            f"[bold blue]    \\ Executing Tests[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                test_result = orchestrator.run_tests(
                    feature_file=feature_path,
                )
                elapsed = format_elapsed_time(time.time() - start_time)
                if test_result.success:
                    console.print(
                        f"[green]✓ \\[/green] All scenarios passed! "
                        f"{test_result.passed}/{test_result.total_scenarios} passed. "
                        f"[dim](Ran in {elapsed})[/dim]"
                    )
                else:
                    console.print(
                        f"[yellow]⚠ \\[/yellow] Tests executed with failures: "
                        f"{test_result.passed} passed, {test_result.failed} failed, "
                        f"{test_result.errored} errored, {test_result.skipped} skipped "
                        f"({test_result.total_scenarios} total). "
                        f"[dim](Ran in {elapsed})[/dim]"
                    )
                if test_result.output_file:
                    console.print(
                        f"  [dim]Results: {test_result.output_file}[/dim]"
                    )
            except Exception as exc:
                console.print(
                    f"[red]✗[/red] Test execution failed for "
                    f"{feature_name}: {exc}"
                )
                raise typer.Exit(code=1)

        if test_result.success:
            console.print(
                f"Test runner generated report successfully. "
            )

        if not test_result.raw_json:
            console.print(
                f"Test runner crashed (no JSON report). "
            )


    # Step 3: MCP Compliance Validation
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
        except Exception as exc:
            console.print(f"[red]✗[/red] Compliance validation failed: {exc}")

    # Step 4: Build and push report to service
    console.print("\n[bold]Building and pushing report to service...[/bold]")
    with console.status(
        "[bold blue]Assembling probe report...[/bold blue]",
        spinner="dots",
    ):
        try:
            start_time = time.time()
            report = asyncio.run(
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
        except Exception as exc:
            console.print(
                f"[yellow]⚠[/yellow] Failed to build/push report: {exc}"
            )

    # Step 5: Upload features to service for future reuse
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

    total_elapsed = format_elapsed_time(time.time() - pipeline_start_time)
    console.print(
        f"\n[bold green]Pipeline finished![/bold green] "
        f"[dim](Total: {total_elapsed})[/dim]"
    )
    console.print(f"[dim]Detailed logs: {log_file}[/dim]\n")


if __name__ == "__main__":
    app()

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

                # Build the base success message
                msg = (
                    f"[green]✓ \\[Test Generation 1/6][/green] Unit Test Planning complete! "
                    f"Planned {result.num_scenarios} scenarios. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                
                # Append debug info conditionally
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
                
                # Build the base success message
                msg = (
                    f"[green]✓ \\[Test Generation 2/6][/green] Integration Test Planning complete! "
                    f"Generated {result.num_scenarios} scenarios. "
                    f"[dim](Ran in {elapsed})[/dim]"
                )
                
                # Append debug info conditionally
                if debug:
                    scenario_plans_str = '\n'.join(str(val) for val in result.scenario_plans)
                    msg += f"\nScenario plans:\n{scenario_plans_str}"
                
                console.print(msg)
            except Exception as exc:
                console.print(f"[red]✗[/red] Integration Test Planning failed: {exc}")
                raise typer.Exit(code=1)

        # Step 2.3: Generating Feature Files
        with console.status(
            "[bold blue]    Generating Feature Files[/bold blue]",
            spinner="line",
        ):
            try:
                start_time = time.time()
                result = asyncio.run(orchestrator.generate_feature_files())
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

        # Step 2.6: Test Execution, Evaluation, and Healing Loop
        MAX_HEAL_ITERATIONS = 5
        iteration = 0
        test_result = None

        while iteration < MAX_HEAL_ITERATIONS:
            # --- Execute ---
            with console.status(
                f"[bold blue]    \\[Heal Loop {iteration + 1}/{MAX_HEAL_ITERATIONS}] Executing Tests[/bold blue]",
                spinner="line",
            ):
                try:
                    start_time = time.time()
                    test_result = orchestrator.run_tests()
                    elapsed = format_elapsed_time(time.time() - start_time)
                    if test_result.success:
                        console.print(
                            f"[green]✓ \\[Test Generation 6/6][/green] All tests passed! "
                            f"{test_result.passed}/{test_result.total_scenarios} passed. "
                            f"[dim](Ran in {elapsed})[/dim]"
                        )
                    else:
                        console.print(
                            f"[yellow]⚠ \\[Test Generation 6/6][/yellow] Tests executed with failures: "
                            f"{test_result.passed} passed, {test_result.failed} failed, "
                            f"{test_result.errored} errored, {test_result.skipped} skipped "
                            f"({test_result.total_scenarios} total). "
                            f"[dim](Ran in {elapsed})[/dim]"
                        )
                    if test_result.output_file:
                        console.print(f"  [dim]Results: {test_result.output_file}[/dim]")
                except Exception as exc:
                    console.print(f"[red]✗[/red] Test execution failed: {exc}")
                    raise typer.Exit(code=1)

            if test_result.success:
                break

            # --- Crash path: no JSON report produced ---
            if not test_result.raw_json:
                console.print(
                    f"[yellow]  \\[Heal Loop {iteration + 1}/{MAX_HEAL_ITERATIONS}] "
                    f"Test runner crashed (no JSON report). Attempting crash-heal...[/yellow]"
                )
                try:
                    start_time = time.time()
                    asyncio.run(orchestrator.heal_crash(test_result))
                    elapsed = format_elapsed_time(time.time() - start_time)
                    console.print(
                        f"[cyan]  \\[Crash-Heal][/cyan] "
                        f"Crash-heal applied. [dim](Ran in {elapsed})[/dim]"
                    )
                except Exception as exc:
                    console.print(f"[red]✗[/red] Crash-heal failed: {exc}")
                    raise typer.Exit(code=1)

                iteration += 1
                continue

            # --- Normal path: JSON report exists ---

            # Repopulate features (may have changed from prior healing)
            orchestrator.repopulate_features()

            # --- Evaluate ---
            with console.status(
                f"[bold blue]    \\[Heal Loop {iteration + 1}/{MAX_HEAL_ITERATIONS}] Evaluating Test Failures[/bold blue]",
                spinner="line",
            ):
                try:
                    start_time = time.time()
                    eval_result = asyncio.run(orchestrator.evaluate_tests(test_result))
                    elapsed = format_elapsed_time(time.time() - start_time)
                    console.print(
                        f"[cyan]  \\[Evaluation][/cyan] "
                        f"{len(eval_result.true_negatives)} SUT bugs (true negatives), "
                        f"{len(eval_result.false_negatives)} test bugs (false negatives). "
                        f"[dim](Ran in {elapsed})[/dim]"
                    )
                    for v in eval_result.true_negatives:
                        console.print(
                            f"    [yellow]SUT Bug:[/yellow] {v.step.text} — {v.failure_logs}"
                        )
                    for v in eval_result.false_negatives:
                        console.print(
                            f"    [blue]Test Bug:[/blue] {v.step.text} — {v.failure_logs}"
                        )
                except Exception as exc:
                    console.print(f"[red]✗[/red] Test evaluation failed: {exc}")
                    raise typer.Exit(code=1)

            if len(eval_result.false_negatives) == 0:
                console.print(
                    "[yellow]  Only SUT bugs remain (true negatives). "
                    "No further healing possible.[/yellow]"
                )
                break

            # --- Heal ---
            with console.status(
                f"[bold blue]    \\[Heal Loop {iteration + 1}/{MAX_HEAL_ITERATIONS}] Healing Test Implementation[/bold blue]",
                spinner="line",
            ):
                try:
                    start_time = time.time()
                    heal_result = asyncio.run(
                        orchestrator.heal_tests(test_result)
                    )
                    elapsed = format_elapsed_time(time.time() - start_time)
                except Exception as exc:
                    console.print(f"[red]✗[/red] Test healing failed: {exc}")
                    raise typer.Exit(code=1)

            iteration += 1
        else:
            console.print(
                f"[yellow]⚠ Max heal iterations ({MAX_HEAL_ITERATIONS}) reached. "
                f"Some test failures may remain.[/yellow]"
            )

    

    total_elapsed = format_elapsed_time(time.time() - pipeline_start_time)
    console.print(f"\n[bold green]✨ Pipeline finished successfully![/bold green] [dim](Total: {total_elapsed})[/dim]")
    console.print(f"[dim]Detailed logs: {log_file}[/dim]\n")


if __name__ == "__main__":
    app()

"""Command-line interface for MCP-Probe-Pilot.

This module provides the CLI entry point for the MCP testing framework,
supporting test generation, execution, and reporting commands.

Usage:
    mcp-probe init          Create configuration file template
    mcp-probe generate      Generate test cases from server discovery
    mcp-probe run           Execute generated tests
    mcp-probe report        Generate HTML test report
    mcp-probe full          Run complete test pipeline
"""

import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Optional
import os
import zipfile
import tempfile

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .config import (
    LLMConfig,
    MCPProbeConfig,
    create_default_config,
    load_config,
    save_config,
)
from .discovery import ASTIndexer, ASTIndexerError, MCPDiscoveryClient, MCPDiscoveryError
from .generators import (
    GeneratorError,
    IntegrationTestGenerator,
    UnitTestGenerator,
    create_llm_client,
)
from .service_client import (
    MCPProbeServiceClient,
    ServiceAPIError,
    ServiceClientError,
    ServiceConnectionError,
)

# Initialize Typer app
app = typer.Typer(
    name="mcp-probe",
    help="Automated testing framework for MCP server validation",
    add_completion=False,
)

# Rich console for formatted output
console = Console()

# Default config filename
DEFAULT_CONFIG_FILENAME = "mcp-probe-service-properties.json"


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with Rich handler.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def get_config_path(config: Optional[Path], mcp_source_code: Optional[Path] = None) -> Path:
    """Get the configuration file path.

    Args:
        config: Optional path provided by user.
        mcp_source_code: Optional path to source code directory.

    Returns:
        Path to the configuration file.
    """
    if config is not None:
        return config

    if mcp_source_code is not None:
        return mcp_source_code / DEFAULT_CONFIG_FILENAME

    env_source_path = os.environ.get("MCP_SOURCE_CODE_PATH")
    if env_source_path:
        return Path(env_source_path) / DEFAULT_CONFIG_FILENAME

    return Path.cwd() / DEFAULT_CONFIG_FILENAME


def load_config_with_error_handling(
    config_path: Path, mcp_source_code: Optional[Path] = None
) -> MCPProbeConfig:
    """Load configuration with user-friendly error handling.

    Args:
        config_path: Path to the configuration file.
        mcp_source_code: Optional path to override the source code directory.

    Returns:
        Loaded configuration.

    Raises:
        typer.Exit: On configuration loading failure.
    """
    try:
        probe_config = load_config(config_path)

        if mcp_source_code:
            probe_config.mcp_source_code_path = str(mcp_source_code.absolute())
            if (
                probe_config.server_command.startswith("uv")
                and "--directory" not in probe_config.server_command
            ):
                parts = probe_config.server_command.split(None, 1)
                if len(parts) > 1:
                    probe_config.server_command = (
                        f"uv --directory {probe_config.mcp_source_code_path} {parts[1]}"
                    )
                else:
                    probe_config.server_command = (
                        f"uv --directory {probe_config.mcp_source_code_path}"
                    )

        return probe_config
    except FileNotFoundError:
        console.print(
            f"[red]Error:[/red] Configuration file not found: {config_path}",
            style="bold",
        )
        if mcp_source_code:
            console.print(
                f"\n[yellow]Hint:[/yellow] Make sure [cyan]{DEFAULT_CONFIG_FILENAME}[/cyan] "
                f"exists in your source directory."
            )
        console.print(
            "\nRun [cyan]mcp-probe init[/cyan] to create a configuration file."
        )
        raise typer.Exit(code=1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] Invalid configuration: {e}", style="bold")
        raise typer.Exit(code=1)


def print_discovery_summary(discovery_result) -> None:
    """Print a summary table of discovered capabilities.

    Args:
        discovery_result: The discovery result to summarize.
    """
    table = Table(title="Discovered MCP Capabilities")
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="green", justify="right")
    table.add_column("Names", style="dim")

    tool_names = ", ".join(t.name for t in discovery_result.tools[:5])
    if len(discovery_result.tools) > 5:
        tool_names += f" (+{len(discovery_result.tools) - 5} more)"
    table.add_row("Tools", str(len(discovery_result.tools)), tool_names)

    resource_names = ", ".join(r.name or r.uri for r in discovery_result.resources[:5])
    if len(discovery_result.resources) > 5:
        resource_names += f" (+{len(discovery_result.resources) - 5} more)"
    table.add_row("Resources", str(len(discovery_result.resources)), resource_names)

    prompt_names = ", ".join(p.name for p in discovery_result.prompts[:5])
    if len(discovery_result.prompts) > 5:
        prompt_names += f" (+{len(discovery_result.prompts) - 5} more)"
    table.add_row("Prompts", str(len(discovery_result.prompts)), prompt_names)

    console.print(table)


# =============================================================================
# CLI Commands
# =============================================================================


@app.command()
def init(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to save the configuration file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Create a new mcp-probe-service-properties.json configuration file.

    Interactively prompts for required configuration values and creates
    a new configuration file in the current directory or specified path.
    """
    setup_logging(verbose)

    config_path = get_config_path(config)

    if config_path.exists():
        overwrite = Confirm.ask(
            f"[yellow]Configuration file already exists at {config_path}.[/yellow]\n"
            "Do you want to overwrite it?"
        )
        if not overwrite:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(code=0)

    console.print(
        Panel(
            "[bold cyan]MCP-Probe Configuration Setup[/bold cyan]\n\n"
            "This will create a configuration file for testing your MCP server.",
            expand=False,
        )
    )

    project_code = Prompt.ask(
        "\n[cyan]Project code[/cyan] (unique identifier for your MCP server)",
        default="my-mcp-server",
    )

    server_command = Prompt.ask(
        "[cyan]Server command[/cyan] (command to start your MCP server)",
        default="python -m my_server",
    )

    console.print("\n[dim]Available LLM providers: openai, anthropic, gemini[/dim]")
    llm_provider = Prompt.ask(
        "[cyan]LLM provider[/cyan]",
        choices=["openai", "anthropic", "gemini"],
        default="gemini",
    )

    try:
        probe_config = create_default_config(
            project_code=project_code,
            server_command=server_command,
            llm_provider=llm_provider,
        )

        saved_path = save_config(probe_config, config_path)

        console.print(
            f"\n[green]✓[/green] Configuration saved to [cyan]{saved_path}[/cyan]"
        )
        console.print(
            "\n[dim]Next steps:[/dim]\n"
            f"  1. Set your API key: export {llm_provider.upper()}_API_KEY=your-key\n"
            "  2. Run: [cyan]mcp-probe generate[/cyan] to generate tests\n"
            "  3. Run: [cyan]mcp-probe run[/cyan] to execute tests"
        )

    except ValueError as e:
        console.print(f"[red]Error:[/red] Invalid configuration: {e}")
        raise typer.Exit(code=1)


@app.command()
def generate(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
    mcp_source_code: Optional[Path] = typer.Option(
        None,
        "--mcp-source-code",
        help="Absolute path to the server source code directory",
    ),
) -> None:
    """Generate test cases from MCP server discovery.

    Connects to the MCP server specified in the configuration,
    discovers available tools, resources, and prompts, indexes
    the source code via AST, then generates BDD Gherkin test
    scenarios using LLM-powered analysis with ChromaDB context.
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    config_path = get_config_path(config, mcp_source_code)
    probe_config = load_config_with_error_handling(config_path, mcp_source_code)

    console.print(
        Panel(
            f"[bold cyan]MCP-Probe Test Generation[/bold cyan]\n\n"
            f"Project: [green]{probe_config.project_code}[/green]\n"
            f"Server: [dim]{probe_config.server_command}[/dim]",
            expand=False,
        )
    )

    asyncio.run(_run_generation(probe_config, logger))


async def _run_generation(probe_config: MCPProbeConfig, logger: logging.Logger) -> None:
    """Run the test generation pipeline.

    Args:
        probe_config: The loaded configuration.
        logger: Logger instance.
    """
    # Step 0: Connect to mcp-probe-service
    console.print("\n[bold]Stage 0: Connecting to mcp-probe-service[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking service connection...", total=None)

        try:
            async with MCPProbeServiceClient(probe_config.service_url) as service_client:
                await service_client.health_check()
                progress.update(task, description="Service connected!")

                await service_client.ensure_project_exists(
                    project_code=probe_config.project_code,
                    name=probe_config.project_code,
                    server_command=probe_config.server_command,
                )

                await _run_generation_with_service(
                    probe_config, service_client, logger
                )

        except ServiceConnectionError as e:
            console.print(f"\n[red]Error:[/red] {e}")
            console.print(
                f"\n[yellow]Hint:[/yellow] Make sure mcp-probe-service is running at "
                f"[cyan]{probe_config.service_url}[/cyan]"
            )
            console.print(
                "  Start it with: [cyan]cd mcp-probe-service && docker-compose up -d[/cyan]"
            )
            raise typer.Exit(code=1)
        except ServiceAPIError as e:
            console.print(f"\n[red]Error:[/red] Service API error: {e.detail}")
            raise typer.Exit(code=1)


async def _run_generation_with_service(
    probe_config: MCPProbeConfig,
    service_client: MCPProbeServiceClient,
    logger: logging.Logger,
) -> None:
    """Run generation pipeline with service client context.

    Args:
        probe_config: The loaded configuration.
        service_client: Connected service client.
        logger: Logger instance.
    """
    console.print("[green]✓[/green] Connected to mcp-probe-service")

    # Step 1: MCP Discovery
    console.print("\n[bold]Stage 1: Server Discovery[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting to MCP server...", total=None)

        try:
            async with MCPDiscoveryClient(probe_config.server_command) as client:
                progress.update(task, description="Discovering capabilities...")
                discovery_result = await client.discover_all()

        except MCPDiscoveryError as e:
            console.print(f"\n[red]Error:[/red] Failed to connect to server: {e}")
            raise typer.Exit(code=1)

    print_discovery_summary(discovery_result)

    if discovery_result.tool_count == 0 and discovery_result.resource_count == 0:
        console.print(
            "\n[yellow]Warning:[/yellow] No tools or resources discovered. "
            "Check that your server is running correctly."
        )
        raise typer.Exit(code=1)

    # Step 2: AST Codebase Indexing
    console.print("\n[bold]Stage 2: AST Codebase Indexing[/bold]")

    source_path = None
    if probe_config.mcp_source_code_path:
        source_path = Path(probe_config.mcp_source_code_path)

    if source_path and source_path.is_dir():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Indexing source code with AST parser...", total=None)

            try:
                indexer = ASTIndexer()
                codebase_index = indexer.index_directory(source_path)
                progress.update(
                    task,
                    description=(
                        f"Indexed {codebase_index.total_entities} entities "
                        f"from {codebase_index.total_files} files"
                    ),
                )
            except ASTIndexerError as e:
                console.print(f"\n[red]Error:[/red] AST indexing failed: {e}")
                console.print("[dim]Continuing without code context...[/dim]")
                codebase_index = None

        if codebase_index and codebase_index.total_entities > 0:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Sending code entities to ChromaDB...", total=None)
                try:
                    result = await indexer.index_to_chromadb(
                        service_client=service_client,
                        project_code=probe_config.project_code,
                        index=codebase_index,
                    )
                    indexed_count = result.get("indexed", codebase_index.total_entities)
                    progress.update(
                        task,
                        description=f"Indexed {indexed_count} entities in ChromaDB",
                    )
                    console.print(
                        f"[green]✓[/green] Codebase indexed: {indexed_count} entities "
                        f"from {codebase_index.total_files} files"
                    )
                except Exception as e:
                    console.print(
                        f"\n[yellow]Warning:[/yellow] ChromaDB indexing failed: {e}"
                    )
                    console.print("[dim]Continuing without indexed code context...[/dim]")
        else:
            console.print("[dim]No code entities found to index.[/dim]")
    else:
        console.print(
            "[yellow]⚠ No source code path configured.[/yellow]"
        )
        console.print(
            "[dim]Provide --mcp-source-code or set mcp_source_code_path in config "
            "for AST-based code context in test generation.[/dim]"
        )

    # Step 3: Gherkin Test Generation
    console.print("\n[bold]Stage 3: Gherkin Test Generation[/bold]")

    llm_config = probe_config.get_generator_llm_config()
    llm_client = create_llm_client(llm_config)

    unit_generator = UnitTestGenerator(
        llm_client=llm_client,
        service_client=service_client,
        project_code=probe_config.project_code,
    )
    integration_generator = IntegrationTestGenerator(
        llm_client=llm_client,
        service_client=service_client,
        project_code=probe_config.project_code,
    )

    # Generate unit tests
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating unit test feature files...", total=None)

        try:
            unit_result = await unit_generator.generate_all(discovery_result)
            progress.update(
                task,
                description=(
                    f"Generated {unit_result.total_feature_files} unit feature files "
                    f"({unit_result.total_scenarios} scenarios)"
                ),
            )
        except GeneratorError as e:
            console.print(f"\n[red]Error:[/red] Unit test generation failed: {e}")
            unit_result = None

    if unit_result:
        console.print(
            f"[green]✓[/green] Unit tests: {unit_result.total_feature_files} feature files, "
            f"{unit_result.total_scenarios} scenarios "
            f"({unit_result.tools_covered} tools, {unit_result.resources_covered} resources, "
            f"{unit_result.prompts_covered} prompts)"
        )
        if unit_result.has_errors:
            for error in unit_result.errors:
                console.print(f"  [yellow]⚠[/yellow] {error}")

    # Generate integration tests
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Generating integration test feature file...", total=None
        )

        try:
            integration_result = await integration_generator.generate_all(discovery_result)
            progress.update(
                task,
                description=(
                    f"Generated {integration_result.total_scenarios} integration scenarios "
                    f"({integration_result.workflows_identified} workflows)"
                ),
            )
        except GeneratorError as e:
            console.print(f"\n[red]Error:[/red] Integration test generation failed: {e}")
            integration_result = None

    if integration_result and integration_result.total_feature_files > 0:
        console.print(
            f"[green]✓[/green] Integration tests: "
            f"{integration_result.total_scenarios} scenarios "
            f"({integration_result.workflows_identified} workflows identified)"
        )
        if integration_result.has_errors:
            for error in integration_result.errors:
                console.print(f"  [yellow]⚠[/yellow] {error}")
    elif integration_result:
        console.print(
            "[dim]No integration workflow patterns identified.[/dim]"
        )

    # Collect all feature files and save/store
    all_features = []
    if unit_result:
        all_features.extend(unit_result.feature_files)
    if integration_result:
        all_features.extend(integration_result.feature_files)

    if all_features:
        # Save feature files locally
        output_dir = probe_config.get_output_path() / "features"
        output_dir.mkdir(parents=True, exist_ok=True)

        for feature in all_features:
            feature_path = output_dir / feature.filename
            feature_path.write_text(feature.content)

        console.print(
            f"\n[green]✓[/green] Saved {len(all_features)} feature files to "
            f"[cyan]{output_dir}[/cyan]"
        )

        # Store scenario set metadata in service
        total_scenarios = sum(f.scenario_count for f in all_features)
        scenario_set = {
            "unit_features": [
                f.model_dump() for f in all_features if f.target_type != "integration"
            ],
            "integration_feature": next(
                (f.model_dump() for f in all_features if f.target_type == "integration"),
                None,
            ),
            "total_scenarios": total_scenarios,
            "feature_file_count": len(all_features),
        }
        tc_version = None
        try:
            tc_response = await service_client.store_scenario_set(
                project_code=probe_config.project_code,
                scenario_set=scenario_set,
            )
            tc_version = tc_response.version
            console.print(
                f"[green]✓[/green] Stored scenario set v{tc_version} "
                f"in mcp-probe-service"
            )
        except ServiceClientError as e:
            console.print(
                f"[yellow]Warning:[/yellow] Failed to store scenario set in service: {e}"
            )

        # Upload feature files as artifacts to the service for persistence
        if tc_version is not None:
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    zip_path = Path(tmpdir) / "artifacts.zip"
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for feature in all_features:
                            zf.writestr(
                                f"features/{feature.filename}",
                                feature.content,
                            )

                    await service_client.store_test_artifacts(
                        project_code=probe_config.project_code,
                        version=tc_version,
                        artifacts_path=zip_path,
                    )

                console.print(
                    f"[green]✓[/green] Uploaded {len(all_features)} feature files "
                    f"as artifacts to mcp-probe-service"
                )
            except Exception as e:
                console.print(
                    f"[yellow]Warning:[/yellow] Failed to upload artifacts "
                    f"to service: {e}"
                )
    else:
        console.print(
            "\n[yellow]⚠ No feature files were generated.[/yellow]"
        )


@app.command()
def run(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
    mcp_source_code: Optional[Path] = typer.Option(
        None,
        "--mcp-source-code",
        help="Absolute path to the server source code directory",
    ),
) -> None:
    """Execute generated tests against the MCP server.

    Loads previously generated test cases and executes them
    using the BDD Behave test runner with compliance validation.

    Note: This command requires the Test Runner module which is
    not yet implemented.
    """
    setup_logging(verbose)

    config_path = get_config_path(config, mcp_source_code)
    probe_config = load_config_with_error_handling(config_path, mcp_source_code)

    console.print(
        Panel(
            f"[bold cyan]MCP-Probe Test Execution[/bold cyan]\n\n"
            f"Project: [green]{probe_config.project_code}[/green]",
            expand=False,
        )
    )

    console.print("\n[yellow]⚠ Test Runner Not Implemented[/yellow]")
    console.print(
        Panel(
            "The Test Runner module (Task 11.0) has not been implemented yet.\n\n"
            "This command will execute BDD Behave tests once the following\n"
            "components are completed:\n"
            "  - runner/executor.py - BDD Behave test executor\n"
            "  - runner/server_manager.py - MCP server lifecycle management\n"
            "  - compliance/middleware.py - Protocol validation interceptor\n"
            "  - oracle/evaluator.py - Semantic assertion evaluator",
            title="Not Implemented",
            border_style="yellow",
        )
    )

    raise typer.Exit(code=1)


@app.command()
def report(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
    mcp_source_code: Optional[Path] = typer.Option(
        None,
        "--mcp-source-code",
        help="Absolute path to the server source code directory",
    ),
) -> None:
    """Generate HTML test report from execution results.

    Creates a detailed HTML report with test results, compliance
    validation outcomes, and failure classification.

    Note: This command requires the Report Generator module which
    is not yet implemented.
    """
    setup_logging(verbose)

    config_path = get_config_path(config, mcp_source_code)
    probe_config = load_config_with_error_handling(config_path, mcp_source_code)

    console.print(
        Panel(
            f"[bold cyan]MCP-Probe Report Generation[/bold cyan]\n\n"
            f"Project: [green]{probe_config.project_code}[/green]",
            expand=False,
        )
    )

    output_dir = probe_config.get_output_path()

    console.print("\n[yellow]⚠ Report Generator Not Implemented[/yellow]")
    console.print(
        Panel(
            "The Report Generator module (Task 14.0) has not been implemented yet.\n\n"
            "This command will generate HTML reports once the following\n"
            "components are completed:\n"
            "  - reporting/generator.py - HTML report generator\n"
            "  - reporting/templates/ - HTML report templates\n"
            "  - results/classifier.py - Failure classification logic\n\n"
            f"Reports will be saved to: {output_dir / 'report.html'}",
            title="Not Implemented",
            border_style="yellow",
        )
    )

    raise typer.Exit(code=1)


@app.command()
def full(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
    mcp_source_code: Optional[Path] = typer.Option(
        None,
        "--mcp-source-code",
        help="Absolute path to the server source code directory",
    ),
) -> None:
    """Run the complete test pipeline: generate -> run -> report.

    This command orchestrates the full testing workflow:
    1. Generate test cases from server discovery + AST indexing
    2. Execute tests against the MCP server
    3. Generate HTML report

    Note: Currently only the discovery step is fully implemented.
    AST indexing, generation, run, and report steps require further
    implementation.
    """
    setup_logging(verbose)

    config_path = get_config_path(config, mcp_source_code)
    probe_config = load_config_with_error_handling(config_path, mcp_source_code)

    console.print(
        Panel(
            f"[bold cyan]MCP-Probe Full Pipeline[/bold cyan]\n\n"
            f"Project: [green]{probe_config.project_code}[/green]\n"
            f"Server: [dim]{probe_config.server_command}[/dim]",
            expand=False,
        )
    )

    # Phase 1: Generate
    console.print("\n[bold blue]═══ Phase 1: Test Generation ═══[/bold blue]\n")

    try:
        asyncio.run(_run_generation(probe_config, logging.getLogger(__name__)))
    except SystemExit as e:
        if e.code != 0:
            console.print("\n[red]Pipeline aborted due to generation failure.[/red]")
            raise

    # Phase 2: Run (placeholder)
    console.print("\n[bold blue]═══ Phase 2: Test Execution ═══[/bold blue]\n")
    console.print(
        "[yellow]⚠ Skipping test execution - Test Runner not implemented.[/yellow]"
    )
    console.print(
        "[dim]This phase requires the Test Runner module (Task 11.0).[/dim]\n"
    )

    # Phase 3: Report (placeholder)
    console.print("[bold blue]═══ Phase 3: Report Generation ═══[/bold blue]\n")
    console.print(
        "[yellow]⚠ Skipping report generation - Report Generator not implemented.[/yellow]"
    )
    console.print(
        "[dim]This phase requires the Report Generator module (Task 14.0).[/dim]\n"
    )

    # Summary
    console.print(
        Panel(
            "[green]✓[/green] Discovery completed successfully.\n"
            "[green]✓[/green] AST indexing + Gherkin generation completed.\n"
            "[yellow]⚠[/yellow] Test execution skipped (not implemented).\n"
            "[yellow]⚠[/yellow] Report generation skipped (not implemented).\n\n"
            "[dim]Once Test Runner (Task 11.0) and Report Generator (Task 14.0)\n"
            "are implemented, the full pipeline will execute all phases.[/dim]",
            title="Pipeline Summary",
            border_style="cyan",
        )
    )


@app.command()
def version() -> None:
    """Display the version information."""
    from . import __version__

    console.print(f"mcp-probe version [cyan]{__version__}[/cyan]")


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    app()

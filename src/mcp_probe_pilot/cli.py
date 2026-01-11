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
from .discovery import MCPDiscoveryClient, MCPDiscoveryError
from .generators import (
    ClientTestGenerator,
    GeneratorError,
    ScenarioSet,
    TestImplementor,
    TestImplementorError,
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


class NotImplementedModuleError(Exception):
    """Raised when attempting to use a module that hasn't been implemented yet."""

    pass


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

    # Priority 2: Environment variable
    env_source_path = os.environ.get("MCP_SOURCE_CODE_PATH")
    if env_source_path:
        return Path(env_source_path) / DEFAULT_CONFIG_FILENAME

    return Path.cwd() / DEFAULT_CONFIG_FILENAME


def load_config_with_error_handling(config_path: Path, mcp_source_code: Optional[Path] = None) -> MCPProbeConfig:
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
        
        # If flag was provided, it should override anything from env or file
        if mcp_source_code:
            probe_config.mcp_source_code_path = str(mcp_source_code.absolute())
            # Re-apply auto-injection if path changed manually
            if probe_config.server_command.startswith("uv") and "--directory" not in probe_config.server_command:
                parts = probe_config.server_command.split(None, 1)
                if len(parts) > 1:
                    probe_config.server_command = f"uv --directory {probe_config.mcp_source_code_path} {parts[1]}"
                else:
                    probe_config.server_command = f"uv --directory {probe_config.mcp_source_code_path}"
        
        return probe_config
    except FileNotFoundError:
        console.print(
            f"[red]Error:[/red] Configuration file not found: {config_path}",
            style="bold",
        )
        if mcp_source_code:
             console.print(
                f"\n[yellow]Hint:[/yellow] Make sure [cyan]{DEFAULT_CONFIG_FILENAME}[/cyan] exists in your source directory."
            )
        console.print(
            "\nRun [cyan]mcp-probe init[/cyan] to create a configuration file."
        )
        raise typer.Exit(code=1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] Invalid configuration: {e}", style="bold")
        raise typer.Exit(code=1)


def save_scenario_set_local(scenario_set: ScenarioSet, output_dir: Path) -> None:
    """Save generated scenarios to the local output directory (for debugging).

    Args:
        scenario_set: The generated scenarios to save.
        output_dir: Directory to save files to.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save complete scenario set as JSON for debugging/backup
    scenario_set_file = output_dir / "scenario_set.json"
    with open(scenario_set_file, "w") as f:
        json.dump(scenario_set.model_dump(), f, indent=2)


async def store_scenario_set_in_service(
    service_client: MCPProbeServiceClient,
    project_code: str,
    scenario_set: ScenarioSet,
) -> int:
    """Store scenario set in mcp-probe-service.

    Args:
        service_client: The service client.
        project_code: Project code.
        scenario_set: The generated scenarios.

    Returns:
        The version number of the stored test cases.
    """
    response = await service_client.store_scenario_set(
        project_code=project_code,
        scenario_set=scenario_set.model_dump(),
    )
    return response.version


def print_discovery_summary(discovery_result) -> None:
    """Print a summary table of discovered capabilities.

    Args:
        discovery_result: The discovery result to summarize.
    """
    table = Table(title="Discovered MCP Capabilities")
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="green", justify="right")
    table.add_column("Names", style="dim")

    # Tools
    tool_names = ", ".join(t.name for t in discovery_result.tools[:5])
    if len(discovery_result.tools) > 5:
        tool_names += f" (+{len(discovery_result.tools) - 5} more)"
    table.add_row("Tools", str(len(discovery_result.tools)), tool_names)

    # Resources
    resource_names = ", ".join(r.name or r.uri for r in discovery_result.resources[:5])
    if len(discovery_result.resources) > 5:
        resource_names += f" (+{len(discovery_result.resources) - 5} more)"
    table.add_row("Resources", str(len(discovery_result.resources)), resource_names)

    # Prompts
    prompt_names = ", ".join(p.name for p in discovery_result.prompts[:5])
    if len(discovery_result.prompts) > 5:
        prompt_names += f" (+{len(discovery_result.prompts) - 5} more)"
    table.add_row("Prompts", str(len(discovery_result.prompts)), prompt_names)

    console.print(table)


def print_generation_summary(scenario_set: ScenarioSet) -> None:
    """Print a summary of generated test scenarios.

    Args:
        scenario_set: The generated scenario set.
    """
    table = Table(title="Generated Test Scenarios")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")

    table.add_row("Ground Truths", str(len(scenario_set.ground_truths)))
    table.add_row("Feature Files", str(len(scenario_set.features)))
    table.add_row("Scenarios", str(len(scenario_set.scenarios)))
    table.add_row("Workflow Ground Truths", str(len(scenario_set.workflow_ground_truths)))
    table.add_row("Workflow Scenarios", str(len(scenario_set.workflow_scenarios)))
    table.add_row("Total Scenarios", str(scenario_set.total_scenarios))

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

    # Check if config already exists
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

    # Prompt for required values
    project_code = Prompt.ask(
        "\n[cyan]Project code[/cyan] (unique identifier for your MCP server)",
        default="my-mcp-server",
    )

    server_command = Prompt.ask(
        "[cyan]Server command[/cyan] (command to start your MCP server)",
        default="python -m my_server",
    )

    # Prompt for LLM provider
    console.print("\n[dim]Available LLM providers: openai, anthropic, gemini[/dim]")
    llm_provider = Prompt.ask(
        "[cyan]LLM provider[/cyan]",
        choices=["openai", "anthropic", "gemini"],
        default="gemini",
    )

    # Create configuration
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
    discovers available tools, resources, and prompts, then
    generates BDD test scenarios using LLM-powered analysis.
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

    # Run the async generation pipeline
    asyncio.run(_run_generation(probe_config, logger))


async def _run_generation(probe_config: MCPProbeConfig, logger: logging.Logger) -> None:
    """Run the test generation pipeline.

    Args:
        probe_config: The loaded configuration.
        logger: Logger instance.
    """
    output_dir = probe_config.get_output_path()

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
                # Check service health
                await service_client.health_check()
                progress.update(task, description="Service connected!")

                # Ensure project exists
                # progress.update(task, description="Ensuring project exists...") # silenced
                await service_client.ensure_project_exists(
                    project_code=probe_config.project_code,
                    name=probe_config.project_code,
                    server_command=probe_config.server_command,
                )

                # Continue with the rest of the pipeline within the service client context
                await _run_generation_with_service(
                    probe_config, service_client, output_dir, logger
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
    output_dir: Path,
    logger: logging.Logger,
) -> None:
    """Run generation pipeline with service client context.

    Args:
        probe_config: The loaded configuration.
        service_client: Connected service client.
        output_dir: Output directory for generated tests.
        logger: Logger instance.
    """
    console.print("[green]✓[/green] Connected to mcp-probe-service")

    # Step 1: Discovery
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

    # Step 2: Test Generation
    console.print("\n[bold]Stage 2: Test Generation[/bold]")

    llm_config = probe_config.get_generator_llm_config()
    generator = ClientTestGenerator(llm_config)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating ground truth...", total=None)

        try:
            # Check if tests exist and if we should skip generation
            existing_tests = None
            if not probe_config.regenerate_tests:
                progress.update(task, description="Checking for existing tests...")
                existing_tests = await service_client.get_scenario_set(probe_config.project_code)
            
            if existing_tests:
                console.print("\n[yellow]Tests already exist for this project. Skipping generation.[/yellow]")
                console.print("[dim]Use 'regenerate_tests': true in config to force regeneration.[/dim]")
                
                # We need a ScenarioSet object for the next steps, so reconstruct it from stored data
                # Note: This might be incomplete depending on what's stored vs what ScenarioSet expects,
                # but getting the scenario set from service usually returns the JSON dump.
                # For now, we'll try to validate it into the model.
                try:
                    scenario_set = ScenarioSet(**existing_tests)
                    console.print(f"[green]✓[/green] Loaded existing tests (version {existing_tests.get('version', 'unknown')})")
                except Exception as e:
                    console.print(f"[red]Warning:[/red] Failed to parse existing tests: {e}")
                    console.print("Proceeding with regeneration...")
                    existing_tests = None

            if not existing_tests:
                progress.update(task, description="Generating test scenarios...")
                scenario_set = await generator.generate_scenarios(
                    discovery_result,
                    max_test_cases=probe_config.max_test_cases,
                    max_ground_truths=probe_config.max_ground_truths,
                )

        except GeneratorError as e:
            console.print(f"\n[red]Error:[/red] Test generation failed: {e}")
            raise typer.Exit(code=1)

    print_generation_summary(scenario_set)

    # Step 3: Store in mcp-probe-service
    console.print("\n[bold]Stage 3: Storing Tests in Service[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Storing scenarios in service...", total=None)

        try:
            # Only store if we generated new tests (not existing ones)
            if not existing_tests:
                version = await store_scenario_set_in_service(
                    service_client,
                    probe_config.project_code,
                    scenario_set,
                )
                progress.update(task, description=f"Stored as version {version}")
            else:
                 # If we loaded existing tests, we don't need to store, 
                 # but we might want the version for display
                 version = existing_tests.get('version', 'existing')
                 progress.update(task, description=f"Using existing version {version}")

        except ServiceAPIError as e:
            console.print(f"\n[red]Error:[/red] Failed to store tests: {e.detail}")
            raise typer.Exit(code=1)

    console.print(
        f"[green]✓[/green] Tests stored in service (version {version})"
    )

    # Step 4: Generate executable Behave tests
    console.print("\n[bold]Stage 4: Generating Executable Tests[/bold]")

    implementor = TestImplementor(llm_config)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating feature files...", total=None)

        try:
            progress.update(task, description="Generating step definitions (LLM)...")
            implementation = await implementor.implement_tests(
                scenario_set=scenario_set,
                output_dir=output_dir,
                project_code=probe_config.project_code,
                service_url=probe_config.service_url,
                server_command=probe_config.server_command,
            )

        except TestImplementorError as e:
            console.print(f"\n[red]Error:[/red] Test implementation failed: {e}")
            raise typer.Exit(code=1)

    # Also save local backup
    save_scenario_set_local(scenario_set, output_dir)
    
    # NEW: Zip and store artifacts in service
    if not existing_tests: # version is defined
        # with Progress(
        #     SpinnerColumn(),
        #     TextColumn("[progress.description]{task.description}"),
        #     console=console,
        # ) as progress:
        #     task = progress.add_task("Uploading artifacts to service...", total=None)
            
        #     try:
        #         # Create zip archive
        #         zip_base_name = output_dir / "artifacts"
        #         zip_path_str = shutil.make_archive(str(zip_base_name), 'zip', output_dir)
        #         zip_path = Path(zip_path_str)
                
        #         # Upload
        #         await service_client.store_test_artifacts(
        #             project_code=probe_config.project_code,
        #             version=version,
        #             artifacts_path=zip_path
        #         )
                
        #         # Cleanup zip
        #         if zip_path.exists():
        #             zip_path.unlink()
                    
        #         progress.update(task, description="Artifacts uploaded successfully")
        #         console.print(f"[green]✓[/green] Artifacts stored in service")
                
        #     except Exception as e:
        #         console.print(f"\n[red]Warning:[/red] Failed to upload artifacts: {e}")
        #         # Don't fail the whole process just for upload failure
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Uploading artifacts to service...", total=None)
            
            # Create a temporary directory to hold the zip file
            # This prevents the "zipping the zip file" corruption issue
            with tempfile.TemporaryDirectory() as temp_dir:
                try:
                    progress.update(task, description="Creating zip archive...")
                    
                    # Create zip OUTSIDE the output_dir
                    zip_base_name = Path(temp_dir) / "artifacts"
                    
                    # Run strictly synchronous to ensure flush
                    zip_path_str = shutil.make_archive(
                        str(zip_base_name), 
                        'zip', 
                        root_dir=output_dir
                    )
                    zip_path = Path(zip_path_str)
                    
                    # --- SANITY CHECK ---
                    # Verify the zip is valid locally before sending
                    if not zipfile.is_zipfile(zip_path):
                        raise ValueError("Generated zip is invalid (header check)")
                        
                    with zipfile.ZipFile(zip_path, 'r') as z:
                        bad_file = z.testzip()
                        if bad_file:
                             raise ValueError(f"Generated zip has corrupt file: {bad_file}")
                    # --------------------

                    progress.update(task, description="Uploading to service...")
                    
                    # Upload (Client reads into memory -> sends)
                    await service_client.store_test_artifacts(
                        project_code=probe_config.project_code,
                        version=version,
                        artifacts_path=zip_path
                    )
                    
                    progress.update(task, description="Artifacts uploaded successfully")
                    console.print(f"[green]✓[/green] Artifacts stored in service")
                    
                except Exception as e:
                    console.print(f"\n[red]Warning:[/red] Failed to upload artifacts: {e}")
                    # Don't fail the whole process just for upload failure

    console.print(f"\n[green]✓[/green] Tests generated to [cyan]{output_dir}[/cyan]")
    console.print(
        f"  - Feature files: {len(implementation.feature_files)} files\n"
        f"  - Step definitions: {implementation.step_definitions_file}\n"
        f"  - Environment: {implementation.environment_file}\n"
        f"  - Ground truth client: {implementation.ground_truth_client_file}"
    )

    # Note about fuzzing (not yet implemented)
    console.print(
        "\n[dim]Note: Fuzzing module not yet implemented. "
        "Fuzz scenarios will be added in a future version.[/dim]"
    )

    console.print(
        "\n[dim]Next step:[/dim] Run [cyan]mcp-probe run[/cyan] to execute tests"
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

    output_dir = probe_config.get_output_path()
    scenario_set_file = output_dir / "scenario_set.json"

    # Check if tests have been generated
    if not scenario_set_file.exists():
        console.print(
            f"[red]Error:[/red] No generated tests found at {output_dir}",
            style="bold",
        )
        console.print(
            "\nRun [cyan]mcp-probe generate[/cyan] first to generate tests."
        )
        raise typer.Exit(code=1)

    # Placeholder for Test Runner (not yet implemented)
    console.print("\n[yellow]⚠ Test Runner Not Implemented[/yellow]")
    console.print(
        Panel(
            "The Test Runner module (Task 11.0) has not been implemented yet.\n\n"
            "This command will execute BDD Behave tests once the following\n"
            "components are completed:\n"
            "  • runner/executor.py - BDD Behave test executor\n"
            "  • runner/server_manager.py - MCP server lifecycle management\n"
            "  • compliance/middleware.py - Protocol validation interceptor\n"
            "  • oracle/evaluator.py - Semantic assertion evaluator",
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

    # Placeholder for Report Generator (not yet implemented)
    console.print("\n[yellow]⚠ Report Generator Not Implemented[/yellow]")
    console.print(
        Panel(
            "The Report Generator module (Task 14.0) has not been implemented yet.\n\n"
            "This command will generate HTML reports once the following\n"
            "components are completed:\n"
            "  • reporting/generator.py - HTML report generator\n"
            "  • reporting/templates/ - HTML report templates\n"
            "  • results/classifier.py - Failure classification logic\n\n"
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
    1. Generate test cases from server discovery
    2. Execute tests against the MCP server
    3. Generate HTML report

    Note: Currently only the generate step is fully implemented.
    Run and report steps will fail with NotImplemented errors.
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

    # Step 1: Generate (this works)
    console.print("\n[bold blue]═══ Phase 1: Test Generation ═══[/bold blue]\n")

    try:
        asyncio.run(_run_generation(probe_config, logging.getLogger(__name__)))
    except SystemExit as e:
        if e.code != 0:
            console.print("\n[red]Pipeline aborted due to generation failure.[/red]")
            raise

    # Step 2: Run (placeholder - will fail)
    console.print("\n[bold blue]═══ Phase 2: Test Execution ═══[/bold blue]\n")
    console.print(
        "[yellow]⚠ Skipping test execution - Test Runner not implemented.[/yellow]"
    )
    console.print(
        "[dim]The following phases require the Test Runner module (Task 11.0).[/dim]\n"
    )

    # Step 3: Report (placeholder - would fail)
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
            "[green]✓[/green] Test generation completed successfully.\n"
            "[yellow]⚠[/yellow] Test execution skipped (not implemented).\n"
            "[yellow]⚠[/yellow] Report generation skipped (not implemented).\n\n"
            "[dim]Once all modules are implemented, the full pipeline will\n"
            "execute all phases automatically.[/dim]",
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

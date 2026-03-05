import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from mcp_probe_pilot.orchestrator import MCPProbeOrchestrator, OrchestratorError

app = typer.Typer(add_completion=False, help="MCP-Probe CLI")
console = Console()


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
):
    """
    Run the MCP-Probe pipeline using the configuration found in the repository root.
    """
    try:
        orchestrator = MCPProbeOrchestrator(
            repository_root=repo_root, generate_new=generate_new
        )
    except OrchestratorError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(
        Panel(
            f"[bold cyan]MCP-Probe Configuration Loaded[/bold cyan]\n\n"
            f"[bold]Server Command:[/bold] [dim]{orchestrator.get_server_command()}[/dim]\n"
            f"[bold]Transport:[/bold]      {orchestrator.get_transport()}\n"
            f"[bold]Service URL:[/bold]    {orchestrator.get_service_url()}\n"
            f"[bold]Generate New Tests:[/bold]   {'[yellow]Yes[/yellow]' if orchestrator.get_generate_new() else 'No'}",
            expand=False,
        )
    )

    console.print("\n[bold]Starting MCP-Probe Pipeline...[/bold]")

    # Step 1: MCP Server Discovery
    with console.status(
        "[bold blue]Discovering MCP Server...[/bold blue]", spinner="dots"
    ):
        # Step 1.1: Discover MCP Server capabilities
        with console.status(
            "[bold blue]    Discovering MCP Server capabilities...[/bold blue]", spinner="line"
        ):
            try:
                result = asyncio.run(orchestrator.run_discovery())
                console.print(
                    f"[green]✓ \\[Discovery 1/3][/green] Discovery complete! "
                    f"Found {result.tool_count} tools, "
                    f"{result.resource_count} resources, "
                    f"and {result.prompt_count} prompts."
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
                index = orchestrator.run_ast_indexing()
                console.print(
                    f"[green]✓ \\[Discovery 2/3][/green] AST indexing complete! "
                    f"Indexed {index.total_entities} entities from {index.total_files} files."
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
                result = asyncio.run(orchestrator.send_codebase_index())
                indexed_count = result.get("indexed_count", "unknown")
                console.print(
                    f"[green]✓ \\[Discovery 3/3][/green] Codebase index sent to service! "
                    f"{indexed_count} entities indexed in ChromaDB."
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
                result = orchestrator.run_unit_test_planning()
                console.print(
                    f"[green]✓ \\[Test Generation 1/5][/green] Unit Test Planning complete! "
                    f"Planned {result.num_scenarios} scenarios."
                    f"Scenario plans: {'\n'.join([f'{value}' for value in result.scenario_plans])}" # Temporary debug print CHECK
                )
            except Exception as exc:
                console.print(f"[red]✗[/red] Unit Test Planning failed: {exc}")
                raise typer.Exit(code=1)
        
        # Step 2.2: Planning Integration Test Scenarios
        with console.status(
            "[bold blue]    Planning Integration Test Scenarios[/bold blue]",
            spinner="line",
        ):
            try:
                result = orchestrator.run_integration_test_planning()
                console.print(
                    f"[green]✓ \\[Test Generation 2/5][/green] Integration Test Planning complete! "
                    f"Generated {result.num_scenarios} scenarios."
                    f"Scenario plans: {'\n'.join([f'{value}' for value in result.scenario_plans])}" # Temporary debug print CHECK
                )
            except Exception as exc:
                console.print(f"[red]✗[/red] Integration Test Planning failed: {exc}")
                raise typer.Exit(code=1)

        # Step 2.3: Generating Feature Files
        with console.status(
            "[bold blue]    Generating Feature Files[/bold blue]",
            spinner="line",
        ):
            try:
                result = asyncio.run(orchestrator.generate_feature_files())
                console.print(
                    f"[green]✓ \\[Test Generation 3/5][/green] Feature Files generated! "
                    f"{result.files_generated} files written, {result.files_failed} failed."
                )
                for warning in result.validation_warnings:
                    console.print(f"  [yellow]⚠ {warning}[/yellow]")
            except Exception as exc:
                console.print(f"[red]✗[/red] Feature Files generation failed: {exc}")
                raise typer.Exit(code=1)


    

    console.print("\n[bold green]✨ Pipeline finished successfully![/bold green]\n")


if __name__ == "__main__":
    app()

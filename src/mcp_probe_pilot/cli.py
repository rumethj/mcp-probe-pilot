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
        "[bold blue]Discovery:Discovering MCP Server capabilities...[/bold blue]", spinner="dots"
    ):
        try:
            result = asyncio.run(orchestrator.run_discovery())
            console.print(
                f"[green]✓[/green] Discovery complete! "
                f"Found {result.tool_count} tools, "
                f"{result.resource_count} resources, "
                f"and {result.prompt_count} prompts."
            )
        except Exception as exc:
            console.print(f"[red]✗[/red] Discovery failed: {exc}")
            raise typer.Exit(code=1)

    # Step 2: AST Codebase Indexing
    with console.status(
        "[bold blue]Indexing repository source code...[/bold blue]",
        spinner="bouncingBar",
    ):
        try:
            index = orchestrator.run_ast_indexing()
            console.print(
                f"[green]✓[/green] AST indexing complete! "
                f"Indexed {index.total_entities} entities from {index.total_files} files."
            )
        except Exception as exc:
            console.print(f"[red]✗[/red] AST indexing failed: {exc}")
            raise typer.Exit(code=1)

    # Step 3: Send codebase index to mcp-probe-service
    with console.status(
        "[bold blue]Sending codebase index to mcp-probe-service...[/bold blue]",
        spinner="bouncingBar",
    ):
        try:
            result = asyncio.run(orchestrator.send_codebase_index())
            indexed_count = result.get("indexed_count", "unknown")
            console.print(
                f"[green]✓[/green] Codebase index sent to service! "
                f"{indexed_count} entities indexed in ChromaDB."
            )
        except Exception as exc:
            console.print(f"[red]✗[/red] Failed to send codebase index: {exc}")
            raise typer.Exit(code=1)

    # Step 4: Test Generation (placeholder)
    console.print("[dim]⏭  Test generation not yet implemented.[/dim]")

    console.print("\n[bold green]✨ Pipeline finished successfully![/bold green]\n")


if __name__ == "__main__":
    app()

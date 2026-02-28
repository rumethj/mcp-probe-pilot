import json
import time
from pathlib import Path
from pydantic import ValidationError

import typer
from rich.console import Console
from rich.panel import Panel

from mcp_probe_pilot.core.models import ProbeConfig

# Initialize CLI app and rich console
app = typer.Typer(add_completion=False, help="MCP-Probe CLI")
console = Console()

CONFIG_FILENAME = "mcp-probe-service-properties.json"




def load_config(repo_root: Path) -> ProbeConfig:
    """Load the configuration from the given path."""
    config_path = repo_root / CONFIG_FILENAME

    if not config_path.exists():
        console.print(f"[red]Error:[/red] Configuration file not found at [cyan]{config_path}[/cyan]")
        raise typer.Exit(code=1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
            
        return ProbeConfig(**raw_config)

    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON in [cyan]{config_path}[/cyan]\nDetails: {e}")
        raise typer.Exit(code=1)
        
    except ValidationError as e:
        console.print(f"[red]Error:[/red] Missing or invalid keys in config [cyan]{config_path}[/cyan]:")
        for error in e.errors():
            field_name = error["loc"][0]
            error_msg = error["msg"]
            console.print(f"  [yellow]- {field_name}: {error_msg}[/yellow]")
        raise typer.Exit(code=1)


@app.command()
def main(
    repo_root: Path = typer.Argument(
        ..., 
        help="Path to the repository root directory",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True
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
    # Load configuration
    config = load_config(repo_root)
    config.generate_new = generate_new

    # Success output
    console.print(
        Panel(
            f"[bold cyan]MCP-Probe Configuration Loaded[/bold cyan]\n\n"
            f"[bold]Project Code:[/bold]   [green]{config.project_code}[/green]\n"
            f"[bold]Server Command:[/bold] [dim]{config.server_command}[/dim]\n"
            f"[bold]Transport:[/bold]      {config.transport}\n"
            f"[bold]Service URL:[/bold]    {config.service_url}\n"
            f"[bold]Generate New:[/bold]    {'[yellow]Yes[/yellow]' if config.generate_new else 'No'}",
            expand=False
        )
    )

    console.print("\n[bold]Starting MCP-Probe Pipeline...[/bold]")

    # ==========================================
    # PIPELINE STEPS WITH SPINNERS
    # ==========================================
    
    # Step 1: Simulated Discovery
    with console.status("[bold blue]Discovering MCP Server capabilities...[/bold blue]", spinner="dots"):
        time.sleep(2)  # Simulate a 2-second network call
        console.print("[green]✓[/green] Discovery complete! Found 3 tools and 2 resources.")

    # Step 2: Simulated AST Indexing
    with console.status("[bold blue]Indexing repository source code...[/bold blue]", spinner="bouncingBar"):
        time.sleep(3)  # Simulate 3 seconds of file parsing
        console.print("[green]✓[/green] AST Indexing complete! Indexed 45 files.")

    # Step 3: Simulated Test Generation
    with console.status("[bold blue]Generating Gherkin BDD tests...[/bold blue]", spinner="line"):
        time.sleep(2.5)  # Simulate 2.5 seconds of LLM generation
        console.print("[green]✓[/green] Test generation complete! Wrote 5 feature files.")
    
    console.print("\n[bold green]✨ Pipeline finished successfully![/bold green]\n")


if __name__ == "__main__":
    app()
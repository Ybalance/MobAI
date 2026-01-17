"""Main CLI application for Mobile-Use."""

import sys
import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    name="mobile-use",
    help="AI-Driven Mobile Device Automation System",
    add_completion=False,
)
console = Console(force_terminal=True)


@app.command()
def version():
    """Show version information."""
    console.print(Panel(
        Text("Mobile-Use v2.0.0\nAI-Driven Mobile Device Automation", justify="center"),
        title="Version Info",
        border_style="blue"
    ))


@app.command()
def run(
    instruction: str = typer.Argument(..., help="Natural language instruction"),
    device_id: str = typer.Option(None, "--device", "-d", help="Device ID"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Execute a natural language task on a mobile device."""
    console.print(f"[bold green]Executing:[/bold green] {instruction}")
    if device_id:
        console.print(f"[blue]Device:[/blue] {device_id}")

    # TODO: Implement actual task execution
    console.print("[yellow]Task execution not yet implemented[/yellow]")


@app.command()
def device():
    """Device management commands."""
    console.print("[bold blue]Device Management[/bold blue]")
    console.print("Available commands:")
    console.print("  • mobile-use device list    - List available devices")
    console.print("  • mobile-use device connect - Connect to a device")


@app.command()
def config():
    """Configuration management."""
    console.print("[bold blue]Configuration Management[/bold blue]")
    console.print("Available commands:")
    console.print("  • mobile-use config show   - Show current configuration")
    console.print("  • mobile-use config set    - Set configuration values")


if __name__ == "__main__":
    app()

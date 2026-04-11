"""CLI entry point — mlaude serve."""

import subprocess
import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(name="mlaude", invoke_without_command=True)
console = Console()


@app.callback(invoke_without_command=True)
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(7474, "--port", "-p", help="Port to listen on"),
    reload: bool = typer.Option(True, "--reload", help="Enable auto-reload"),
):
    """Start the Mlaude agent server."""
    import uvicorn

    # Show LAN IP for phone access
    lan_ip = "unknown"
    try:
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            lan_ip = result.stdout.strip()
    except Exception:
        pass

    console.print(
        Panel(
            f"[bold]mlaude[/bold] v0.2\n\n"
            f"  Local:   [bold]http://localhost:{port}[/bold]\n"
            f"  Network: [bold]http://{lan_ip}:{port}[/bold]\n\n"
            f"  [dim]Stop with Ctrl+C[/dim]",
            border_style="bright_black",
        )
    )

    uvicorn.run(
        "mlaude.server:app",
        host=host,
        port=port,
        log_level="warning",
        reload=reload,
        reload_dirs=["src"],
    )

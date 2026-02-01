"""CLI interface with Typer."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv()

app = typer.Typer(name="onchain3r", help="Token due diligence system")
console = Console()


@app.callback()
def main() -> None:
    """Onchain3r - Token due diligence system."""


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


@app.command()
def analyze(
    address: str = typer.Argument(..., help="Token contract address"),
    chain: str = typer.Option("base", help="Chain name"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown or json"),
) -> None:
    """Analyze a token and generate a due diligence report."""
    from onchain3r.core.engine import Engine
    from onchain3r.reporter.generator import to_json, to_markdown

    config = _load_config()

    console.print(Panel(f"Analyzing [bold]{address}[/bold] on [cyan]{chain}[/cyan]..."))

    engine = Engine(config)
    report = asyncio.run(engine.analyze(address, chain))

    if fmt == "json":
        text = to_json(report)
    else:
        text = to_markdown(report)

    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"Report saved to [green]{output}[/green]")
    else:
        console.print(text)


@app.command()
def debug(
    address: str = typer.Argument(..., help="Token contract address"),
    chain: str = typer.Option("base", help="Chain name"),
    collector: str | None = typer.Option(None, "--collector", "-c", help="Only run a specific collector: onchain, dex, social, web"),
    output: str | None = typer.Option(None, "--output", "-o", help="Save debug output to file"),
) -> None:
    """Run collectors in debug mode - shows raw API responses without LLM analysis."""
    import json as _json

    from rich.syntax import Syntax

    from onchain3r.core.engine import Engine

    config = _load_config()
    engine = Engine(config)
    engine.set_debug(True)

    if collector:
        engine.collectors = [c for c in engine.collectors if c.name == collector]
        if not engine.collectors:
            console.print(f"[red]Unknown collector: {collector}[/red]")
            raise typer.Exit(1)

    console.print(Panel(
        f"[yellow]DEBUG MODE[/yellow] - Analyzing [bold]{address}[/bold] on [cyan]{chain}[/cyan]\n"
        f"Collectors: {', '.join(c.name for c in engine.collectors)}"
    ))

    results = asyncio.run(engine.collect_all(address, chain))

    # Show collector results
    for r in results:
        status = "[green]OK[/green]" if r.success else f"[red]FAIL: {r.error}[/red]"
        console.print(f"\n{'='*60}")
        console.print(f"[bold]{r.source.upper()}[/bold] - {status}")
        console.print(f"{'='*60}")

        if r.data:
            data_json = _json.dumps(r.data.model_dump(mode="json"), indent=2, default=str)
            console.print(Syntax(data_json, "json", theme="monokai", line_numbers=False))

    # Show raw API responses
    debug_logs = engine.get_debug_logs()
    if debug_logs:
        console.print(f"\n{'='*60}")
        console.print("[bold yellow]RAW API RESPONSES[/bold yellow]")
        console.print(f"{'='*60}")

        for name, entries in debug_logs.items():
            for entry in entries:
                label = entry.get("label", "")
                console.print(f"\n[cyan]{name}[/cyan] | [dim]{label}[/dim]")
                if "status" in entry:
                    console.print(f"  Status: {entry['status']}")
                if "response" in entry:
                    raw = _json.dumps(entry["response"], indent=2, default=str)
                    # Truncate very long responses for terminal readability
                    if len(raw) > 5000:
                        raw = raw[:5000] + "\n... (truncated)"
                    console.print(Syntax(raw, "json", theme="monokai", line_numbers=False))
                if "error" in entry:
                    console.print(f"  [red]{entry['error']}[/red]")
                    if "traceback" in entry:
                        console.print(f"  [dim]{entry['traceback']}[/dim]")

    if output:
        dump = {
            "results": [r.model_dump(mode="json") for r in results],
            "raw_api_logs": debug_logs,
        }
        Path(output).write_text(_json.dumps(dump, indent=2, default=str), encoding="utf-8")
        console.print(f"\nDebug output saved to [green]{output}[/green]")


if __name__ == "__main__":
    app()

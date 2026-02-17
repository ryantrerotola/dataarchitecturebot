"""CLI interface for snowflake-architect."""

from __future__ import annotations

import logging
import sys

import click
from rich.console import Console
from rich.table import Table

from snowflake_architect.analyzer import ArchitectureAnalyzer
from snowflake_architect.config import load_config
from snowflake_architect.extractor import MetadataExtractor
from snowflake_architect.recommender import (
    ALL_GOALS,
    GOAL_DESCRIPTIONS,
    generate_recommendations,
)
from snowflake_architect.report import generate_report

console = Console()

GOAL_CHOICES = click.Choice(ALL_GOALS, case_sensitive=False)


@click.group()
@click.option("--config", "-c", "config_path", default=None, help="Path to YAML config file.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
@click.pass_context
def main(ctx: click.Context, config_path: str | None, verbose: bool) -> None:
    """Snowflake Architecture Analyzer — analyze lineage and recommend improvements."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["verbose"] = verbose


@main.command()
@click.option(
    "--goal", "-g",
    multiple=True,
    type=GOAL_CHOICES,
    help=(
        "Optimization goal (can specify multiple). "
        "Options: reduce_compute, reduce_storage, simplify, "
        "improve_reliability, improve_performance, governance"
    ),
)
@click.option(
    "--output-dir", "-o",
    default="./reports",
    help="Directory for the output report.",
)
@click.option(
    "--stale-days",
    default=90,
    type=int,
    help="Days after which an unmodified object is considered stale.",
)
@click.option(
    "--low-usage-days",
    default=30,
    type=int,
    help="Days of no reads after which an object is considered unused.",
)
@click.pass_context
def analyze(
    ctx: click.Context,
    goal: tuple[str, ...],
    output_dir: str,
    stale_days: int,
    low_usage_days: int,
) -> None:
    """Run full architecture analysis and generate a report."""
    config_path = ctx.obj["config_path"]

    try:
        config = load_config(config_path)
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)

    config.stale_threshold_days = stale_days
    config.low_usage_threshold_days = low_usage_days
    config.output_dir = output_dir
    if goal:
        config.goals = list(goal)

    goals = config.goals if config.goals else None

    console.print("[bold]Snowflake Architecture Analyzer[/bold]\n")

    # Extract
    console.print("[cyan]Connecting to Snowflake...[/cyan]")
    with MetadataExtractor(config) as extractor:
        console.print("[cyan]Extracting metadata...[/cyan]")
        metadata = extractor.extract_all()

    console.print(
        f"  Found [green]{len(metadata.objects)}[/green] objects, "
        f"[green]{len(metadata.lineage_edges)}[/green] lineage edges, "
        f"[green]{len(metadata.query_usage)}[/green] usage records"
    )

    # Analyze
    console.print("\n[cyan]Analyzing architecture...[/cyan]")
    analyzer = ArchitectureAnalyzer(
        metadata,
        stale_threshold_days=stale_days,
        low_usage_threshold_days=low_usage_days,
    )
    analysis = analyzer.analyze()

    # Recommend
    console.print("[cyan]Generating recommendations...[/cyan]")
    report = generate_recommendations(analysis, goals)

    # Display summary
    _print_summary(report.recommendations, goals)

    # Write report
    console.print(f"\n[cyan]Writing report...[/cyan]")
    report_path = generate_report(report, output_dir)
    console.print(f"\n[bold green]Report saved to:[/bold green] {report_path}")


@main.command()
def goals() -> None:
    """List available optimization goals."""
    table = Table(title="Available Optimization Goals")
    table.add_column("Goal", style="cyan")
    table.add_column("Description")

    for goal_id, desc in GOAL_DESCRIPTIONS.items():
        table.add_row(goal_id, desc)

    console.print(table)
    console.print("\nUsage: [cyan]snowflake-architect analyze -g reduce_compute -g simplify[/cyan]")


@main.command()
@click.pass_context
def test_connection(ctx: click.Context) -> None:
    """Test the Snowflake connection without running analysis."""
    config_path = ctx.obj["config_path"]

    try:
        config = load_config(config_path)
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)

    console.print(f"Connecting to account [cyan]{config.connection.account}[/cyan]...")
    try:
        with MetadataExtractor(config) as extractor:
            databases = extractor._get_databases()
            console.print(f"[green]Connected successfully![/green]")
            console.print(f"Accessible databases: {', '.join(databases)}")
    except Exception as e:
        console.print(f"[red]Connection failed:[/red] {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

PRIORITY_COLORS = {
    "CRITICAL": "red",
    "HIGH": "dark_orange",
    "MEDIUM": "yellow",
    "LOW": "green",
}


def _print_summary(recommendations: list, goals: list[str] | None) -> None:
    if goals:
        goal_str = ", ".join(g.replace("_", " ").title() for g in goals)
        console.print(f"\n[bold]Goals:[/bold] {goal_str}")

    if not recommendations:
        console.print("\n[green]No issues found — architecture looks clean.[/green]")
        return

    table = Table(title="Top Findings")
    table.add_column("#", width=3)
    table.add_column("Priority", width=10)
    table.add_column("Category", width=16)
    table.add_column("Finding", max_width=60)

    for i, rec in enumerate(recommendations[:15], 1):
        color = PRIORITY_COLORS.get(rec.priority_label, "white")
        table.add_row(
            str(i),
            f"[{color}]{rec.priority_label}[/{color}]",
            rec.finding.category,
            rec.finding.title,
        )

    console.print(table)

    if len(recommendations) > 15:
        console.print(f"  ...and {len(recommendations) - 15} more findings in the report.")

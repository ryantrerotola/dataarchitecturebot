"""Markdown report generator with Mermaid lineage diagrams."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import networkx as nx

from snowflake_architect.analyzer import AnalysisResult
from snowflake_architect.recommender import Recommendation, RecommendationReport

logger = logging.getLogger(__name__)

PRIORITY_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}

SEVERITY_EMOJI = {
    "high": "🔴",
    "medium": "🟡",
    "low": "🟢",
    "info": "🔵",
}


def generate_report(report: RecommendationReport, output_dir: str = "./reports") -> str:
    """Generate a Markdown report file and return its path."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_file = out_path / f"architecture_report_{timestamp}.md"

    sections = [
        _header_section(report),
        _summary_section(report),
        _lineage_diagram_section(report.analysis),
        _recommendations_section(report),
        _detailed_findings_section(report),
        _object_inventory_section(report.analysis),
        _warehouse_section(report),
        _footer_section(),
    ]

    content = "\n\n".join(s for s in sections if s)

    report_file.write_text(content, encoding="utf-8")
    logger.info("Report written to %s", report_file)
    return str(report_file)


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------


def _header_section(report: RecommendationReport) -> str:
    from snowflake_architect import __version__

    goal_labels = {
        "reduce_compute": "Reduce Compute",
        "reduce_storage": "Reduce Storage",
        "simplify": "Simplify Architecture",
        "improve_reliability": "Improve Reliability",
        "improve_performance": "Improve Performance",
        "governance": "Governance",
    }
    goals_str = ", ".join(goal_labels.get(g, g) for g in report.goals)

    return f"""# Snowflake Architecture Analysis Report

**Generated:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
**Tool Version:** {__version__}
**Goals:** {goals_str}

---"""


def _summary_section(report: RecommendationReport) -> str:
    a = report.analysis
    recs = report.recommendations

    critical = sum(1 for r in recs if r.priority_label == "CRITICAL")
    high = sum(1 for r in recs if r.priority_label == "HIGH")
    medium = sum(1 for r in recs if r.priority_label == "MEDIUM")
    low = sum(1 for r in recs if r.priority_label == "LOW")

    return f"""## Executive Summary

| Metric | Value |
|--------|-------|
| Databases analyzed | {a.database_count} |
| Total objects | {a.object_count} |
| Lineage edges | {a.edge_count} |
| Total storage | {_fmt_bytes(a.total_storage_bytes)} |
| Findings | {len(recs)} |

### Finding Breakdown

| Priority | Count |
|----------|-------|
| {PRIORITY_EMOJI['CRITICAL']} Critical | {critical} |
| {PRIORITY_EMOJI['HIGH']} High | {high} |
| {PRIORITY_EMOJI['MEDIUM']} Medium | {medium} |
| {PRIORITY_EMOJI['LOW']} Low | {low} |"""


def _lineage_diagram_section(analysis: AnalysisResult) -> str:
    """Generate a Mermaid flowchart of the lineage graph.

    For large graphs, only include the most-connected subgraph to keep
    the diagram readable.
    """
    graph = analysis.graph
    if graph.number_of_nodes() == 0:
        return ""

    # For large graphs, take top nodes by total degree
    max_nodes = 40
    if graph.number_of_nodes() > max_nodes:
        top_nodes = sorted(
            graph.nodes, key=lambda n: graph.degree(n), reverse=True
        )[:max_nodes]
        subgraph = graph.subgraph(top_nodes)
    else:
        subgraph = graph

    lines = ["## Lineage Overview", "", "```mermaid", "flowchart LR"]

    # Assign short IDs to nodes for readability
    node_ids: dict[str, str] = {}
    for i, node in enumerate(subgraph.nodes):
        nid = f"n{i}"
        node_ids[node] = nid
        # Use just the table name for the label
        label = _short_name(node)
        obj_type = subgraph.nodes[node].get("object_type", "")
        if obj_type == "VIEW":
            lines.append(f'    {nid}[/"{label}"/]')
        elif obj_type == "MATERIALIZED VIEW":
            lines.append(f'    {nid}[["{label}"]]')
        else:
            lines.append(f'    {nid}["{label}"]')

    for src, tgt in subgraph.edges:
        if src in node_ids and tgt in node_ids:
            lines.append(f"    {node_ids[src]} --> {node_ids[tgt]}")

    lines.append("```")

    if graph.number_of_nodes() > max_nodes:
        lines.append(
            f"\n*Showing top {max_nodes} most-connected objects out of "
            f"{graph.number_of_nodes()} total.*"
        )

    return "\n".join(lines)


def _recommendations_section(report: RecommendationReport) -> str:
    if not report.recommendations:
        return "## Recommendations\n\nNo issues found — your architecture looks clean."

    lines = ["## Top Recommendations", ""]

    # Show top 10 most relevant recommendations
    top = [r for r in report.recommendations if r.relevance_score > 0][:10]
    if not top:
        top = report.recommendations[:10]

    for i, rec in enumerate(top, 1):
        emoji = PRIORITY_EMOJI.get(rec.priority_label, "")
        goals = ", ".join(
            g.replace("_", " ").title() for g in rec.relevant_goals
        )
        lines.append(
            f"### {i}. {emoji} {rec.finding.title}\n"
            f"**Priority:** {rec.priority_label} | "
            f"**Category:** {rec.finding.category} | "
            f"**Severity:** {rec.finding.severity}\n"
        )
        if goals:
            lines.append(f"**Relevant goals:** {goals}\n")
        lines.append(f"{rec.finding.description}\n")
        lines.append(f"**Recommendation:** {rec.finding.recommendation}\n")
        if rec.finding.estimated_impact:
            lines.append(f"**Estimated impact:** {rec.finding.estimated_impact}\n")
        if rec.finding.affected_objects:
            lines.append("**Affected objects:**")
            for obj in rec.finding.affected_objects[:10]:
                lines.append(f"- `{obj}`")
            if len(rec.finding.affected_objects) > 10:
                lines.append(
                    f"- *...and {len(rec.finding.affected_objects) - 10} more*"
                )
        lines.append("")

    return "\n".join(lines)


def _detailed_findings_section(report: RecommendationReport) -> str:
    if len(report.recommendations) <= 10:
        return ""

    remaining = report.recommendations[10:]
    if not remaining:
        return ""

    lines = ["## Additional Findings", ""]
    lines.append("| # | Priority | Category | Title |")
    lines.append("|---|----------|----------|-------|")

    for i, rec in enumerate(remaining, 11):
        emoji = PRIORITY_EMOJI.get(rec.priority_label, "")
        lines.append(
            f"| {i} | {emoji} {rec.priority_label} | {rec.finding.category} | {rec.finding.title} |"
        )

    return "\n".join(lines)


def _object_inventory_section(analysis: AnalysisResult) -> str:
    """Summary of objects by type and database."""
    if analysis.object_count == 0:
        return ""

    # Count by type
    type_counts: dict[str, int] = {}
    db_counts: dict[str, int] = {}
    graph = analysis.graph
    for node in graph.nodes:
        obj_type = graph.nodes[node].get("object_type", "UNKNOWN")
        type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
        db = graph.nodes[node].get("database", "")
        if db:
            db_counts[db] = db_counts.get(db, 0) + 1

    lines = ["## Object Inventory", ""]
    lines.append("### By Type")
    lines.append("| Type | Count |")
    lines.append("|------|-------|")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {t} | {c} |")

    lines.append("")
    lines.append("### By Database")
    lines.append("| Database | Objects |")
    lines.append("|----------|---------|")
    for db, c in sorted(db_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {db} | {c} |")

    return "\n".join(lines)


def _warehouse_section(report: RecommendationReport) -> str:
    warehouses = report.analysis.graph  # We'll get this from metadata
    wh_data = getattr(report, "_warehouse_data", None)
    # Warehouse data is in the original metadata, which we can access via analysis
    # For now, we'll skip if not available
    return ""


def _footer_section() -> str:
    return """---

*Generated by [snowflake-architect](https://github.com/ryantrerotola/dataarchitecturebot). \
Findings are based on Snowflake metadata and heuristics — always validate before making changes.*"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_name(fqn: str) -> str:
    """Extract a readable short name from a fully qualified name."""
    parts = fqn.split(".")
    if len(parts) >= 3:
        return f"{parts[1]}.{parts[2]}"
    return parts[-1]


def _fmt_bytes(b: int) -> str:
    if b >= 1_099_511_627_776:
        return f"{b / 1_099_511_627_776:.1f} TB"
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.1f} GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f} MB"
    if b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} bytes"

"""Goal-driven recommendation engine — filters and prioritizes findings based on user goals."""

from __future__ import annotations

from dataclasses import dataclass, field

from snowflake_architect.analyzer import AnalysisResult, Finding


# ---------------------------------------------------------------------------
# Goal definitions
# ---------------------------------------------------------------------------

# Each goal maps to the finding categories it cares about, with weight multipliers.
# Higher weight = more relevant to that goal.
GOAL_CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    "reduce_compute": {
        "cycle": 2.0,
        "deep_lineage": 2.0,
        "clustering": 2.0,
        "write_only": 1.5,
        "fan_out": 1.0,
        "bottleneck": 0.5,
        "duplication": 1.0,
    },
    "reduce_storage": {
        "stale_data": 2.0,
        "unused": 2.0,
        "duplication": 2.0,
        "write_only": 1.5,
        "retention": 1.5,
    },
    "simplify": {
        "cycle": 2.0,
        "deep_lineage": 2.0,
        "fan_out": 1.5,
        "schema_sprawl": 2.0,
        "duplication": 1.5,
        "bottleneck": 1.0,
    },
    "improve_reliability": {
        "cycle": 2.5,
        "bottleneck": 2.0,
        "deep_lineage": 1.5,
        "fan_out": 1.0,
    },
    "improve_performance": {
        "clustering": 2.5,
        "deep_lineage": 2.0,
        "cycle": 1.5,
        "fan_out": 1.0,
    },
    "governance": {
        "schema_sprawl": 2.0,
        "unused": 1.5,
        "stale_data": 1.5,
        "duplication": 1.0,
    },
}

GOAL_DESCRIPTIONS: dict[str, str] = {
    "reduce_compute": "Reduce credit consumption and compute costs",
    "reduce_storage": "Reduce storage costs by removing or archiving unused data",
    "simplify": "Simplify the data architecture and reduce complexity",
    "improve_reliability": "Improve pipeline reliability and reduce failure risk",
    "improve_performance": "Improve query and pipeline performance",
    "governance": "Improve data governance, discovery, and compliance",
}

ALL_GOALS = list(GOAL_DESCRIPTIONS.keys())


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


@dataclass
class Recommendation:
    finding: Finding
    relevance_score: float  # 0.0 - 1.0, how relevant to the stated goals
    relevant_goals: list[str] = field(default_factory=list)

    @property
    def priority_label(self) -> str:
        if self.relevance_score >= 0.8:
            return "CRITICAL"
        if self.relevance_score >= 0.5:
            return "HIGH"
        if self.relevance_score >= 0.3:
            return "MEDIUM"
        return "LOW"


@dataclass
class RecommendationReport:
    recommendations: list[Recommendation]
    goals: list[str]
    analysis: AnalysisResult
    summary: str = ""


def generate_recommendations(
    analysis: AnalysisResult,
    goals: list[str] | None = None,
) -> RecommendationReport:
    """Score and prioritize findings based on user goals.

    If no goals are specified, all findings are returned with equal weight.
    """
    if not goals:
        goals = ALL_GOALS  # show everything

    # Normalize goal names
    goals = [g.lower().replace(" ", "_").replace("-", "_") for g in goals]

    recommendations: list[Recommendation] = []
    for finding in analysis.findings:
        score, relevant = _score_finding(finding, goals)
        recommendations.append(Recommendation(
            finding=finding,
            relevance_score=score,
            relevant_goals=relevant,
        ))

    # Sort: highest relevance first, then by severity
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    recommendations.sort(
        key=lambda r: (-r.relevance_score, severity_order.get(r.finding.severity, 4))
    )

    summary = _build_summary(recommendations, goals, analysis)

    return RecommendationReport(
        recommendations=recommendations,
        goals=goals,
        analysis=analysis,
        summary=summary,
    )


def _score_finding(finding: Finding, goals: list[str]) -> tuple[float, list[str]]:
    """Compute a relevance score (0-1) for a finding given the active goals."""
    max_possible = 0.0
    actual = 0.0
    relevant_goals = []

    severity_mult = {"high": 1.5, "medium": 1.0, "low": 0.6, "info": 0.3}
    sev = severity_mult.get(finding.severity, 1.0)

    for goal in goals:
        weights = GOAL_CATEGORY_WEIGHTS.get(goal, {})
        max_possible += 2.5 * sev  # max weight * severity
        weight = weights.get(finding.category, 0.0)
        if weight > 0:
            actual += weight * sev
            relevant_goals.append(goal)

    if max_possible == 0:
        return 0.0, relevant_goals

    return min(actual / max_possible, 1.0), relevant_goals


def _build_summary(
    recommendations: list[Recommendation],
    goals: list[str],
    analysis: AnalysisResult,
) -> str:
    goal_labels = [GOAL_DESCRIPTIONS.get(g, g) for g in goals]
    critical = sum(1 for r in recommendations if r.priority_label == "CRITICAL")
    high = sum(1 for r in recommendations if r.priority_label == "HIGH")

    lines = [
        f"Analyzed {analysis.object_count} objects across {analysis.database_count} databases "
        f"with {analysis.edge_count} lineage edges.",
        f"Total storage: {_fmt_bytes(analysis.total_storage_bytes)}.",
        "",
        f"Goals: {', '.join(goal_labels)}.",
        "",
        f"Found {len(recommendations)} findings: "
        f"{critical} critical, {high} high priority.",
    ]
    return "\n".join(lines)


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

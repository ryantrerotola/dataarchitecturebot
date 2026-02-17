"""Tests for the recommendation engine."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from snowflake_architect.analyzer import AnalysisResult, ArchitectureAnalyzer, Finding
from snowflake_architect.extractor import ExtractedMetadata, LineageEdge, ObjectInfo, QueryUsage
from snowflake_architect.recommender import (
    ALL_GOALS,
    generate_recommendations,
)


def _make_finding(category, severity="medium", title="Test finding"):
    return Finding(
        category=category,
        severity=severity,
        title=title,
        description="Description",
        recommendation="Fix it",
    )


def _make_analysis(findings: list[Finding]) -> AnalysisResult:
    return AnalysisResult(
        findings=findings,
        object_count=10,
        edge_count=5,
        database_count=2,
        total_storage_bytes=1_000_000_000,
    )


class TestGoalPrioritization:
    def test_reduce_compute_prioritizes_cycles(self):
        findings = [
            _make_finding("stale_data", severity="medium"),
            _make_finding("cycle", severity="high"),
            _make_finding("schema_sprawl", severity="low"),
        ]
        analysis = _make_analysis(findings)
        report = generate_recommendations(analysis, goals=["reduce_compute"])

        # Cycle should be the top recommendation for reduce_compute
        assert report.recommendations[0].finding.category == "cycle"
        assert report.recommendations[0].relevance_score > 0

    def test_reduce_storage_prioritizes_stale_and_unused(self):
        findings = [
            _make_finding("cycle", severity="medium"),
            _make_finding("stale_data", severity="medium"),
            _make_finding("unused", severity="medium"),
        ]
        analysis = _make_analysis(findings)
        report = generate_recommendations(analysis, goals=["reduce_storage"])

        top_categories = [r.finding.category for r in report.recommendations[:2]]
        assert "stale_data" in top_categories
        assert "unused" in top_categories

    def test_simplify_prioritizes_complexity(self):
        findings = [
            _make_finding("clustering", severity="medium"),
            _make_finding("deep_lineage", severity="medium"),
            _make_finding("schema_sprawl", severity="medium"),
        ]
        analysis = _make_analysis(findings)
        report = generate_recommendations(analysis, goals=["simplify"])

        top_categories = [r.finding.category for r in report.recommendations[:2]]
        assert "deep_lineage" in top_categories
        assert "schema_sprawl" in top_categories

    def test_no_goals_shows_everything(self):
        findings = [
            _make_finding("cycle", severity="high"),
            _make_finding("stale_data", severity="low"),
        ]
        analysis = _make_analysis(findings)
        report = generate_recommendations(analysis, goals=None)

        assert len(report.recommendations) == 2
        assert len(report.goals) == len(ALL_GOALS)

    def test_multiple_goals(self):
        findings = [
            _make_finding("cycle", severity="high"),
            _make_finding("stale_data", severity="medium"),
            _make_finding("clustering", severity="medium"),
        ]
        analysis = _make_analysis(findings)
        report = generate_recommendations(
            analysis, goals=["reduce_compute", "reduce_storage"]
        )

        # Cycle should score high (relevant to reduce_compute)
        # Stale data should score high (relevant to reduce_storage)
        assert report.recommendations[0].relevance_score > 0
        assert len(report.recommendations) == 3


class TestRecommendationReport:
    def test_summary_generated(self):
        findings = [_make_finding("cycle", severity="high")]
        analysis = _make_analysis(findings)
        report = generate_recommendations(analysis, goals=["reduce_compute"])

        assert "10 objects" in report.summary
        assert "2 databases" in report.summary

    def test_priority_labels(self):
        findings = [_make_finding("cycle", severity="high")]
        analysis = _make_analysis(findings)
        report = generate_recommendations(analysis, goals=["reduce_compute"])

        rec = report.recommendations[0]
        assert rec.priority_label in ("CRITICAL", "HIGH", "MEDIUM", "LOW")

    def test_relevant_goals_tracked(self):
        findings = [_make_finding("stale_data", severity="medium")]
        analysis = _make_analysis(findings)
        report = generate_recommendations(analysis, goals=["reduce_storage"])

        rec = report.recommendations[0]
        assert "reduce_storage" in rec.relevant_goals


class TestGoalNormalization:
    def test_goal_names_normalized(self):
        findings = [_make_finding("cycle", severity="high")]
        analysis = _make_analysis(findings)

        # Various input formats should all work
        report = generate_recommendations(analysis, goals=["Reduce Compute"])
        assert "reduce_compute" in report.goals

        report = generate_recommendations(analysis, goals=["reduce-compute"])
        assert "reduce_compute" in report.goals

"""Tests for the Markdown report generator."""

from __future__ import annotations

from snowflake_architect.analyzer import AnalysisResult, Finding
from snowflake_architect.recommender import generate_recommendations
from snowflake_architect.report import generate_report


def _make_finding(category, severity="medium", title="Test finding"):
    return Finding(
        category=category,
        severity=severity,
        title=title,
        description="A test description.",
        affected_objects=["DB.SCHEMA.TABLE1"],
        recommendation="Fix the issue.",
        estimated_impact="Saves money.",
    )


def _make_analysis(findings: list[Finding]) -> AnalysisResult:
    return AnalysisResult(
        findings=findings,
        object_count=5,
        edge_count=3,
        database_count=1,
        total_storage_bytes=500_000_000,
    )


class TestReportGeneration:
    def test_generates_markdown_file(self, tmp_path):
        findings = [
            _make_finding("cycle", severity="high", title="Circular dep"),
            _make_finding("stale_data", severity="medium", title="Stale tables"),
        ]
        analysis = _make_analysis(findings)
        report = generate_recommendations(analysis, goals=["reduce_compute", "reduce_storage"])

        path = generate_report(report, output_dir=str(tmp_path))

        assert path.endswith(".md")
        content = open(path).read()
        assert "# Snowflake Architecture Analysis Report" in content
        assert "Circular dep" in content
        assert "Stale tables" in content

    def test_report_contains_summary_table(self, tmp_path):
        analysis = _make_analysis([_make_finding("unused")])
        report = generate_recommendations(analysis, goals=["reduce_storage"])

        path = generate_report(report, output_dir=str(tmp_path))
        content = open(path).read()

        assert "Executive Summary" in content
        assert "5" in content  # object count
        assert "500.0 MB" in content or "476.8 MB" in content  # storage

    def test_report_with_no_findings(self, tmp_path):
        analysis = _make_analysis([])
        report = generate_recommendations(analysis)

        path = generate_report(report, output_dir=str(tmp_path))
        content = open(path).read()

        assert "looks clean" in content

    def test_report_contains_affected_objects(self, tmp_path):
        analysis = _make_analysis([_make_finding("cycle", severity="high")])
        report = generate_recommendations(analysis, goals=["simplify"])

        path = generate_report(report, output_dir=str(tmp_path))
        content = open(path).read()

        assert "DB.SCHEMA.TABLE1" in content

"""Tests for the architecture analyzer."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from snowflake_architect.analyzer import ArchitectureAnalyzer, _fmt_bytes
from snowflake_architect.extractor import (
    ExtractedMetadata,
    LineageEdge,
    ObjectInfo,
    QueryUsage,
)


def _make_obj(
    db="DB",
    schema="PUBLIC",
    name="TABLE1",
    obj_type="TABLE",
    row_count=1000,
    bytes_=1_000_000,
    last_altered=None,
    clustering_key=None,
    is_transient=False,
) -> ObjectInfo:
    return ObjectInfo(
        database=db,
        schema=schema,
        name=name,
        object_type=obj_type,
        row_count=row_count,
        bytes=bytes_,
        created=datetime(2023, 1, 1),
        last_altered=last_altered or datetime.utcnow(),
        clustering_key=clustering_key,
        is_transient=is_transient,
    )


def _make_edge(src_name, tgt_name, db="DB", schema="PUBLIC") -> LineageEdge:
    return LineageEdge(
        source_database=db,
        source_schema=schema,
        source_name=src_name,
        source_object_type="TABLE",
        target_database=db,
        target_schema=schema,
        target_name=tgt_name,
        target_object_type="TABLE",
    )


def _make_usage(
    name, db="DB", schema="PUBLIC", reads=10, writes=5
) -> QueryUsage:
    return QueryUsage(
        database=db,
        schema=schema,
        name=name,
        total_queries=reads + writes,
        read_queries=reads,
        write_queries=writes,
        last_read=datetime.utcnow() if reads else None,
        last_write=datetime.utcnow() if writes else None,
    )


class TestCycleDetection:
    def test_detects_simple_cycle(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="A"),
                _make_obj(name="B"),
                _make_obj(name="C"),
            ],
            lineage_edges=[
                _make_edge("A", "B"),
                _make_edge("B", "C"),
                _make_edge("C", "A"),  # creates cycle
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        cycle_findings = [f for f in result.findings if f.category == "cycle"]
        assert len(cycle_findings) >= 1
        assert cycle_findings[0].severity == "high"

    def test_no_cycle_in_dag(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="A"),
                _make_obj(name="B"),
                _make_obj(name="C"),
            ],
            lineage_edges=[
                _make_edge("A", "B"),
                _make_edge("B", "C"),
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        cycle_findings = [f for f in result.findings if f.category == "cycle"]
        assert len(cycle_findings) == 0


class TestStaleObjectDetection:
    def test_detects_stale_tables(self):
        old_date = datetime.utcnow() - timedelta(days=120)
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="OLD_TABLE", last_altered=old_date, bytes_=5_000_000_000),
                _make_obj(name="FRESH_TABLE"),  # defaults to now
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata, stale_threshold_days=90)
        result = analyzer.analyze()

        stale_findings = [f for f in result.findings if f.category == "stale_data"]
        assert len(stale_findings) == 1
        assert "OLD_TABLE" in stale_findings[0].affected_objects[0]

    def test_views_not_flagged_as_stale(self):
        old_date = datetime.utcnow() - timedelta(days=120)
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="OLD_VIEW", obj_type="VIEW", last_altered=old_date),
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata, stale_threshold_days=90)
        result = analyzer.analyze()

        stale_findings = [f for f in result.findings if f.category == "stale_data"]
        assert len(stale_findings) == 0


class TestUnusedObjectDetection:
    def test_detects_unused_objects(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="USED"),
                _make_obj(name="UNUSED"),
            ],
            query_usage=[
                _make_usage("USED", reads=50),
                # UNUSED has no usage entry
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        unused = [f for f in result.findings if f.category == "unused"]
        assert len(unused) == 1
        assert any("UNUSED" in obj for obj in unused[0].affected_objects)

    def test_detects_write_only(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="WRITE_ONLY"),
            ],
            query_usage=[
                _make_usage("WRITE_ONLY", reads=0, writes=100),
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        write_only = [f for f in result.findings if f.category == "write_only"]
        assert len(write_only) == 1


class TestDeepLineage:
    def test_detects_deep_chains(self):
        # Create a chain of 10 objects
        names = [f"T{i}" for i in range(10)]
        objects = [_make_obj(name=n) for n in names]
        edges = [_make_edge(names[i], names[i + 1]) for i in range(9)]

        metadata = ExtractedMetadata(objects=objects, lineage_edges=edges)
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        deep = [f for f in result.findings if f.category == "deep_lineage"]
        assert len(deep) == 1


class TestDuplicateDetection:
    def test_detects_same_size_tables(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="COPY_A", row_count=50000, bytes_=10_000_000),
                _make_obj(name="COPY_B", row_count=50000, bytes_=10_000_000),
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        dupes = [f for f in result.findings if f.category == "duplication"]
        assert len(dupes) == 1

    def test_different_sizes_not_flagged(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="TABLE_A", row_count=50000, bytes_=10_000_000),
                _make_obj(name="TABLE_B", row_count=60000, bytes_=12_000_000),
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        dupes = [f for f in result.findings if f.category == "duplication"]
        assert len(dupes) == 0


class TestClusteringDetection:
    def test_detects_large_unclustered(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(
                    name="BIG_TABLE",
                    bytes_=5_000_000_000,  # 5 GB
                    clustering_key=None,
                ),
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        clustering = [f for f in result.findings if f.category == "clustering"]
        assert len(clustering) == 1

    def test_clustered_table_not_flagged(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(
                    name="CLUSTERED",
                    bytes_=5_000_000_000,
                    clustering_key="(date_col)",
                ),
            ],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        clustering = [f for f in result.findings if f.category == "clustering"]
        assert len(clustering) == 0


class TestRetentionCandidates:
    def test_detects_staging_tables(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(name="STG_ORDERS"),
                _make_obj(name="RAW_EVENTS"),
                _make_obj(name="FACT_SALES"),  # not staging
            ],
        )
        # Set retention_time so they're flagged
        for obj in metadata.objects:
            obj.retention_time = 1

        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        retention = [f for f in result.findings if f.category == "retention"]
        assert len(retention) == 1
        affected_names = " ".join(retention[0].affected_objects)
        assert "STG_ORDERS" in affected_names
        assert "RAW_EVENTS" in affected_names
        assert "FACT_SALES" not in affected_names


class TestFmtBytes:
    def test_bytes(self):
        assert _fmt_bytes(500) == "500 bytes"

    def test_kb(self):
        assert _fmt_bytes(2048) == "2.0 KB"

    def test_mb(self):
        assert _fmt_bytes(5 * 1024 * 1024) == "5.0 MB"

    def test_gb(self):
        assert _fmt_bytes(3 * 1024 * 1024 * 1024) == "3.0 GB"

    def test_tb(self):
        assert _fmt_bytes(2 * 1024 * 1024 * 1024 * 1024) == "2.0 TB"


class TestGraphMetrics:
    def test_analysis_result_metrics(self):
        metadata = ExtractedMetadata(
            objects=[
                _make_obj(db="DB1", name="A"),
                _make_obj(db="DB2", name="B"),
            ],
            lineage_edges=[_make_edge("A", "B")],
        )
        analyzer = ArchitectureAnalyzer(metadata)
        result = analyzer.analyze()

        assert result.object_count == 2
        assert result.database_count == 2
        assert result.edge_count == 1
        assert result.total_storage_bytes == 2_000_000

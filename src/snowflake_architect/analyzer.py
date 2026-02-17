"""Graph-based lineage analysis — builds a DAG and detects structural issues."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import networkx as nx

from snowflake_architect.extractor import ExtractedMetadata, LineageEdge, ObjectInfo, QueryUsage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Finding types
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    category: str  # e.g. "stale_data", "cycle", "unused", "duplication", etc.
    severity: str  # "high", "medium", "low", "info"
    title: str
    description: str
    affected_objects: list[str] = field(default_factory=list)
    recommendation: str = ""
    estimated_impact: str = ""  # human-readable impact note


@dataclass
class AnalysisResult:
    findings: list[Finding] = field(default_factory=list)
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    object_count: int = 0
    edge_count: int = 0
    database_count: int = 0
    total_storage_bytes: int = 0
    analysis_time: datetime = field(default_factory=datetime.utcnow)

    @property
    def high_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "high"]

    @property
    def medium_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "medium"]

    @property
    def low_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "low"]


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class ArchitectureAnalyzer:
    def __init__(
        self,
        metadata: ExtractedMetadata,
        stale_threshold_days: int = 90,
        low_usage_threshold_days: int = 30,
    ):
        self.metadata = metadata
        self.stale_days = stale_threshold_days
        self.low_usage_days = low_usage_threshold_days
        self.graph = nx.DiGraph()
        self._object_map: dict[str, ObjectInfo] = {}
        self._usage_map: dict[str, QueryUsage] = {}
        self._build_graph()

    def _build_graph(self) -> None:
        """Construct the lineage DAG from extracted metadata."""
        for obj in self.metadata.objects:
            fqn = obj.fqn
            self._object_map[fqn] = obj
            self.graph.add_node(fqn, **{
                "object_type": obj.object_type,
                "database": obj.database,
                "schema": obj.schema,
                "name": obj.name,
                "row_count": obj.row_count,
                "bytes": obj.bytes,
                "created": obj.created,
                "last_altered": obj.last_altered,
            })

        for usage in self.metadata.query_usage:
            fqn = f"{usage.database}.{usage.schema}.{usage.name}"
            self._usage_map[fqn] = usage

        for edge in self.metadata.lineage_edges:
            src = edge.source_fqn
            tgt = edge.target_fqn
            # Ensure nodes exist even if not in object list (e.g. external sources)
            if src not in self.graph:
                self.graph.add_node(src, object_type=edge.source_object_type, external=True)
            if tgt not in self.graph:
                self.graph.add_node(tgt, object_type=edge.target_object_type, external=True)
            self.graph.add_edge(src, tgt)

        logger.info(
            "Built lineage graph: %d nodes, %d edges",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )

    def analyze(self) -> AnalysisResult:
        """Run all analysis checks and return findings."""
        result = AnalysisResult(
            graph=self.graph,
            object_count=len(self.metadata.objects),
            edge_count=len(self.metadata.lineage_edges),
            database_count=len({o.database for o in self.metadata.objects}),
            total_storage_bytes=sum(o.bytes or 0 for o in self.metadata.objects),
        )

        result.findings.extend(self._find_cycles())
        result.findings.extend(self._find_stale_objects())
        result.findings.extend(self._find_unused_objects())
        result.findings.extend(self._find_write_only_objects())
        result.findings.extend(self._find_deep_lineage_chains())
        result.findings.extend(self._find_wide_fan_out())
        result.findings.extend(self._find_potential_duplicates())
        result.findings.extend(self._find_large_unclustered_tables())
        result.findings.extend(self._find_high_retention_transient_candidates())
        result.findings.extend(self._find_single_source_bottlenecks())
        result.findings.extend(self._find_schema_sprawl())

        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        result.findings.sort(key=lambda f: severity_order.get(f.severity, 4))

        logger.info("Analysis complete: %d findings", len(result.findings))
        return result

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def _find_cycles(self) -> list[Finding]:
        """Detect cycles in the lineage graph (logical loops)."""
        findings = []
        cycles = list(nx.simple_cycles(self.graph))
        if cycles:
            for cycle in cycles[:20]:  # cap reported cycles
                cycle_path = " -> ".join(cycle) + f" -> {cycle[0]}"
                findings.append(Finding(
                    category="cycle",
                    severity="high",
                    title="Circular dependency detected",
                    description=(
                        f"A circular data dependency exists: {cycle_path}. "
                        "This means data flows in a loop, which can cause infinite refresh "
                        "chains, stale data, or unpredictable results."
                    ),
                    affected_objects=cycle,
                    recommendation=(
                        "Break the cycle by removing one of the edges. Consider whether "
                        "one of these objects can read from a shared upstream source instead "
                        "of creating a circular reference."
                    ),
                    estimated_impact="Eliminates potential infinite refresh loops and simplifies lineage.",
                ))
            if len(cycles) > 20:
                findings.append(Finding(
                    category="cycle",
                    severity="high",
                    title=f"{len(cycles) - 20} additional cycles detected",
                    description=f"There are {len(cycles)} total circular dependencies. Only the first 20 are shown.",
                    recommendation="Audit the full lineage graph to resolve all cycles.",
                ))
        return findings

    def _find_stale_objects(self) -> list[Finding]:
        """Find objects that haven't been modified in a long time but still consume storage."""
        findings = []
        now = datetime.utcnow()
        threshold = now - timedelta(days=self.stale_days)

        stale_objects = []
        for obj in self.metadata.objects:
            if obj.object_type == "VIEW":
                continue  # views don't consume storage
            if obj.last_altered and obj.last_altered < threshold:
                stale_objects.append(obj)

        if stale_objects:
            stale_objects.sort(key=lambda o: o.bytes or 0, reverse=True)
            total_bytes = sum(o.bytes or 0 for o in stale_objects)

            # Group into one finding with top offenders listed
            top_names = [o.fqn for o in stale_objects[:15]]
            findings.append(Finding(
                category="stale_data",
                severity="medium" if total_bytes > 1_000_000_000 else "low",
                title=f"{len(stale_objects)} stale objects (not modified in {self.stale_days}+ days)",
                description=(
                    f"These objects haven't been modified in over {self.stale_days} days "
                    f"and collectively consume {_fmt_bytes(total_bytes)} of storage."
                ),
                affected_objects=top_names,
                recommendation=(
                    "Review whether these objects are still needed. Consider archiving, "
                    "dropping, or converting to transient tables if Time Travel isn't needed."
                ),
                estimated_impact=f"Could reclaim up to {_fmt_bytes(total_bytes)} of storage.",
            ))
        return findings

    def _find_unused_objects(self) -> list[Finding]:
        """Find objects with no read queries in the lookback period."""
        findings = []
        unused = []
        for obj in self.metadata.objects:
            fqn = obj.fqn
            usage = self._usage_map.get(fqn)
            if usage is None or usage.read_queries == 0:
                unused.append(obj)

        if unused:
            unused.sort(key=lambda o: o.bytes or 0, reverse=True)
            total_bytes = sum(o.bytes or 0 for o in unused)
            names = [o.fqn for o in unused[:15]]

            findings.append(Finding(
                category="unused",
                severity="medium" if total_bytes > 500_000_000 else "low",
                title=f"{len(unused)} objects with no read queries in {self.low_usage_days}+ days",
                description=(
                    f"These objects exist but have not been read by any query recently. "
                    f"They consume {_fmt_bytes(total_bytes)} of storage."
                ),
                affected_objects=names,
                recommendation=(
                    "Verify these objects aren't consumed by external tools outside Snowflake. "
                    "If truly unused, drop them or archive to external storage."
                ),
                estimated_impact=f"Could reclaim up to {_fmt_bytes(total_bytes)} and reduce clutter.",
            ))
        return findings

    def _find_write_only_objects(self) -> list[Finding]:
        """Find objects that are written to but never read — data is produced but not consumed."""
        findings = []
        write_only = []
        for fqn, usage in self._usage_map.items():
            if usage.write_queries > 0 and usage.read_queries == 0:
                obj = self._object_map.get(fqn)
                if obj and obj.object_type != "VIEW":
                    write_only.append(obj)

        if write_only:
            write_only.sort(key=lambda o: o.bytes or 0, reverse=True)
            total_bytes = sum(o.bytes or 0 for o in write_only)
            names = [o.fqn for o in write_only[:10]]

            findings.append(Finding(
                category="write_only",
                severity="medium",
                title=f"{len(write_only)} objects are written to but never read",
                description=(
                    "These objects are actively being loaded or updated by pipelines, "
                    "but no queries read from them. This wastes compute on writes and "
                    f"storage ({_fmt_bytes(total_bytes)})."
                ),
                affected_objects=names,
                recommendation=(
                    "Investigate whether the write pipelines can be disabled. "
                    "The data may be an artifact of an old pipeline that's no longer consumed."
                ),
                estimated_impact=f"Could save compute costs from unnecessary writes and {_fmt_bytes(total_bytes)} storage.",
            ))
        return findings

    def _find_deep_lineage_chains(self, max_depth: int = 8) -> list[Finding]:
        """Find lineage chains that are excessively deep (many hops from source to target)."""
        findings = []
        # Find root nodes (no incoming edges)
        roots = [n for n in self.graph.nodes if self.graph.in_degree(n) == 0]

        deep_chains = []
        for root in roots:
            lengths = nx.single_source_shortest_path_length(self.graph, root)
            for node, depth in lengths.items():
                if depth >= max_depth:
                    deep_chains.append((root, node, depth))

        if deep_chains:
            deep_chains.sort(key=lambda x: x[2], reverse=True)
            descriptions = []
            affected = set()
            for src, tgt, depth in deep_chains[:10]:
                descriptions.append(f"  {src} -> ... -> {tgt} ({depth} hops)")
                affected.add(src)
                affected.add(tgt)

            findings.append(Finding(
                category="deep_lineage",
                severity="medium",
                title=f"{len(deep_chains)} excessively deep lineage chains ({max_depth}+ hops)",
                description=(
                    "Long transformation chains increase latency, make debugging harder, "
                    "and create fragile pipelines:\n" + "\n".join(descriptions)
                ),
                affected_objects=list(affected)[:15],
                recommendation=(
                    "Consider materializing intermediate results closer to the source, "
                    "or consolidating transformation steps to reduce hop count."
                ),
                estimated_impact="Reduces pipeline latency and simplifies debugging.",
            ))
        return findings

    def _find_wide_fan_out(self, threshold: int = 10) -> list[Finding]:
        """Find objects that feed into many downstream objects (high fan-out)."""
        findings = []
        high_fanout = [
            (node, self.graph.out_degree(node))
            for node in self.graph.nodes
            if self.graph.out_degree(node) >= threshold
        ]

        if high_fanout:
            high_fanout.sort(key=lambda x: x[1], reverse=True)
            affected = []
            desc_lines = []
            for node, degree in high_fanout[:10]:
                desc_lines.append(f"  {node}: {degree} downstream dependents")
                affected.append(node)

            findings.append(Finding(
                category="fan_out",
                severity="low",
                title=f"{len(high_fanout)} objects with high fan-out ({threshold}+ dependents)",
                description=(
                    "These objects feed many downstream tables/views. Changes to them "
                    "will cascade widely:\n" + "\n".join(desc_lines)
                ),
                affected_objects=affected,
                recommendation=(
                    "Ensure these high-impact objects have thorough testing and monitoring. "
                    "Consider whether some downstream objects can share a common intermediate layer."
                ),
                estimated_impact="Reduces blast radius of schema changes.",
            ))
        return findings

    def _find_potential_duplicates(self) -> list[Finding]:
        """Detect objects that might be duplicates based on identical schemas and similar names."""
        findings = []
        # Group by (row_count, bytes) as a rough similarity signal
        signature_groups: dict[tuple, list[ObjectInfo]] = {}
        for obj in self.metadata.objects:
            if obj.object_type == "VIEW" or obj.row_count is None or obj.bytes is None:
                continue
            if obj.row_count == 0:
                continue
            sig = (obj.row_count, obj.bytes)
            signature_groups.setdefault(sig, []).append(obj)

        duplicate_groups = [
            group for group in signature_groups.values()
            if len(group) > 1
        ]

        if duplicate_groups:
            duplicate_groups.sort(key=lambda g: g[0].bytes or 0, reverse=True)
            total_waste = sum(
                (len(g) - 1) * (g[0].bytes or 0) for g in duplicate_groups
            )

            desc_lines = []
            all_affected = []
            for group in duplicate_groups[:10]:
                names = [o.fqn for o in group]
                desc_lines.append(
                    f"  Possible duplicates ({_fmt_bytes(group[0].bytes or 0)}, "
                    f"{group[0].row_count:,} rows): {', '.join(names)}"
                )
                all_affected.extend(names)

            findings.append(Finding(
                category="duplication",
                severity="medium" if total_waste > 1_000_000_000 else "low",
                title=f"{len(duplicate_groups)} potential duplicate table groups",
                description=(
                    "These groups of tables have identical row counts and byte sizes, "
                    "suggesting they may be copies of the same data:\n" + "\n".join(desc_lines)
                ),
                affected_objects=all_affected[:20],
                recommendation=(
                    "Investigate whether these are intentional copies (e.g. snapshots) "
                    "or accidental duplicates. Consolidate where possible using views or "
                    "secure data sharing."
                ),
                estimated_impact=f"Could reclaim up to {_fmt_bytes(total_waste)} if duplicates are consolidated.",
            ))
        return findings

    def _find_large_unclustered_tables(self, size_threshold_gb: float = 1.0) -> list[Finding]:
        """Find large tables without clustering keys."""
        findings = []
        threshold_bytes = int(size_threshold_gb * 1024 * 1024 * 1024)

        unclustered = [
            obj for obj in self.metadata.objects
            if obj.object_type == "TABLE"
            and (obj.bytes or 0) >= threshold_bytes
            and not obj.clustering_key
        ]

        if unclustered:
            unclustered.sort(key=lambda o: o.bytes or 0, reverse=True)
            names = [f"{o.fqn} ({_fmt_bytes(o.bytes or 0)})" for o in unclustered[:10]]

            findings.append(Finding(
                category="clustering",
                severity="medium",
                title=f"{len(unclustered)} large tables without clustering keys",
                description=(
                    "Tables over 1 GB without clustering keys may have poor query performance "
                    "and higher scan costs:\n  " + "\n  ".join(names)
                ),
                affected_objects=[o.fqn for o in unclustered[:10]],
                recommendation=(
                    "Add clustering keys based on the most common filter/join columns. "
                    "This improves micro-partition pruning and reduces compute costs."
                ),
                estimated_impact="Can significantly reduce query scan times and credit consumption.",
            ))
        return findings

    def _find_high_retention_transient_candidates(self) -> list[Finding]:
        """Find non-transient tables that might benefit from being transient."""
        findings = []
        candidates = []
        for obj in self.metadata.objects:
            if obj.object_type != "TABLE" or obj.is_transient:
                continue
            # If the table is a staging/temp table or rarely read, it may not need Time Travel
            usage = self._usage_map.get(obj.fqn)
            name_lower = obj.name.lower()
            is_staging = any(
                kw in name_lower for kw in ("stg", "staging", "tmp", "temp", "raw", "landing")
            )
            if is_staging and (obj.retention_time or 1) > 0:
                candidates.append(obj)

        if candidates:
            total_bytes = sum(o.bytes or 0 for o in candidates)
            names = [o.fqn for o in candidates[:10]]

            findings.append(Finding(
                category="retention",
                severity="low",
                title=f"{len(candidates)} staging/temp tables with Time Travel retention",
                description=(
                    "These tables appear to be staging or temporary data but have Time Travel "
                    f"retention enabled, consuming extra storage ({_fmt_bytes(total_bytes)})."
                ),
                affected_objects=names,
                recommendation=(
                    "Convert staging/temp tables to TRANSIENT tables and set "
                    "DATA_RETENTION_TIME_IN_DAYS = 0 to reduce Fail-safe and Time Travel costs."
                ),
                estimated_impact=f"Could reduce storage overhead by up to {_fmt_bytes(total_bytes)}.",
            ))
        return findings

    def _find_single_source_bottlenecks(self) -> list[Finding]:
        """Find objects that are the sole source for many critical downstream objects."""
        findings = []
        bottlenecks = []
        for node in self.graph.nodes:
            successors = list(self.graph.successors(node))
            if len(successors) < 5:
                continue
            # Check if any successor has only this one source
            sole_source_count = sum(
                1 for s in successors if self.graph.in_degree(s) == 1
            )
            if sole_source_count >= 3:
                bottlenecks.append((node, sole_source_count, len(successors)))

        if bottlenecks:
            bottlenecks.sort(key=lambda x: x[1], reverse=True)
            desc_lines = []
            affected = []
            for node, sole_count, total in bottlenecks[:10]:
                desc_lines.append(
                    f"  {node}: sole source for {sole_count} of {total} downstream objects"
                )
                affected.append(node)

            findings.append(Finding(
                category="bottleneck",
                severity="medium",
                title=f"{len(bottlenecks)} single-source bottleneck objects",
                description=(
                    "These objects are the only data source for multiple downstream objects. "
                    "If they fail or become stale, all dependents are affected:\n"
                    + "\n".join(desc_lines)
                ),
                affected_objects=affected,
                recommendation=(
                    "Add monitoring and alerting for these critical objects. Consider "
                    "whether downstream objects can have fallback sources or whether "
                    "the bottleneck should be replicated for resilience."
                ),
                estimated_impact="Improves pipeline resilience and reduces single points of failure.",
            ))
        return findings

    def _find_schema_sprawl(self, threshold: int = 50) -> list[Finding]:
        """Detect databases with an excessive number of schemas."""
        findings = []
        db_schema_count: dict[str, set[str]] = {}
        for obj in self.metadata.objects:
            db_schema_count.setdefault(obj.database, set()).add(obj.schema)

        sprawl = [
            (db, len(schemas))
            for db, schemas in db_schema_count.items()
            if len(schemas) >= threshold
        ]

        if sprawl:
            sprawl.sort(key=lambda x: x[1], reverse=True)
            desc = ", ".join(f"{db} ({count} schemas)" for db, count in sprawl)
            findings.append(Finding(
                category="schema_sprawl",
                severity="low",
                title=f"{len(sprawl)} databases with schema sprawl",
                description=(
                    f"These databases have {threshold}+ schemas, which can make discovery "
                    f"and governance harder: {desc}"
                ),
                affected_objects=[db for db, _ in sprawl],
                recommendation=(
                    "Consolidate schemas where possible. Use a consistent naming convention "
                    "and archive unused schemas."
                ),
                estimated_impact="Simplifies data discovery, access management, and governance.",
            ))
        return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

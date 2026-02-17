"""Snowflake metadata extraction — pulls lineage, usage stats, storage, and object info."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import snowflake.connector

from snowflake_architect.config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes for extracted metadata
# ---------------------------------------------------------------------------


@dataclass
class ObjectInfo:
    database: str
    schema: str
    name: str
    object_type: str  # TABLE, VIEW, MATERIALIZED VIEW, DYNAMIC TABLE, etc.
    row_count: int | None = None
    bytes: int | None = None
    created: datetime | None = None
    last_altered: datetime | None = None
    retention_time: int | None = None
    is_transient: bool = False
    clustering_key: str | None = None
    comment: str | None = None
    table_type: str | None = None  # BASE TABLE, TEMPORARY, EXTERNAL, etc.

    @property
    def fqn(self) -> str:
        return f"{self.database}.{self.schema}.{self.name}"


@dataclass
class LineageEdge:
    """A directed edge: source_object -> target_object."""

    source_database: str
    source_schema: str
    source_name: str
    source_object_type: str
    target_database: str
    target_schema: str
    target_name: str
    target_object_type: str

    @property
    def source_fqn(self) -> str:
        return f"{self.source_database}.{self.source_schema}.{self.source_name}"

    @property
    def target_fqn(self) -> str:
        return f"{self.target_database}.{self.target_schema}.{self.target_name}"


@dataclass
class QueryUsage:
    """Aggregated query usage statistics for an object."""

    database: str
    schema: str
    name: str
    total_queries: int = 0
    read_queries: int = 0
    write_queries: int = 0
    last_read: datetime | None = None
    last_write: datetime | None = None
    total_credits_used: float = 0.0


@dataclass
class WarehouseUsage:
    warehouse_name: str
    total_credits: float = 0.0
    total_queries: int = 0
    avg_execution_time_ms: float = 0.0
    avg_queued_time_ms: float = 0.0


@dataclass
class ExtractedMetadata:
    objects: list[ObjectInfo] = field(default_factory=list)
    lineage_edges: list[LineageEdge] = field(default_factory=list)
    query_usage: list[QueryUsage] = field(default_factory=list)
    warehouse_usage: list[WarehouseUsage] = field(default_factory=list)
    extraction_time: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_OBJECTS_QUERY = """
SELECT
    table_catalog AS database_name,
    table_schema AS schema_name,
    table_name AS name,
    table_type,
    row_count,
    bytes,
    created,
    last_altered,
    retention_time,
    is_transient,
    clustering_key,
    comment
FROM {database}.information_schema.tables
WHERE table_schema NOT IN ({exclude_schemas})
ORDER BY table_catalog, table_schema, table_name
"""

_LINEAGE_QUERY = """
SELECT DISTINCT
    directSources.value:objectDomain::STRING AS source_object_type,
    directSources.value:objectName::STRING   AS source_object_name,
    om.value:objectDomain::STRING            AS target_object_type,
    om.value:objectName::STRING              AS target_object_name
FROM snowflake.account_usage.access_history,
    LATERAL FLATTEN(input => objects_modified) om,
    LATERAL FLATTEN(input => om.value:directSources) directSources
WHERE query_start_time >= DATEADD('day', -{lookback_days}, CURRENT_TIMESTAMP())
    AND directSources.value:objectName IS NOT NULL
    AND om.value:objectName IS NOT NULL
"""

_QUERY_USAGE_QUERY = """
WITH base_objects AS (
    SELECT
        directSources.value:objectName::STRING AS object_name,
        'READ' AS access_type,
        qh.start_time,
        qh.total_elapsed_time,
        qh.warehouse_name
    FROM snowflake.account_usage.access_history ah,
        LATERAL FLATTEN(input => base_objects_accessed) directSources,
        snowflake.account_usage.query_history qh
    WHERE ah.query_id = qh.query_id
        AND ah.query_start_time >= DATEADD('day', -{lookback_days}, CURRENT_TIMESTAMP())
        AND directSources.value:objectName IS NOT NULL

    UNION ALL

    SELECT
        om.value:objectName::STRING AS object_name,
        'WRITE' AS access_type,
        qh.start_time,
        qh.total_elapsed_time,
        qh.warehouse_name
    FROM snowflake.account_usage.access_history ah,
        LATERAL FLATTEN(input => objects_modified) om,
        snowflake.account_usage.query_history qh
    WHERE ah.query_id = qh.query_id
        AND ah.query_start_time >= DATEADD('day', -{lookback_days}, CURRENT_TIMESTAMP())
        AND om.value:objectName IS NOT NULL
)
SELECT
    object_name,
    COUNT(*) AS total_queries,
    COUNT(CASE WHEN access_type = 'READ' THEN 1 END) AS read_queries,
    COUNT(CASE WHEN access_type = 'WRITE' THEN 1 END) AS write_queries,
    MAX(CASE WHEN access_type = 'READ' THEN start_time END) AS last_read,
    MAX(CASE WHEN access_type = 'WRITE' THEN start_time END) AS last_write
FROM base_objects
GROUP BY object_name
ORDER BY total_queries DESC
"""

_WAREHOUSE_USAGE_QUERY = """
SELECT
    warehouse_name,
    SUM(credits_used) AS total_credits,
    COUNT(*) AS total_queries,
    AVG(avg_running * 1000) AS avg_execution_time_ms,
    AVG(avg_queued_load * 1000) AS avg_queued_time_ms
FROM snowflake.account_usage.warehouse_metering_history wmh
LEFT JOIN (
    SELECT
        warehouse_name AS wh,
        AVG(total_elapsed_time) AS avg_running,
        AVG(queued_provisioning_time + queued_repair_time + queued_overload_time) AS avg_queued_load
    FROM snowflake.account_usage.query_history
    WHERE start_time >= DATEADD('day', -{lookback_days}, CURRENT_TIMESTAMP())
    GROUP BY warehouse_name
) qstats ON wmh.warehouse_name = qstats.wh
WHERE start_time >= DATEADD('day', -{lookback_days}, CURRENT_TIMESTAMP())
GROUP BY warehouse_name
ORDER BY total_credits DESC
"""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def _parse_fqn(fqn: str) -> tuple[str, str, str]:
    """Parse 'DB.SCHEMA.NAME' into (db, schema, name). Handles missing parts."""
    parts = fqn.split(".")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return "", parts[0], parts[1]
    return "", "", parts[0]


class MetadataExtractor:
    def __init__(self, config: Config):
        self.config = config
        self._conn: snowflake.connector.SnowflakeConnection | None = None

    def connect(self) -> None:
        logger.info("Connecting to Snowflake account: %s", self.config.connection.account)
        self._conn = snowflake.connector.connect(**self.config.connection.to_connect_params())

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    def _cursor(self):
        if not self._conn:
            raise RuntimeError("Not connected. Call connect() first or use as context manager.")
        return self._conn.cursor()

    def _get_databases(self) -> list[str]:
        """Get list of databases to analyze based on scope config."""
        scope = self.config.scope
        if scope.databases:
            return [db.upper() for db in scope.databases]

        cur = self._cursor()
        try:
            cur.execute("SHOW DATABASES")
            all_dbs = [row[1] for row in cur.fetchall()]
        finally:
            cur.close()

        excludes = {db.upper() for db in scope.exclude_databases}
        return [db for db in all_dbs if db.upper() not in excludes]

    def extract_objects(self) -> list[ObjectInfo]:
        """Extract table/view metadata from all in-scope databases."""
        databases = self._get_databases()
        objects: list[ObjectInfo] = []
        exclude_schemas = ", ".join(
            f"'{s}'" for s in self.config.scope.exclude_schemas
        )

        for db in databases:
            query = _OBJECTS_QUERY.format(database=db, exclude_schemas=exclude_schemas)
            cur = self._cursor()
            try:
                cur.execute(query)
                for row in cur.fetchall():
                    obj_type = _classify_table_type(row[3])
                    objects.append(ObjectInfo(
                        database=row[0] or db,
                        schema=row[1],
                        name=row[2],
                        object_type=obj_type,
                        row_count=row[4],
                        bytes=row[5],
                        created=row[6],
                        last_altered=row[7],
                        retention_time=row[8],
                        is_transient=row[9] == "YES" if row[9] else False,
                        clustering_key=row[10],
                        comment=row[11],
                        table_type=row[3],
                    ))
            except Exception as e:
                logger.warning("Could not query objects in %s: %s", db, e)
            finally:
                cur.close()

        logger.info("Extracted %d objects across %d databases", len(objects), len(databases))
        return objects

    def extract_lineage(self, lookback_days: int = 90) -> list[LineageEdge]:
        """Extract object-level lineage from access_history."""
        query = _LINEAGE_QUERY.format(lookback_days=lookback_days)
        edges: list[LineageEdge] = []
        cur = self._cursor()
        try:
            cur.execute(query)
            for row in cur.fetchall():
                src_type, src_fqn, tgt_type, tgt_fqn = row[0], row[1], row[2], row[3]
                sd, ss, sn = _parse_fqn(src_fqn)
                td, ts, tn = _parse_fqn(tgt_fqn)
                edges.append(LineageEdge(
                    source_database=sd,
                    source_schema=ss,
                    source_name=sn,
                    source_object_type=src_type or "UNKNOWN",
                    target_database=td,
                    target_schema=ts,
                    target_name=tn,
                    target_object_type=tgt_type or "UNKNOWN",
                ))
        except Exception as e:
            logger.warning("Could not extract lineage (requires SNOWFLAKE.ACCOUNT_USAGE access): %s", e)
        finally:
            cur.close()

        logger.info("Extracted %d lineage edges", len(edges))
        return edges

    def extract_query_usage(self, lookback_days: int = 90) -> list[QueryUsage]:
        """Extract per-object query usage statistics."""
        query = _QUERY_USAGE_QUERY.format(lookback_days=lookback_days)
        usage: list[QueryUsage] = []
        cur = self._cursor()
        try:
            cur.execute(query)
            for row in cur.fetchall():
                db, schema, name = _parse_fqn(row[0])
                usage.append(QueryUsage(
                    database=db,
                    schema=schema,
                    name=name,
                    total_queries=row[1] or 0,
                    read_queries=row[2] or 0,
                    write_queries=row[3] or 0,
                    last_read=row[4],
                    last_write=row[5],
                ))
        except Exception as e:
            logger.warning("Could not extract query usage: %s", e)
        finally:
            cur.close()

        logger.info("Extracted usage stats for %d objects", len(usage))
        return usage

    def extract_warehouse_usage(self, lookback_days: int = 90) -> list[WarehouseUsage]:
        """Extract warehouse-level credit and performance stats."""
        query = _WAREHOUSE_USAGE_QUERY.format(lookback_days=lookback_days)
        warehouses: list[WarehouseUsage] = []
        cur = self._cursor()
        try:
            cur.execute(query)
            for row in cur.fetchall():
                warehouses.append(WarehouseUsage(
                    warehouse_name=row[0],
                    total_credits=float(row[1] or 0),
                    total_queries=int(row[2] or 0),
                    avg_execution_time_ms=float(row[3] or 0),
                    avg_queued_time_ms=float(row[4] or 0),
                ))
        except Exception as e:
            logger.warning("Could not extract warehouse usage: %s", e)
        finally:
            cur.close()

        logger.info("Extracted usage for %d warehouses", len(warehouses))
        return warehouses

    def extract_all(self) -> ExtractedMetadata:
        """Run full extraction and return consolidated metadata."""
        lookback = max(self.config.stale_threshold_days, self.config.low_usage_threshold_days, 90)
        return ExtractedMetadata(
            objects=self.extract_objects(),
            lineage_edges=self.extract_lineage(lookback_days=lookback),
            query_usage=self.extract_query_usage(lookback_days=lookback),
            warehouse_usage=self.extract_warehouse_usage(lookback_days=lookback),
        )


def _classify_table_type(table_type: str | None) -> str:
    if not table_type:
        return "UNKNOWN"
    t = table_type.upper()
    if "VIEW" in t and "MATERIALIZED" in t:
        return "MATERIALIZED VIEW"
    if "VIEW" in t:
        return "VIEW"
    if "EXTERNAL" in t:
        return "EXTERNAL TABLE"
    return "TABLE"

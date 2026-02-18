"""DDL parser — extract objects and lineage from Snowflake DDL statements.

Supports CREATE TABLE, CREATE VIEW, CREATE MATERIALIZED VIEW, CREATE OR REPLACE
variants, TRANSIENT tables, CLUSTER BY, and derives lineage from view/CTAS SELECT
references.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from snowflake_architect.extractor import (
    ExtractedMetadata,
    LineageEdge,
    ObjectInfo,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for Snowflake DDL
# ---------------------------------------------------------------------------

# Matches: CREATE [OR REPLACE] [TRANSIENT] TABLE/VIEW/MATERIALIZED VIEW [IF NOT EXISTS] <name>
_CREATE_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?P<transient>TRANSIENT\s+)?"
    r"(?P<obj_type>(?:MATERIALIZED\s+)?(?:(?:DYNAMIC\s+)?TABLE|VIEW|SECURE\s+VIEW))"
    r"\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>(?:\"[^\"]*\"\.)*(?:\"[^\"]*\"|[^\s(]+))",
    re.IGNORECASE,
)

# Matches CLUSTER BY (col1, col2, ...) — including linear/expressions
_CLUSTER_BY_RE = re.compile(
    r"CLUSTER\s+BY\s*\(([^)]+)\)",
    re.IGNORECASE,
)

# Matches DATA_RETENTION_TIME_IN_DAYS = N
_RETENTION_RE = re.compile(
    r"DATA_RETENTION_TIME_IN_DAYS\s*=\s*(\d+)",
    re.IGNORECASE,
)

# Matches COMMENT = '...' on the CREATE statement
_COMMENT_RE = re.compile(
    r"COMMENT\s*=\s*'([^']*)'",
    re.IGNORECASE,
)

# Matches AS SELECT ... (for views and CTAS)
_AS_SELECT_RE = re.compile(
    r"\bAS\s*\n?\s*(?:WITH\b|\(?SELECT\b)",
    re.IGNORECASE,
)

# Finds table/view references inside a SELECT body.
# Looks for FROM/JOIN followed by a qualified or unqualified name.
_TABLE_REF_RE = re.compile(
    r"(?:FROM|JOIN)\s+"
    r"(?:LATERAL\s+FLATTEN\s*\(.*?\)\s+|"  # skip LATERAL FLATTEN(...)
    r"(?:TABLE\s*\(\s*)?)"  # skip TABLE( wrapper
    r"(?P<ref>"
    r"(?:[A-Za-z_][A-Za-z0-9_$]*\.){0,2}"  # optional db.schema. prefix
    r"[A-Za-z_][A-Za-z0-9_$]*"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_ddl(
    ddl_text: str,
    default_database: str = "DEFAULT_DB",
    default_schema: str = "PUBLIC",
) -> ExtractedMetadata:
    """Parse DDL text and return extracted metadata.

    Args:
        ddl_text: One or more DDL statements (separated by semicolons).
        default_database: Database name to use when not specified in DDL.
        default_schema: Schema name to use when not specified in DDL.

    Returns:
        ExtractedMetadata with objects and lineage edges populated.
        (query_usage and warehouse_usage will be empty since there's no runtime data.)
    """
    statements = _split_statements(ddl_text)
    objects: list[ObjectInfo] = []
    edges: list[LineageEdge] = []
    known_objects: dict[str, ObjectInfo] = {}  # fqn -> ObjectInfo

    for stmt in statements:
        result = _parse_create_statement(stmt, default_database, default_schema)
        if result is None:
            continue

        obj, source_refs = result
        objects.append(obj)
        known_objects[obj.fqn] = obj
        # Also index by short names for reference resolution
        known_objects[f"{obj.schema}.{obj.name}"] = obj
        known_objects[obj.name] = obj

        for ref in source_refs:
            ref_db, ref_schema, ref_name = _resolve_name(
                ref, default_database, default_schema
            )
            edges.append(LineageEdge(
                source_database=ref_db,
                source_schema=ref_schema,
                source_name=ref_name,
                source_object_type="TABLE",  # we can't tell from DDL alone
                target_database=obj.database,
                target_schema=obj.schema,
                target_name=obj.name,
                target_object_type=obj.object_type,
            ))

    logger.info(
        "Parsed %d objects and %d lineage edges from DDL",
        len(objects),
        len(edges),
    )

    return ExtractedMetadata(
        objects=objects,
        lineage_edges=edges,
        query_usage=[],
        warehouse_usage=[],
    )


def _split_statements(ddl_text: str) -> list[str]:
    """Split DDL text into individual statements on semicolons.

    Respects single-quoted strings so semicolons inside strings aren't split on.
    """
    statements = []
    current: list[str] = []
    in_string = False

    for char in ddl_text:
        if char == "'" and not in_string:
            in_string = True
            current.append(char)
        elif char == "'" and in_string:
            in_string = False
            current.append(char)
        elif char == ";" and not in_string:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)

    # Last statement (no trailing semicolon)
    remaining = "".join(current).strip()
    if remaining:
        statements.append(remaining)

    return statements


def _parse_create_statement(
    stmt: str,
    default_database: str,
    default_schema: str,
) -> tuple[ObjectInfo, list[str]] | None:
    """Parse a single CREATE statement. Returns (ObjectInfo, list of source refs) or None."""
    match = _CREATE_RE.search(stmt)
    if not match:
        return None

    raw_type = match.group("obj_type").upper()
    raw_name = match.group("name")
    is_transient = match.group("transient") is not None

    # Classify object type
    obj_type = _classify_type(raw_type)

    # Parse the fully qualified name
    db, schema, name = _resolve_name(raw_name, default_database, default_schema)

    # Extract optional properties
    clustering_key = None
    cluster_match = _CLUSTER_BY_RE.search(stmt)
    if cluster_match:
        clustering_key = cluster_match.group(1).strip()

    retention_time = None
    retention_match = _RETENTION_RE.search(stmt)
    if retention_match:
        retention_time = int(retention_match.group(1))

    comment = None
    comment_match = _COMMENT_RE.search(stmt)
    if comment_match:
        comment = comment_match.group(1)

    obj = ObjectInfo(
        database=db,
        schema=schema,
        name=name,
        object_type=obj_type,
        is_transient=is_transient,
        clustering_key=clustering_key,
        retention_time=retention_time,
        comment=comment,
        created=datetime.utcnow(),
        last_altered=datetime.utcnow(),
    )

    # Extract source references from AS SELECT body (views and CTAS)
    source_refs = _extract_source_refs(stmt, raw_name)

    return obj, source_refs


def _extract_source_refs(stmt: str, self_name: str) -> list[str]:
    """Extract table/view references from the SELECT body of a view or CTAS."""
    as_match = _AS_SELECT_RE.search(stmt)
    if not as_match:
        return []

    # Get everything after AS
    select_body = stmt[as_match.start():]

    refs = []
    seen = set()
    for ref_match in _TABLE_REF_RE.finditer(select_body):
        ref = ref_match.group("ref")
        # Skip self-references and common non-table keywords
        ref_upper = ref.upper()
        if ref_upper == self_name.upper().split(".")[-1]:
            continue
        if ref_upper in _SQL_KEYWORDS:
            continue
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)

    return refs


def _resolve_name(
    raw_name: str,
    default_database: str,
    default_schema: str,
) -> tuple[str, str, str]:
    """Resolve a possibly-qualified name into (database, schema, name).

    Strips surrounding quotes from each part.
    """
    parts = [_strip_quotes(p) for p in raw_name.split(".")]
    if len(parts) == 3:
        return parts[0].upper(), parts[1].upper(), parts[2].upper()
    if len(parts) == 2:
        return default_database.upper(), parts[0].upper(), parts[1].upper()
    return default_database.upper(), default_schema.upper(), parts[0].upper()


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _classify_type(raw_type: str) -> str:
    t = raw_type.upper()
    if "MATERIALIZED" in t:
        return "MATERIALIZED VIEW"
    if "VIEW" in t:
        return "VIEW"
    if "DYNAMIC" in t:
        return "TABLE"  # dynamic tables are tables
    return "TABLE"


# Keywords that appear after FROM/JOIN but aren't table names
_SQL_KEYWORDS = {
    "SELECT", "WHERE", "GROUP", "ORDER", "HAVING", "LIMIT", "UNION",
    "INTERSECT", "EXCEPT", "ALL", "DISTINCT", "AS", "ON", "AND", "OR",
    "NOT", "IN", "EXISTS", "BETWEEN", "LIKE", "CASE", "WHEN", "THEN",
    "ELSE", "END", "NULL", "TRUE", "FALSE", "LATERAL", "FLATTEN",
    "TABLE", "VALUES", "DUAL", "UNNEST",
}

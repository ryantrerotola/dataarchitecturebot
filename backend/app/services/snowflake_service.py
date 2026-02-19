import snowflake.connector
from contextlib import contextmanager

from app.config import settings
from app.models.schemas import SnowflakeObject, ColumnInfo


@contextmanager
def _get_connection():
    connect_params = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "role": settings.snowflake_role,
        "warehouse": settings.snowflake_warehouse,
    }
    if settings.snowflake_authenticator:
        connect_params["authenticator"] = settings.snowflake_authenticator
    else:
        connect_params["password"] = settings.snowflake_password

    conn = snowflake.connector.connect(**connect_params)
    try:
        yield conn
    finally:
        conn.close()


def list_objects() -> list[SnowflakeObject]:
    """Fetch all tables, views, and materialized views across accessible databases."""
    query = """
    SELECT
        TABLE_CATALOG AS database,
        TABLE_SCHEMA AS schema_name,
        TABLE_NAME AS name,
        TABLE_TYPE AS type,
        ROW_COUNT,
        BYTES,
        COMMENT
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
    WHERE DELETED IS NULL
      AND TABLE_SCHEMA != 'INFORMATION_SCHEMA'
      AND TABLE_CATALOG NOT IN ('SNOWFLAKE', 'SNOWFLAKE_SAMPLE_DATA')
    ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME
    """
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

    return [
        SnowflakeObject(
            database=r[0],
            schema_name=r[1],
            name=r[2],
            type=r[3],
            row_count=r[4],
            bytes=r[5],
            comment=r[6],
        )
        for r in rows
    ]


def get_columns(database: str, schema: str, table: str) -> list[ColumnInfo]:
    """Fetch column metadata for a specific table or view."""
    query = """
    SELECT
        COLUMN_NAME,
        DATA_TYPE,
        IS_NULLABLE,
        COMMENT,
        ORDINAL_POSITION
    FROM {database}.INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = %s
      AND TABLE_NAME = %s
    ORDER BY ORDINAL_POSITION
    """.format(database=database)

    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (schema, table))
        rows = cursor.fetchall()

    return [
        ColumnInfo(
            name=r[0],
            data_type=r[1],
            nullable=r[2] == "YES",
            comment=r[3],
            ordinal_position=r[4],
        )
        for r in rows
    ]

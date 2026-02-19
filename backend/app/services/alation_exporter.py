import csv
import io

from app.config import settings
from app.models.schemas import TableDocumentation


def export_to_alation(tables: list[TableDocumentation]) -> tuple[str, str]:
    """
    Generate Alation-compatible CSV content for bulk upload.

    Returns (table_csv, column_csv) as strings.
    The format follows Alation's Custom Field bulk upload specification:
    - Table key format: datasource_id.schema.table
    - Column key format: datasource_id.schema.table.column
    """
    ds_id = settings.alation_datasource_id

    # Table descriptions
    table_buf = io.StringIO()
    table_writer = csv.writer(table_buf)
    table_writer.writerow(["key", "title", "description"])
    for t in tables:
        key = f"{ds_id}.{t.database}.{t.schema_name}.{t.table_name}"
        table_writer.writerow([key, t.table_name, t.table_description])

    # Column descriptions
    col_buf = io.StringIO()
    col_writer = csv.writer(col_buf)
    col_writer.writerow(["key", "title", "description"])
    for t in tables:
        for col in t.columns:
            key = f"{ds_id}.{t.database}.{t.schema_name}.{t.table_name}.{col.name}"
            col_writer.writerow([key, col.name, col.description])

    return table_buf.getvalue(), col_buf.getvalue()


def export_combined(tables: list[TableDocumentation]) -> str:
    """
    Generate a single combined CSV with both table and column descriptions.
    Each row has: type, key, title, description
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["type", "key", "title", "description"])

    ds_id = settings.alation_datasource_id

    for t in tables:
        table_key = f"{ds_id}.{t.database}.{t.schema_name}.{t.table_name}"
        writer.writerow(["table", table_key, t.table_name, t.table_description])
        for col in t.columns:
            col_key = f"{ds_id}.{t.database}.{t.schema_name}.{t.table_name}.{col.name}"
            writer.writerow(["column", col_key, col.name, col.description])

    return buf.getvalue()

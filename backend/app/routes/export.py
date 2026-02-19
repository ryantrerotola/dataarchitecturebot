from fastapi import APIRouter
from fastapi.responses import Response

from app.models.schemas import ExportRequest
from app.services.alation_exporter import export_to_alation, export_combined

router = APIRouter()


@router.post("/alation")
def export_alation(req: ExportRequest):
    table_csv, column_csv = export_to_alation(req.tables)
    return {
        "tables": {"filename": "alation_tables.csv", "content": table_csv},
        "columns": {"filename": "alation_columns.csv", "content": column_csv},
    }


@router.post("/alation/combined")
def export_alation_combined(req: ExportRequest):
    content = export_combined(req.tables)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alation_upload.csv"},
    )

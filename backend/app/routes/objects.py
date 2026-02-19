from fastapi import APIRouter, HTTPException

from app.models.schemas import SnowflakeObject, ColumnInfo
from app.services import snowflake_service

router = APIRouter()


@router.get("/", response_model=list[SnowflakeObject])
def list_objects():
    try:
        return snowflake_service.list_objects()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{database}/{schema}/{table}/columns", response_model=list[ColumnInfo])
def get_columns(database: str, schema: str, table: str):
    try:
        return snowflake_service.get_columns(database, schema, table)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

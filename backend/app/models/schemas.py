from pydantic import BaseModel


class SnowflakeObject(BaseModel):
    database: str
    schema_name: str
    name: str
    type: str
    row_count: int | None = None
    bytes: int | None = None
    comment: str | None = None


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    comment: str | None = None
    ordinal_position: int = 0


class SummarizeRequest(BaseModel):
    object_name: str
    transcripts: dict[str, str]  # question_key -> transcript text


class ColumnSummarizeRequest(BaseModel):
    object_name: str
    column_name: str
    transcript: str


class SummaryResponse(BaseModel):
    summary: str


class TableDocumentation(BaseModel):
    database: str
    schema_name: str
    table_name: str
    table_description: str
    columns: list["ColumnDocumentation"]


class ColumnDocumentation(BaseModel):
    name: str
    description: str


class ExportRequest(BaseModel):
    tables: list[TableDocumentation]


class ExportResponse(BaseModel):
    filename: str
    content: str

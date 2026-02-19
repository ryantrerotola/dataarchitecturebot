from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    SummarizeRequest,
    ColumnSummarizeRequest,
    SummaryResponse,
)
from app.services import summarizer

router = APIRouter()


@router.post("/table", response_model=SummaryResponse)
def summarize_table(req: SummarizeRequest):
    try:
        summary = summarizer.summarize_table(req.object_name, req.transcripts)
        return SummaryResponse(summary=summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/column", response_model=SummaryResponse)
def summarize_column(req: ColumnSummarizeRequest):
    try:
        summary = summarizer.summarize_column(
            req.object_name, req.column_name, req.transcript
        )
        return SummaryResponse(summary=summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

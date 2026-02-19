from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import objects, summarize, export

app = FastAPI(title="Snowflake Metadata Documenter", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(objects.router, prefix="/api/objects", tags=["objects"])
app.include_router(summarize.router, prefix="/api/summarize", tags=["summarize"])
app.include_router(export.router, prefix="/api/export", tags=["export"])


@app.get("/api/health")
def health():
    return {"status": "ok"}

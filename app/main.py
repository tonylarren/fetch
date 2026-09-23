from fastapi import FastAPI

from app.api import health, jobs, ocr
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(
    title="CV OCR Service",
    version="0.1.0",
    description="Drive -> PaddleOCR -> clean JSON -> Drive.",
)

app.include_router(health.router)
app.include_router(ocr.router)
app.include_router(jobs.router)

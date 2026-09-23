from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_api_key
from app.schemas.ocr import JobStatus
from app.services.jobs import fetch

router = APIRouter(prefix="/v1", tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def job_status(job_id: str, _: str = Depends(require_api_key)):
    data = fetch(job_id)
    if not data:
        raise HTTPException(404, "Unknown job id.")
    return JobStatus(**data)

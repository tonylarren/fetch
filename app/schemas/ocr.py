from typing import Literal
from pydantic import BaseModel, Field


class DriveOCRRequest(BaseModel):
    file_id: str = Field(..., description="Google Drive file id of the CV")
    output_folder_id: str | None = Field(
        None, description="Defaults to DRIVE_OUTPUT_FOLDER_ID"
    )
    lang: str | None = None
    mode: Literal["text", "layout"] = "text"
    force: bool = Field(False, description="Reprocess even if a result already exists")


class ScanRequest(BaseModel):
    input_folder_id: str | None = None
    output_folder_id: str | None = None
    limit: int = 50
    force: bool = False


class JobAccepted(BaseModel):
    job_id: str
    status: str = "queued"


class JobStatus(BaseModel):
    job_id: str
    status: str
    result: dict | None = None
    error: str | None = None

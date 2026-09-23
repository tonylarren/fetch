from fastapi import APIRouter, Depends, File, HTTPException, Form, UploadFile

from app.core.config import settings
from app.core.security import require_api_key
from app.schemas.ocr import DriveOCRRequest, JobAccepted, ScanRequest
from app.services import clean, engine, extract
from app.services.jobs import enqueue
from app.tasks import scan_folder

router = APIRouter(prefix="/v1", tags=["ocr"])


@router.post("/ocr:drive", response_model=JobAccepted, status_code=202)
async def ocr_drive(req: DriveOCRRequest, _: str = Depends(require_api_key)):
    """Main ATS path. Returns immediately; the worker writes JSON back to Drive."""
    out = req.output_folder_id or settings.drive_output_folder_id
    if not out:
        raise HTTPException(400, "No output folder (set DRIVE_OUTPUT_FOLDER_ID).")
    job_id = enqueue("app.tasks.run_drive_ocr", {**req.model_dump(), "output_folder_id": out})
    return JobAccepted(job_id=job_id)


@router.post("/ocr:scan", status_code=200)
async def ocr_scan(req: ScanRequest, _: str = Depends(require_api_key)):
    """Sweep the input folder and enqueue everything unprocessed."""
    return scan_folder(req.model_dump())


@router.post("/ocr:file")
async def ocr_file(
    file: UploadFile = File(...),
    lang: str = Form(default=""),
    _: str = Depends(require_api_key),
):
    """Generic endpoint for other clients. Synchronous, no Drive involved.
    Keep uploads small here; anything heavy should use ocr:drive."""
    data = await file.read()
    try:
        prepared = extract.prepare(data, file.content_type or "", file.filename or "upload")
    except ValueError as e:
        raise HTTPException(415, str(e)) from e

    chosen = lang or settings.ocr_lang
    pages = []
    if prepared["kind"] == "text":
        for i, raw in enumerate(prepared["pages"], start=1):
            pages.append({"page": i, "text": clean.normalize_text(raw)})
    else:
        for i, image in enumerate(prepared["pages"], start=1):
            blocks = engine.run(image, chosen)
            blocks = clean.filter_blocks(blocks, settings.min_block_score)
            blocks = clean.order_blocks(blocks, float(image.shape[1]))
            pages.append({"page": i, "text": clean.blocks_to_text(blocks)})

    return {
        "meta": {
            "pages": prepared["page_count"],
            "text_layer": prepared["kind"] == "text",
            "lang": chosen,
        },
        "full_text": clean.normalize_text("\n\n".join(p["text"] for p in pages)),
        "pages": pages,
    }

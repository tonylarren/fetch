"""The whole pipeline: Drive -> extract/OCR -> clean -> Drive."""
import hashlib
import json
import logging
import time
from pathlib import Path

from app.core.config import settings
from app.services import clean, engine, extract
from app.services.drive import DriveClient

log = logging.getLogger(__name__)

PROCESSED_PROP = "ocrJsonId"
SOURCE_HASH_PROP = "ocrSourceHash"


def source_hash(file_id: str, modified_time: str) -> str:
    """Idempotency key. A retried call on an unchanged file is a no-op."""
    return hashlib.sha256(f"{file_id}:{modified_time}".encode()).hexdigest()[:16]


def _ocr_pages(prepared: dict, lang: str) -> tuple[list[dict], bool]:
    pages, used_ocr = [], False
    if prepared["kind"] == "text":
        for i, raw in enumerate(prepared["pages"], start=1):
            pages.append(
                {"page": i, "text": clean.normalize_text(raw), "blocks": []}
            )
        return pages, used_ocr

    used_ocr = True
    for i, image in enumerate(prepared["pages"], start=1):
        blocks = engine.run(image, lang)
        blocks = clean.filter_blocks(blocks, settings.min_block_score)
        blocks = clean.order_blocks(blocks, float(image.shape[1]))
        pages.append(
            {"page": i, "text": clean.blocks_to_text(blocks), "blocks": blocks}
        )
    return pages, used_ocr


def run_drive_ocr(payload: dict) -> dict:
    started = time.time()
    drive = DriveClient()

    file_id = payload["file_id"]
    lang = payload.get("lang") or settings.ocr_lang
    out_folder = payload.get("output_folder_id") or settings.drive_output_folder_id
    force = payload.get("force", False)

    meta = drive.metadata(file_id)
    filename = meta["name"]
    digest = source_hash(file_id, meta.get("modifiedTime", ""))
    stem = Path(filename).stem
    out_name = f"{stem}.json"

    if not force:
        existing = drive.find_by_name(out_folder, out_name)
        if existing and (existing.get("appProperties") or {}).get(SOURCE_HASH_PROP) == digest:
            log.info("skip unchanged file", extra={"file_id": file_id, "filename": filename})
            return {
                "status": "skipped",
                "reason": "already_processed",
                "output_file_id": existing["id"],
                "source": {"drive_file_id": file_id, "filename": filename},
            }

    data = drive.download(file_id)
    prepared = extract.prepare(data, meta.get("mimeType", ""), filename)
    pages, used_ocr = _ocr_pages(prepared, lang)

    full_text = clean.normalize_text("\n\n".join(p["text"] for p in pages))
    duration_ms = int((time.time() - started) * 1000)

    result = {
        "source": {
            "drive_file_id": file_id,
            "filename": filename,
            "mime_type": meta.get("mimeType"),
            "modified_time": meta.get("modifiedTime"),
            "source_hash": digest,
        },
        "meta": {
            "pages": prepared["page_count"],
            "pages_processed": len(pages),
            "text_layer": not used_ocr,
            "engine": "PP-OCR" if used_ocr else "native-text",
            "lang": lang,
            "duration_ms": duration_ms,
        },
        "full_text": full_text,
        "pages": pages,
    }

    props = {SOURCE_HASH_PROP: digest}

    # clean result (what downstream reads)
    slim = {**result, "pages": [{"page": p["page"], "text": p["text"]} for p in pages]}
    created = drive.upload_json(
        out_folder, out_name, json.dumps(slim, ensure_ascii=False, indent=2).encode(), props
    )

    # raw result with bboxes, for debugging
    if used_ocr:
        drive.upload_json(
            out_folder,
            f"{stem}.raw.json",
            json.dumps(result, ensure_ascii=False).encode(),
            props,
        )

    drive.mark_source(file_id, {PROCESSED_PROP: created["id"], SOURCE_HASH_PROP: digest})

    log.info(
        "ocr done",
        extra={"file_id": file_id, "filename": filename,
               "duration_ms": duration_ms, "pages": len(pages)},
    )
    return {
        "status": "completed",
        "output_file_id": created["id"],
        "output_name": created["name"],
        "web_view_link": created.get("webViewLink"),
        "meta": result["meta"],
        "source": result["source"],
    }


SUPPORTED = [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]


def scan_folder(payload: dict) -> dict:
    """Walk the input folder and enqueue anything not yet processed."""
    from app.services.jobs import enqueue

    drive = DriveClient()
    in_folder = payload.get("input_folder_id") or settings.drive_input_folder_id
    out_folder = payload.get("output_folder_id") or settings.drive_output_folder_id
    force = payload.get("force", False)
    limit = payload.get("limit", 50)

    files = drive.list_folder(in_folder, SUPPORTED)[:limit]
    queued, skipped = [], 0
    for f in files:
        digest = source_hash(f["id"], f.get("modifiedTime", ""))
        if not force:
            existing = drive.find_by_name(out_folder, f"{Path(f['name']).stem}.json")
            if existing and (existing.get("appProperties") or {}).get(SOURCE_HASH_PROP) == digest:
                skipped += 1
                continue
        job_id = enqueue(
            "app.tasks.run_drive_ocr",
            {"file_id": f["id"], "output_folder_id": out_folder, "force": force},
            job_id=f"ocr-{digest}",
        )
        queued.append({"file_id": f["id"], "name": f["name"], "job_id": job_id})
    return {"scanned": len(files), "queued": len(queued), "skipped": skipped, "jobs": queued}

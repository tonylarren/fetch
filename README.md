# CV OCR Service

Self-contained microservice: pulls a CV from Google Drive, extracts the text
(native text layer when available, PaddleOCR when not), cleans it, and writes a
JSON result back to Drive.

```
Drive input folder  ──▶  FastAPI  ──▶  Redis/RQ  ──▶  worker (PaddleOCR)
                                                          │
                          Drive output folder  ◀──────────┘
```

Nothing else is required in the loop. With `POLL_ENABLED=true` the service
watches the input folder itself, so n8n only has to drop a file in Drive and
pick the JSON up later.

---

## Setup

### 1. Google Cloud

1. Create a project, enable the **Google Drive API**.
2. Create a **service account**, then create a JSON key for it.
3. Save the key as `secrets/service-account.json`.
4. In your **Shared Drive**, create two folders (e.g. `CV/incoming` and
   `CV/parsed`) and add the service account email as **Content Manager**.
   Adding it at the Shared Drive level is easiest.
5. Copy both folder IDs from their URLs (`/drive/folders/<ID>`).

> The folders must live in a **Shared Drive**, not a personal My Drive.
> Service accounts have zero My Drive storage quota, so uploads into a shared
> personal folder can fail with `storageQuotaExceeded`. `scripts/check_drive.py`
> tells you which case you're in.

### 2. Configure

```bash
cp .env.example .env
$EDITOR .env          # API_KEYS, DRIVE_INPUT_FOLDER_ID, DRIVE_OUTPUT_FOLDER_ID
```

Generate a key: `openssl rand -hex 24`

### 3. Build and preflight

```bash
docker compose build
docker compose run --rm api python scripts/check_drive.py
```

Do not skip the preflight. It verifies read access, write access, and Shared
Drive placement in about five seconds, which is where most of the day-one
failures are.

### 4. Run

```bash
docker compose up -d
docker compose logs -f worker
```

### 5. Expose it

Copy `docker/nginx.conf.example` to `/etc/nginx/sites-available/`, symlink it
into `sites-enabled`, then:

```bash
certbot --nginx -d ocr.tonylarren.com
ufw allow 22 && ufw allow 443 && ufw default deny incoming && ufw enable
```

The API only binds to `127.0.0.1:8080`, and Redis is not published at all.

---

## API

All endpoints require `X-API-Key`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/ocr:drive` | Queue one Drive file. Returns `202 {job_id}`. |
| `POST` | `/v1/ocr:scan` | Sweep the input folder, queue everything new. |
| `POST` | `/v1/ocr:file` | Multipart upload, synchronous. For other clients. |
| `GET` | `/v1/jobs/{job_id}` | Job status and result. |
| `GET` | `/healthz` `/readyz` | Liveness / dependency checks. |

```bash
curl -X POST https://ocr.tonylarren.com/v1/ocr:drive \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"file_id":"1AbC...","lang":"fr"}'
# {"job_id":"...","status":"queued"}
```

Interactive docs at `/docs`.

## Output

Two files per CV in the output folder:

- `{name}.json` — clean text, one entry per page plus `full_text`. This is what
  downstream reads.
- `{name}.raw.json` — same plus every OCR block with bbox and confidence.
  Written only when OCR actually ran. Useful when a result looks wrong.

```json
{
  "source": { "drive_file_id": "...", "filename": "cv.pdf", "source_hash": "a1b2..." },
  "meta": { "pages": 2, "text_layer": false, "engine": "PP-OCR", "duration_ms": 8400 },
  "full_text": "...",
  "pages": [{ "page": 1, "text": "..." }]
}
```

No `name` / `email` / `skills` fields, deliberately. Field extraction is a
separate concern: if it lived here, every prompt change would be a redeploy and
you could not reprocess stored OCR output without re-OCRing the PDF.

## Design notes

**Async everywhere.** OCR takes 5 to 60 seconds. The HTTP call returns a
`job_id` immediately so no caller ever sits on an open connection waiting for a
gateway timeout.

**Model loaded once.** `get_engine()` is `lru_cache`d and warmed at worker
startup. Instantiating `PaddleOCR()` per request costs several seconds and a lot
of RAM.

**Text layer first.** Most emailed CVs are digital PDFs. `extract.prepare()`
checks with PyMuPDF and skips OCR entirely when there is real text, which is
both faster and more accurate. DOCX is handled natively too.

**Idempotent.** The key is `sha256(file_id + modifiedTime)`, stored in the
result's `appProperties`. A retried call on an unchanged file is a no-op unless
you pass `"force": true`.

**Reading order.** `clean.order_blocks()` detects a two-column layout and sorts
column by column. Without it, two-column CVs interleave into nonsense.

## Tuning

| Setting | Effect |
|---|---|
| `OCR_DPI` | 220 is a good default. 300 for small print, slower. |
| `MIN_BLOCK_SCORE` | Raise to 0.7 to drop more OCR noise. |
| `MIN_TEXT_CHARS` | Threshold for "this PDF has a real text layer". |
| `OMP_NUM_THREADS` | In the Dockerfile. Paddle grabs every core otherwise. |
| `worker.replicas` | Budget ~2-3 GB RAM each. Measure before raising. |

## Before scaling

Run 10 real CVs through it and check the logs for `duration_ms`. If image-based
CVs are slow on this hardware, consider routing only those to a hosted VLM and
keeping PaddleOCR for the bulk.

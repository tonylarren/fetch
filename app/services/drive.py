"""Google Drive adapter. Shared Drive aware.

Every call passes supportsAllDrives / includeItemsFromAllDrives, which is what
makes this work against an enterprise Shared Drive instead of a personal My Drive.
"""
import io
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaInMemoryUpload

from app.core.config import settings

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
SHARED = {"supportsAllDrives": True}
SHARED_LIST = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}


def _service():
    creds = service_account.Credentials.from_service_account_file(
        settings.google_credentials_file, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class DriveClient:
    def __init__(self):
        self.svc = _service()

    # --- read ---

    def metadata(self, file_id: str) -> dict:
        return (
            self.svc.files()
            .get(
                fileId=file_id,
                fields="id,name,mimeType,size,modifiedTime,driveId,parents",
                **SHARED,
            )
            .execute()
        )

    def download(self, file_id: str) -> bytes:
        buf = io.BytesIO()
        req = self.svc.files().get_media(fileId=file_id, **SHARED)
        downloader = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()

    def list_folder(self, folder_id: str, mime_types: list[str] | None = None) -> list[dict]:
        q = [f"'{folder_id}' in parents", "trashed = false"]
        if mime_types:
            ors = " or ".join(f"mimeType = '{m}'" for m in mime_types)
            q.append(f"({ors})")
        params = dict(
            q=" and ".join(q),
            fields="files(id,name,mimeType,size,modifiedTime),nextPageToken",
            pageSize=200,
            **SHARED_LIST,
        )
        if settings.drive_shared_drive_id:
            params.update(corpora="drive", driveId=settings.drive_shared_drive_id)
        out, token = [], None
        while True:
            if token:
                params["pageToken"] = token
            resp = self.svc.files().list(**params).execute()
            out.extend(resp.get("files", []))
            token = resp.get("nextPageToken")
            if not token:
                return out

    def find_by_name(self, folder_id: str, name: str) -> dict | None:
        safe = name.replace("'", "\\'")
        params = dict(
            q=f"'{folder_id}' in parents and name = '{safe}' and trashed = false",
            fields="files(id,name,modifiedTime,appProperties)",
            pageSize=1,
            **SHARED_LIST,
        )
        if settings.drive_shared_drive_id:
            params.update(corpora="drive", driveId=settings.drive_shared_drive_id)
        files = self.svc.files().list(**params).execute().get("files", [])
        return files[0] if files else None

    # --- write ---

    def upload_json(
        self, folder_id: str, name: str, data: bytes, app_properties: dict | None = None
    ) -> dict:
        """Create or overwrite a JSON file in the target folder."""
        existing = self.find_by_name(folder_id, name)
        media = MediaInMemoryUpload(data, mimetype="application/json", resumable=False)
        if existing:
            body = {"appProperties": app_properties or {}}
            return (
                self.svc.files()
                .update(fileId=existing["id"], body=body, media_body=media,
                        fields="id,name,webViewLink", **SHARED)
                .execute()
            )
        body = {
            "name": name,
            "parents": [folder_id],
            "mimeType": "application/json",
            "appProperties": app_properties or {},
        }
        return (
            self.svc.files()
            .create(body=body, media_body=media, fields="id,name,webViewLink", **SHARED)
            .execute()
        )

    def mark_source(self, file_id: str, props: dict) -> None:
        """Stamp the source CV with appProperties so polling can skip it next time.
        Silently ignored if the service account only has read access."""
        try:
            self.svc.files().update(
                fileId=file_id, body={"appProperties": props}, fields="id", **SHARED
            ).execute()
        except HttpError as e:
            log.warning("could not stamp source file %s: %s", file_id, e)

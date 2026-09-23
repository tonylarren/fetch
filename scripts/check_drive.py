"""Preflight: run this BEFORE anything else.

Confirms the service account can actually read the input folder and WRITE to the
output folder, and tells you whether those folders live in a real Shared Drive
(fine) or in someone's My Drive (will hit storageQuotaExceeded on upload).

    docker compose run --rm api python scripts/check_drive.py
"""
import json
import sys

from app.core.config import settings
from app.services.drive import DriveClient, SHARED


def describe(drive, folder_id: str, label: str) -> dict | None:
    if not folder_id:
        print(f"[!] {label}: not set in .env")
        return None
    try:
        info = (
            drive.svc.files()
            .get(
                fileId=folder_id,
                fields="id,name,mimeType,driveId,capabilities(canAddChildren,canEdit)",
                **SHARED,
            )
            .execute()
        )
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {label}: cannot read folder {folder_id}\n       {e}")
        return None

    in_shared_drive = bool(info.get("driveId"))
    caps = info.get("capabilities", {})
    print(f"[ok] {label}: {info['name']} ({folder_id})")
    print(f"     shared drive : {'YES' if in_shared_drive else 'NO  <-- quota risk'}")
    print(f"     canAddChildren: {caps.get('canAddChildren')}")
    if not in_shared_drive:
        print("     ! This folder is in a My Drive. The service account has no storage")
        print("       quota there and uploads may fail with storageQuotaExceeded.")
        print("       Move it into a Shared Drive and add the SA as Content Manager.")
    return info


def main() -> int:
    with open(settings.google_credentials_file) as f:
        sa_email = json.load(f).get("client_email")
    print(f"service account: {sa_email}\n")

    drive = DriveClient()
    inp = describe(drive, settings.drive_input_folder_id, "input folder")
    out = describe(drive, settings.drive_output_folder_id, "output folder")

    if out and out.get("capabilities", {}).get("canAddChildren"):
        print("\n[test] writing a probe file to the output folder...")
        created = drive.upload_json(
            settings.drive_output_folder_id,
            "_ocr_probe.json",
            b'{"probe": true}',
        )
        print(f"[ok] wrote {created['name']} -> {created['id']}")
        drive.svc.files().delete(fileId=created["id"], **SHARED).execute()
        print("[ok] probe deleted. Write access confirmed.")
    else:
        print("\n[FAIL] no write access to the output folder.")
        return 1

    if inp:
        files = drive.list_folder(settings.drive_input_folder_id)
        print(f"\n[ok] input folder contains {len(files)} file(s)")
        for f in files[:5]:
            print(f"     - {f['name']} ({f['mimeType']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

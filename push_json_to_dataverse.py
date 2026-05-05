#!/usr/bin/env python3
"""Push updated dataset JSONs to Dataverse for file-level metadata changes."""

import argparse
import json
import sys
from pathlib import Path

try:
    from pyDataverse.api import NativeApi
    import httpx
except ImportError as exc:
    raise SystemExit(
        "pyDataverse is required. Install it with `python3 -m pip install pyDataverse`."
    ) from exc


def parse_bool(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def ensure_dir(path: Path):
    if not path.exists():
        raise SystemExit(f"JSON directory not found: {path}")
    if not path.is_dir():
        raise SystemExit(f"JSON path is not a directory: {path}")


def build_files_api_url(native_api, path: str):
    return f"{native_api.base_url}/api{path}"


def push_restrict(native_api, file_id, restricted, use_pid=False):
    if restricted:
        if use_pid:
            url = build_files_api_url(native_api, f"/files/:persistentId/restrict?persistentId={file_id}")
        else:
            url = build_files_api_url(native_api, f"/files/{file_id}/restrict")
    else:
        if use_pid:
            url = build_files_api_url(native_api, f"/files/:persistentId/unrestrict?persistentId={file_id}")
        else:
            url = build_files_api_url(native_api, f"/files/{file_id}/unrestrict")
    return native_api.put_request(url, auth=True)


def update_file_access_request(native_api, file_id, new_value, use_pid=False):
    if use_pid:
        url = build_files_api_url(native_api, f"/files/:persistentId/metadata?persistentId={file_id}")
    else:
        url = build_files_api_url(native_api, f"/files/{file_id}/metadata")

    # Dataverse API requires multipart form-data with jsonData field
    # Use httpx directly to send proper multipart encoding
    files = {"jsonData": (None, json.dumps({"fileAccessRequest": new_value}))}
    headers = {}
    
    # Get API token from native_api if available
    if hasattr(native_api, 'api_token') and native_api.api_token:
        headers["X-Dataverse-key"] = native_api.api_token
    
    response = httpx.post(url, files=files, headers=headers)
    return response


def get_response_status(response):
    if response is None:
        return None
    return getattr(response, "status_code", getattr(response, "returncode", None))


def get_response_text(response):
    if response is None:
        return None
    if hasattr(response, "text"):
        return response.text
    return getattr(response, "stdout", None)


def push_dataset_json(native_api, json_path, dry_run=False):
    with json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        print(f"Skipping invalid JSON: {json_path}")
        return 0, 0

    doi = data.get("persistentId") or data.get("identifier")
    if not doi:
        print(f"Skipping JSON without persistentId: {json_path}")
        return 0, 0

    changed_count = 0
    error_count = 0
    for file_record in data.get("files", []):
        file_item = file_record.get("dataFile", {})
        if not file_item:
            continue

        file_id = file_item.get("id") or file_item.get("persistentId")
        if not file_id:
            continue

        use_pid = isinstance(file_id, str) and not file_id.isdigit()
        restricted_val = parse_bool(file_record.get("restricted"))
        access_val = parse_bool(file_item.get("fileAccessRequest"))

        if restricted_val is None and access_val is None:
            continue

        if dry_run:
            print(f"DRY RUN: would update file {file_id} in {doi}: restricted={restricted_val}, fileAccessRequest={access_val}")
            changed_count += 1
            continue

        if restricted_val is not None:
            try:
                response = push_restrict(native_api, file_id, restricted_val, use_pid=use_pid)
                status_code = get_response_status(response)
                response_text = get_response_text(response)
                
                if status_code not in (200, 201, 204):
                    # Check if file is already in desired state (these are not real errors)
                    if status_code == 400 and ("already unrestricted" in str(response_text) or "already restricted" in str(response_text)):
                        print(f"File {file_id} already {('unrestricted' if not restricted_val else 'restricted')} (no change needed)")
                        changed_count += 1
                    else:
                        print(f"Failed restrict update for file {file_id}: {status_code} {response_text}")
                        error_count += 1
                else:
                    print(f"Updated restricted for file {file_id} to {restricted_val}")
                    changed_count += 1
            except Exception as exc:
                print(f"Error updating restricted for file {file_id}: {exc}")
                error_count += 1

        if access_val is not None:
            try:
                response = update_file_access_request(native_api, file_id, access_val, use_pid=use_pid)
                status_code = get_response_status(response)
                if status_code not in (200, 201, 204):
                    print(f"Failed fileAccessRequest update for file {file_id}: {status_code} {get_response_text(response)}")
                    error_count += 1
                else:
                    print(f"Updated fileAccessRequest for file {file_id} to {access_val}")
                    changed_count += 1
            except Exception as exc:
                print(f"Error updating fileAccessRequest for file {file_id}: {exc}")
                error_count += 1

    return changed_count, error_count


def parse_args():
    parser = argparse.ArgumentParser(
        description="Push updated dataset JSON files to Dataverse file metadata endpoints."
    )
    parser.add_argument(
        "--server-url",
        help="Base Dataverse/Borealis server URL."
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication."
    )
    parser.add_argument(
        "--json-dir",
        default="dataset_jsons",
        help="Directory containing updated dataset JSON files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be pushed without making changes."
    )
    return parser.parse_args()


def prompt_for_missing_args(args):
    if not args.server_url:
        args.server_url = input("Server URL: ").strip()
    if not args.api_key:
        args.api_key = input("API key: ").strip()
    return args


def main():
    args = prompt_for_missing_args(parse_args())
    json_dir = Path(args.json_dir)
    ensure_dir(json_dir)

    native_api = NativeApi(args.server_url, api_token=args.api_key)

    total_changed = 0
    total_errors = 0
    file_count = 0
    for json_path in sorted(json_dir.glob("*.json")):
        file_count += 1
        print(f"Processing {json_path}")
        changed, errors = push_dataset_json(native_api, json_path, dry_run=args.dry_run)
        total_changed += changed
        total_errors += errors

    print(f"Processed {file_count} JSON files")
    print(f"Total changes applied: {total_changed}")
    if total_errors:
        print(f"Total errors: {total_errors}")


if __name__ == "__main__":
    main()

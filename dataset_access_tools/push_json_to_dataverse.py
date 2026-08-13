#!/usr/bin/env python3
"""Push updated dataset JSONs to Dataverse for file-level metadata changes."""

import argparse
import json
import sys
from pathlib import Path

try:
    from .dataverse_json import (
        DatasetValidationError,
        get_file_records,
        get_persistent_id,
        parse_optional_bool,
        validate_dataset,
    )
    from .security_utils import (
        DataverseRequestError,
        confirm_apply,
        get_api_token,
        get_config_value,
        load_config,
        post_file_access_request,
        response_error_summary,
        validate_server_url,
    )
except ImportError:  # Support direct execution
    from dataverse_json import (
        DatasetValidationError,
        get_file_records,
        get_persistent_id,
        parse_optional_bool,
        validate_dataset,
    )
    from security_utils import (
        DataverseRequestError,
        confirm_apply,
        get_api_token,
        get_config_value,
        load_config,
        post_file_access_request,
        response_error_summary,
        validate_server_url,
    )

try:
    from pyDataverse.api import NativeApi
except ImportError:
    NativeApi = None


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

    return post_file_access_request(
        url,
        getattr(native_api, "api_token", None),
        new_value,
    )


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

    validate_dataset(data)
    doi = get_persistent_id(data)
    file_records, _ = get_file_records(data)

    changed_count = 0
    error_count = 0
    for file_record in file_records:
        file_item = file_record.get("dataFile", {})
        if not file_item:
            continue

        file_id = file_item.get("id") or file_item.get("persistentId")
        if not file_id:
            continue

        use_pid = isinstance(file_id, str) and not file_id.isdigit()
        restricted_val = parse_optional_bool(file_record.get("restricted"))
        access_val = parse_optional_bool(file_item.get("fileAccessRequest"))

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
                    print(
                        f"Failed fileAccessRequest update for file {file_id}: "
                        f"{response_error_summary(response)}"
                    )
                    error_count += 1
                else:
                    print(f"Updated fileAccessRequest for file {file_id} to {access_val}")
                    changed_count += 1
            except DataverseRequestError as exc:
                print(f"Error updating fileAccessRequest for file {file_id}: {exc}")
                error_count += 1

    return changed_count, error_count


def parse_args():
    parser = argparse.ArgumentParser(
        description="Push updated dataset JSON files to Dataverse file metadata endpoints."
    )
    parser.add_argument(
        "--config",
        default="config.ini",
        help="INI configuration file (default: config.ini).",
    )
    parser.add_argument(
        "--server-url",
        help="Base Dataverse/Borealis server URL."
    )
    parser.add_argument(
        "--api-key",
        help="API token (discouraged: prefer config.ini or the hidden prompt)."
    )
    parser.add_argument(
        "--json-dir",
        default=None,
        help="Directory containing updated dataset JSON files."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, the command runs in preview mode.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly select preview mode (this is the default).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the APPLY prompt for automation; valid only with --apply.",
    )
    return parser.parse_args()


def prompt_for_missing_args(args):
    config = load_config(args.config)
    args.server_url = args.server_url or get_config_value(config, "dataverse", "server_url")
    args.json_dir = args.json_dir or get_config_value(config, "files", "json_dir", "dataset_jsons")
    if not args.server_url:
        args.server_url = input("Server URL: ").strip()
    args.api_key = get_api_token(
        args.api_key,
        get_config_value(config, "dataverse", "api_token"),
    )
    return args


def main():
    args = prompt_for_missing_args(parse_args())
    args.server_url = validate_server_url(args.server_url, args.api_key)
    if args.yes and not args.apply:
        print("--yes is valid only with --apply.", file=sys.stderr)
        return 2
    if NativeApi is None:
        print("pyDataverse is required. Install dependencies with `python3 -m pip install -r requirements.txt`.", file=sys.stderr)
        return 1
    json_dir = Path(args.json_dir)
    ensure_dir(json_dir)

    json_paths = sorted(json_dir.glob("*.json"))
    if not json_paths:
        print("No JSON files found; nothing was processed.", file=sys.stderr)
        return 1

    dry_run = not args.apply
    print(f"Mode: {'PREVIEW (no changes)' if dry_run else 'APPLY'}")
    print(f"Target server: {args.server_url}")
    print(f"JSON files: {len(json_paths)}")
    if args.apply and not confirm_apply(args.server_url, len(json_paths), assume_yes=args.yes):
        print("Apply cancelled; no changes were made.")
        return 1

    native_api = NativeApi(args.server_url, api_token=args.api_key)

    total_changed = 0
    total_errors = 0
    file_count = 0
    for json_path in json_paths:
        file_count += 1
        print(f"Processing {json_path}")
        try:
            changed, errors = push_dataset_json(native_api, json_path, dry_run=dry_run)
        except (DatasetValidationError, json.JSONDecodeError, OSError) as exc:
            print(f"Error processing {json_path}: {exc}", file=sys.stderr)
            total_errors += 1
            continue
        total_changed += changed
        total_errors += errors

    print(f"Processed {file_count} JSON files")
    print(f"Total changes applied: {total_changed}")
    if total_errors:
        print(f"Total errors: {total_errors}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

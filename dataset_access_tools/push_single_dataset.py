#!/usr/bin/env python3
"""Push a single dataset JSON file to Dataverse for file-level metadata changes."""

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
        put_file_restriction,
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
        put_file_restriction,
        response_error_summary,
        validate_server_url,
    )

try:
    from pyDataverse.api import NativeApi
except ImportError:
    NativeApi = None


def build_files_api_url(native_api, path: str):
    return f"{native_api.base_url}/api{path}"


def push_restrict(native_api, file_id, restricted, access_val=None, use_pid=False):
    if use_pid:
        url = build_files_api_url(
            native_api,
            f"/files/:persistentId/restrict?persistentId={file_id}",
        )
    else:
        url = build_files_api_url(native_api, f"/files/{file_id}/restrict")
    return put_file_restriction(
        url,
        getattr(native_api, "api_token", None),
        restricted,
    )


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
    """Push a single dataset JSON file to Dataverse."""
    print(f"Loading JSON file: {json_path}")

    with json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    validate_dataset(data)
    doi = get_persistent_id(data)

    print(f"Pushing dataset: {doi}")

    changed_count = 0
    error_count = 0
    file_count = 0

    # Handle different JSON structures: files at top level or in datasetVersion
    files_array, _ = get_file_records(data)
    
    for file_record in files_array:
        file_item = file_record.get("dataFile", {})
        if not file_item:
            continue

        file_id = file_item.get("id") or file_item.get("persistentId")
        if not file_id:
            continue

        file_count += 1
        file_name = file_item.get("filename", "unknown")
        print(f"Processing file {file_id} ({file_name})")

        use_pid = isinstance(file_id, str) and not file_id.isdigit()
        restricted_val = parse_optional_bool(file_record.get("restricted"))
        access_val = parse_optional_bool(file_item.get("fileAccessRequest"))

        if restricted_val is None and access_val is None:
            print("  Skipping - no changes needed")
            continue

        if dry_run:
            print(f"  🔍 DRY RUN: would update restricted={restricted_val}, fileAccessRequest={access_val}")
            changed_count += 1
            continue

        # Update restricted status
        if restricted_val is not None:
            try:
                response = push_restrict(native_api, file_id, restricted_val, access_val=access_val, use_pid=use_pid)
                status_code = get_response_status(response)
                response_text = get_response_text(response)

                if status_code not in (200, 201, 204):
                    # Check if file is already in desired state
                    if status_code == 400 and ("already unrestricted" in str(response_text) or "already restricted" in str(response_text)):
                        print(f"  ✓ Already {'restricted' if restricted_val else 'unrestricted'}")
                        # Still update fileAccessRequest if needed
                        if access_val is not None:
                            try:
                                response2 = update_file_access_request(native_api, file_id, access_val, use_pid=use_pid)
                                status_code2 = get_response_status(response2)
                                if status_code2 not in (200, 201, 204):
                                    print(f"  ✗ Failed fileAccessRequest update: {status_code2}")
                                    print(f"     {response_error_summary(response2)}")
                                    error_count += 1
                                else:
                                    print(f"  ✓ Updated fileAccessRequest to {access_val}")
                                    changed_count += 1
                            except DataverseRequestError as exc:
                                print(f"  ✗ Error updating fileAccessRequest: {exc}")
                                error_count += 1
                        changed_count += 1
                    else:
                        print(f"  ✗ Failed restrict update: {status_code} {response_text}")
                        error_count += 1
                else:
                    print(f"  ✓ Updated restricted to {restricted_val}")
                    if access_val is not None:
                        print(f"  ✓ Updated fileAccessRequest to {access_val}")
                    changed_count += 1
            except Exception as exc:
                print(f"  ✗ Error updating restricted: {exc}")
                error_count += 1

        # Update file access request (only if restricted not updated)
        elif access_val is not None:
            try:
                response = update_file_access_request(native_api, file_id, access_val, use_pid=use_pid)
                status_code = get_response_status(response)
                if status_code not in (200, 201, 204):
                    print(f"  ✗ Failed fileAccessRequest update: {response_error_summary(response)}")
                    error_count += 1
                else:
                    print(f"  ✓ Updated fileAccessRequest to {access_val}")
                    changed_count += 1
            except DataverseRequestError as exc:
                print(f"  ✗ Error updating fileAccessRequest: {exc}")
                error_count += 1

    return changed_count, error_count, file_count


def prompt_for_input(prompt, default=None):
    """Prompt user for input with optional default."""
    if default:
        response = input(f"{prompt} (default: {default}): ").strip()
        return response if response else default
    else:
        while True:
            response = input(f"{prompt}: ").strip()
            if response:
                return response
            print("This field is required. Please enter a value.")


def main():
    parser = argparse.ArgumentParser(
        description="Push a single dataset JSON file to Dataverse."
    )
    parser.add_argument(
        "--config",
        default="config.ini",
        help="INI configuration file (default: config.ini).",
    )
    parser.add_argument(
        "--server-url",
        help="Dataverse server URL."
    )
    parser.add_argument(
        "--api-key",
        help="API token (discouraged: prefer config.ini or the hidden prompt)."
    )
    parser.add_argument(
        "--json-path",
        help="Path to the JSON file to push."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, the command runs in preview mode."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the APPLY prompt for automation; valid only with --apply.",
    )
    args = parser.parse_args()
    if args.yes and not args.apply:
        parser.error("--yes is valid only with --apply")

    print("=== Single Dataset JSON Push to Dataverse ===\n")

    config = load_config(args.config)
    # Command-line values override config.ini; prompts fill any missing values.
    server_url = args.server_url or get_config_value(config, "dataverse", "server_url")
    server_url = server_url or prompt_for_input("Server URL", "https://demo.borealisdata.ca")
    api_key = get_api_token(
        args.api_key,
        get_config_value(config, "dataverse", "api_token"),
    )
    json_path_str = args.json_path or get_config_value(config, "files", "json_path")
    json_path_str = json_path_str or prompt_for_input("JSON file path")
    server_url = validate_server_url(server_url, api_key)
    if NativeApi is None:
        print("pyDataverse is required. Install dependencies with `python3 -m pip install -r requirements.txt`.", file=sys.stderr)
        return 1

    json_path = Path(json_path_str)
    if not json_path.exists():
        raise SystemExit(f"JSON file not found: {json_path}")
    if not json_path.is_file():
        raise SystemExit(f"Path is not a file: {json_path}")

    # Initialize API client
    print(f"\nConnecting to {server_url}...")
    print(f"Mode: {'APPLY' if args.apply else 'PREVIEW (no changes)'}")
    if args.apply and not confirm_apply(server_url, 1, assume_yes=args.yes):
        print("Apply cancelled; no changes were made.")
        return 1
    native_api = NativeApi(server_url, api_token=api_key)

    # Push the dataset
    try:
        changed, errors, files = push_dataset_json(native_api, json_path, dry_run=not args.apply)

        print("\n=== Results ===")
        print(f"Files processed: {files}")
        print(f"Changes applied: {changed}")
        if errors:
            print(f"Errors: {errors}")

        if not args.apply:
            print("🔍 DRY RUN - No actual changes made")
        elif errors == 0:
            print("✅ All updates completed successfully!")
        else:
            print("⚠️  Some updates failed. Check the output above for details.")
            return 1

    except (DatasetValidationError, json.JSONDecodeError, OSError, DataverseRequestError) as exc:
        print(f"❌ Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

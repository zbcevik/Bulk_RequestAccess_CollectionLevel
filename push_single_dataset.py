#!/usr/bin/env python3
"""Push a single dataset JSON file to Dataverse for file-level metadata changes."""

import argparse
import json
import sys
from pathlib import Path

try:
    from pyDataverse.api import NativeApi
    import httpx
except ImportError as exc:
    raise SystemExit(
        "Required packages not found. Install with: python3 -m pip install pyDataverse httpx"
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


def build_files_api_url(native_api, path: str):
    return f"{native_api.base_url}/api{path}"


def push_restrict(native_api, file_id, restricted, access_val=None, use_pid=False):
    url = build_files_api_url(native_api, f"/files/{file_id}/restrict")
    if use_pid:
        url = build_files_api_url(native_api, f"/files/:persistentId/restrict?persistentId={file_id}")
    
    data = {"restrict": restricted}
    if access_val is not None:
        data["fileAccessRequest"] = access_val
    return native_api.put_request(url, data=data, auth=True)


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

    response = httpx.post(url, files=files, headers=headers, follow_redirects=True)
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
    """Push a single dataset JSON file to Dataverse."""
    print(f"Loading JSON file: {json_path}")

    with json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise SystemExit(f"Invalid JSON file: {json_path}")

    doi = data.get("persistentId") or data.get("identifier")
    if not doi:
        raise SystemExit(f"JSON file missing persistentId or identifier: {json_path}")

    print(f"Pushing dataset: {doi}")

    changed_count = 0
    error_count = 0
    file_count = 0

    # Handle different JSON structures: files at top level or in datasetVersion
    files_array = data.get("files") or data.get("datasetVersion", {}).get("files", [])
    
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
        restricted_val = parse_bool(file_record.get("restricted"))
        access_val = parse_bool(file_item.get("fileAccessRequest"))

        if restricted_val is None and access_val is None:
            print(f"  Skipping - no changes needed")
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
                                    response_text2 = get_response_text(response2)
                                    print(f"  ✗ Failed fileAccessRequest update: {status_code2}")
                                    if response_text2:
                                        print(f"     Response: {response_text2[:200]}...")
                                    error_count += 1
                                else:
                                    print(f"  ✓ Updated fileAccessRequest to {access_val}")
                                    changed_count += 1
                            except Exception as exc:
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
                    # Print more details about the error
                    response_text = get_response_text(response)
                    print(f"  ✗ Failed fileAccessRequest update: {status_code}")
                    if hasattr(response, 'headers') and 'location' in response.headers:
                        print(f"     Redirect location: {response.headers['location']}")
                    if response_text:
                        print(f"     Response: {response_text[:200]}...")
                    error_count += 1
                else:
                    print(f"  ✓ Updated fileAccessRequest to {access_val}")
                    changed_count += 1
            except Exception as exc:
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
        "--server-url",
        help="Dataverse server URL."
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication."
    )
    parser.add_argument(
        "--json-path",
        help="Path to the JSON file to push."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be pushed without making changes."
    )
    args = parser.parse_args()

    print("=== Single Dataset JSON Push to Dataverse ===\n")

    # Get inputs from arguments or prompts
    server_url = args.server_url or prompt_for_input("Server URL", "https://demo.borealisdata.ca")
    api_key = args.api_key or prompt_for_input("API Key")
    json_path_str = args.json_path or prompt_for_input("JSON file path")

    json_path = Path(json_path_str)
    if not json_path.exists():
        raise SystemExit(f"JSON file not found: {json_path}")
    if not json_path.is_file():
        raise SystemExit(f"Path is not a file: {json_path}")

    # Initialize API client
    print(f"\nConnecting to {server_url}...")
    native_api = NativeApi(server_url, api_token=api_key)

    # Push the dataset
    try:
        changed, errors, files = push_dataset_json(native_api, json_path, dry_run=args.dry_run)

        print("\n=== Results ===")
        print(f"Files processed: {files}")
        print(f"Changes applied: {changed}")
        if errors:
            print(f"Errors: {errors}")

        if args.dry_run:
            print("🔍 DRY RUN - No actual changes made")
        elif errors == 0:
            print("✅ All updates completed successfully!")
        else:
            print("⚠️  Some updates failed. Check the output above for details.")

    except Exception as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
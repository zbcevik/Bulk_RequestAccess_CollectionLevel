#!/usr/bin/env python3
"""Push only explicit CSV access changes, validated against dataset JSON exports."""

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    from .dataverse_json import (
        DatasetValidationError,
        find_file_record,
        get_file_records,
        get_persistent_id,
        get_version_block,
        parse_optional_bool,
        validate_dataset,
    )
    from .security_utils import (
        DataverseRequestError,
        confirm_apply,
        get_api_token,
        get_config_value,
        load_config,
        put_dataset_access_request,
        put_file_restriction,
        response_error_summary,
        validate_server_url,
    )
except ImportError:  # Support direct execution
    from dataverse_json import (
        DatasetValidationError,
        find_file_record,
        get_file_records,
        get_persistent_id,
        get_version_block,
        parse_optional_bool,
        validate_dataset,
    )
    from security_utils import (
        DataverseRequestError,
        confirm_apply,
        get_api_token,
        get_config_value,
        load_config,
        put_dataset_access_request,
        put_file_restriction,
        response_error_summary,
        validate_server_url,
    )

try:
    from pyDataverse.api import NativeApi
except ImportError:
    NativeApi = None


REQUIRED_CHANGE_COLUMNS = {
    "doi",
    "file_id",
    "file_name",
    "restricted_new",
    "file_access_request_new",
}
SUCCESS_CODES = {200, 201, 204}


def load_explicit_changes(csv_path):
    """Return only rows with at least one nonblank *_new value."""
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(REQUIRED_CHANGE_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise DatasetValidationError(
                f"Changes CSV is missing required column(s): {', '.join(missing)}."
            )
        changes = []
        seen = set()
        for row_number, row in enumerate(reader, start=2):
            restricted = parse_optional_bool(row.get("restricted_new"))
            access_request = parse_optional_bool(row.get("file_access_request_new"))
            if restricted is None and access_request is None:
                continue
            persistent_id = str(row.get("doi", "")).strip()
            file_id = str(row.get("file_id", "")).strip()
            if not persistent_id or not file_id:
                raise DatasetValidationError(
                    f"CSV row {row_number} must contain both doi and file_id."
                )
            key = (persistent_id, file_id)
            if key in seen:
                raise DatasetValidationError(
                    f"CSV contains duplicate changes for dataset {persistent_id!r}, file {file_id!r}."
                )
            seen.add(key)
            changes.append(
                {
                    "row_number": row_number,
                    "doi": persistent_id,
                    "file_id": file_id,
                    "file_name": str(row.get("file_name", "")).strip(),
                    "restricted": restricted,
                    "file_access_request": access_request,
                }
            )
    if not changes:
        raise DatasetValidationError(
            "The changes CSV contains no nonblank restricted_new or file_access_request_new values."
        )
    return changes


def index_json_files(json_dir):
    indexed = {}
    for path in sorted(json_dir.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as handle:
                data = validate_dataset(json.load(handle))
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(f"Invalid JSON in {path}: {exc}.") from exc
        persistent_id = get_persistent_id(data)
        if persistent_id in indexed:
            raise DatasetValidationError(f"Duplicate dataset JSON for {persistent_id!r}.")
        indexed[persistent_id] = (path, data)
    if not indexed:
        raise DatasetValidationError(f"No dataset JSON files found in {json_dir}.")
    return indexed


def validate_changes_against_json(changes, json_index):
    """Ensure every requested CSV change matches the updated JSON exactly."""
    for change in changes:
        indexed = json_index.get(change["doi"])
        if indexed is None:
            raise DatasetValidationError(
                f"CSV row {change['row_number']} has no matching dataset JSON for {change['doi']!r}."
            )
        _, data = indexed
        records, _ = get_file_records(data)
        record = find_file_record(records, change["file_id"], change["file_name"])
        if record is None:
            raise DatasetValidationError(
                f"CSV row {change['row_number']} file {change['file_id']!r} is not in its dataset JSON."
            )
        data_file = record.get("dataFile", {})
        if change["restricted"] is not None and record.get("restricted") is not change["restricted"]:
            raise DatasetValidationError(
                f"CSV row {change['row_number']} restricted_new does not match the updated JSON."
            )
        if (
            change["file_access_request"] is not None
            and data_file.get("fileAccessRequest") is not change["file_access_request"]
        ):
            raise DatasetValidationError(
                f"CSV row {change['row_number']} file_access_request_new does not match the updated JSON."
            )
    return changes


def restriction_url(native_api, file_id):
    if isinstance(file_id, str) and not file_id.isdigit():
        return f"{native_api.base_url}/api/files/:persistentId/restrict?persistentId={file_id}"
    return f"{native_api.base_url}/api/files/{file_id}/restrict"


def dataset_access_request_url(native_api, dataset_id):
    return f"{native_api.base_url}/api/access/{dataset_id}/allowAccessRequest"


def get_dataset_id(data):
    """Return the numeric dataset ID accepted by older Dataverse installations."""
    dataset_id = data.get("id")
    if dataset_id is None:
        version = get_version_block(data) or {}
        dataset_id = version.get("datasetId")
    if dataset_id is None or not str(dataset_id).isdigit():
        raise DatasetValidationError(
            "Dataset JSON has no numeric id/datasetId required for allowAccessRequest."
        )
    return str(dataset_id)


def dataset_access_policies(changes, json_index):
    """Return one dataset-wide policy for each dataset with access-request changes."""
    affected_ids = {
        change["doi"]
        for change in changes
        if change["file_access_request"] is not None
    }
    policies = []
    for persistent_id in sorted(affected_ids):
        _, data = json_index[persistent_id]
        version = get_version_block(data) or data
        allowed = version.get("fileAccessRequest")
        if not isinstance(allowed, bool):
            raise DatasetValidationError(
                f"Dataset JSON for {persistent_id!r} has no boolean dataset-level "
                "fileAccessRequest value. Run update_json_from_csv.py again."
            )
        policies.append((persistent_id, get_dataset_id(data), allowed))
    return policies


def apply_dataset_access_policy(native_api, persistent_id, dataset_id, allowed):
    token = getattr(native_api, "api_token", None)
    try:
        response = put_dataset_access_request(
            dataset_access_request_url(native_api, dataset_id), token, allowed
        )
    except DataverseRequestError as exc:
        print(f"Error updating dataset access requests for {persistent_id}: {exc}")
        return 0, 1
    if response.status_code not in SUCCESS_CODES:
        print(
            f"Failed dataset access-request update for {persistent_id}: "
            f"{response_error_summary(response)}"
        )
        return 0, 1
    print(f"Updated dataset access requests for {persistent_id} to {allowed}")
    return 1, 0


def preview_change(change):
    fields = []
    if change["restricted"] is not None:
        fields.append(f"restricted={change['restricted']}")
    if change["file_access_request"] is not None:
        fields.append(f"fileAccessRequest={change['file_access_request']}")
    print(
        f"PREVIEW: dataset={change['doi']} file={change['file_id']} "
        f"({change['file_name'] or 'unnamed'}) -> {', '.join(fields)}"
    )


def apply_change(native_api, change):
    errors = 0
    applied = 0
    token = getattr(native_api, "api_token", None)
    file_id = change["file_id"]

    if change["restricted"] is not None:
        try:
            response = put_file_restriction(
                restriction_url(native_api, file_id), token, change["restricted"]
            )
            if response.status_code not in SUCCESS_CODES:
                print(
                    f"Failed restricted update for file {file_id}: "
                    f"{response_error_summary(response)}"
                )
                errors += 1
            else:
                print(f"Updated restricted for file {file_id} to {change['restricted']}")
                applied += 1
        except DataverseRequestError as exc:
            print(f"Error updating restricted for file {file_id}: {exc}")
            errors += 1

    return applied, errors


def parse_args():
    parser = argparse.ArgumentParser(
        description="Push only explicit *_new CSV changes validated against updated JSON files."
    )
    parser.add_argument("--config", default="config.ini", help="INI configuration file.")
    parser.add_argument("--server-url")
    parser.add_argument("--api-key", help="Discouraged; prefer config.ini or hidden prompt.")
    parser.add_argument("--json-dir", help="Directory containing updated dataset JSON files.")
    parser.add_argument("--changes-csv", help="Updated CSV containing explicit *_new values.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply validated explicit changes.")
    mode.add_argument("--dry-run", action="store_true", help="Preview mode (default).")
    parser.add_argument("--yes", action="store_true", help="Skip APPLY prompt; requires --apply.")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    args.server_url = args.server_url or get_config_value(config, "dataverse", "server_url")
    args.json_dir = args.json_dir or get_config_value(config, "files", "json_dir", "dataset_jsons")
    args.changes_csv = args.changes_csv or get_config_value(
        config,
        "files",
        "changes_csv",
        get_config_value(config, "files", "output_csv", "dataset_files.csv"),
    )
    if not args.server_url:
        args.server_url = input("Server URL: ").strip()
    args.api_key = get_api_token(
        args.api_key, get_config_value(config, "dataverse", "api_token")
    )
    args.server_url = validate_server_url(args.server_url, args.api_key)
    if args.yes and not args.apply:
        print("--yes is valid only with --apply.", file=sys.stderr)
        return 2
    if NativeApi is None:
        print("pyDataverse is required; install requirements.txt.", file=sys.stderr)
        return 1

    json_dir = Path(args.json_dir)
    changes_csv = Path(args.changes_csv)
    if not json_dir.is_dir():
        print(f"JSON directory not found: {json_dir}", file=sys.stderr)
        return 1
    if not changes_csv.is_file():
        print(f"Changes CSV not found: {changes_csv}", file=sys.stderr)
        return 1

    try:
        changes = load_explicit_changes(changes_csv)
        json_index = index_json_files(json_dir)
        validate_changes_against_json(changes, json_index)
        access_policies = dataset_access_policies(changes, json_index)
    except (DatasetValidationError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Mode: {'APPLY' if args.apply else 'PREVIEW (no changes)'}")
    print(f"Target server: {args.server_url}")
    print(f"Explicit file changes: {len(changes)}")
    for change in changes:
        preview_change(change)
    for persistent_id, dataset_id, allowed in access_policies:
        print(
            f"PREVIEW: dataset={persistent_id} id={dataset_id} "
            f"-> allowAccessRequest={allowed}"
        )

    if not args.apply:
        return 0
    if not confirm_apply(args.server_url, len(changes), assume_yes=args.yes):
        print("Apply cancelled; no changes were made.")
        return 1

    native_api = NativeApi(args.server_url, api_token=args.api_key)
    applied = 0
    errors = 0
    for change in changes:
        change_applied, change_errors = apply_change(native_api, change)
        applied += change_applied
        errors += change_errors
    for persistent_id, dataset_id, allowed in access_policies:
        policy_applied, policy_errors = apply_dataset_access_policy(
            native_api, persistent_id, dataset_id, allowed
        )
        applied += policy_applied
        errors += policy_errors
    print(f"API updates applied: {applied}")
    if errors:
        print(f"Total errors: {errors}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

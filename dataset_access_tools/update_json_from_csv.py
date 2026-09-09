#!/usr/bin/env python3
"""Apply reviewed CSV access changes to existing Dataverse dataset JSON files."""

import argparse
import copy
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
    from .security_utils import get_config_value, load_config
except ImportError:  # Support direct execution: python dataset_access_tools/script.py
    from dataverse_json import (
        DatasetValidationError,
        find_file_record,
        get_file_records,
        get_persistent_id,
        get_version_block,
        parse_optional_bool,
        validate_dataset,
    )
    from security_utils import get_config_value, load_config


REQUIRED_COLUMNS = {
    "doi",
    "file_id",
    "file_name",
    "restricted_new",
    "file_access_request_new",
}


def sanitize_filename(persistent_id):
    safe = persistent_id.replace("doi:", "").replace("/", "_").replace(":", "_")
    return f"dataset_{safe}.json"


def load_csv(csv_path):
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise DatasetValidationError(
                f"CSV is missing required column(s): {', '.join(missing)}."
            )
        return list(reader)


def update_dataset_data(data, updates):
    """Apply validated rows atomically and return the changed record count."""
    file_records, _ = get_file_records(data)
    pending = []

    for row_number, row in updates:
        file_id = str(row.get("file_id", "")).strip()
        if not file_id:
            raise DatasetValidationError(f"CSV row {row_number} has no file_id.")

        restricted = parse_optional_bool(row.get("restricted_new"))
        access_request = parse_optional_bool(row.get("file_access_request_new"))
        if restricted is None and access_request is None:
            continue

        record = find_file_record(file_records, file_id, row.get("file_name", ""))
        if record is None:
            raise DatasetValidationError(
                f"CSV row {row_number} references file {file_id!r}, which is not in the dataset JSON."
            )
        pending.append((record, restricted, access_request))

    changed_records = 0
    for record, restricted, access_request in pending:
        changed = False
        data_file = record.setdefault("dataFile", {})
        if restricted is not None and record.get("restricted") != restricted:
            record["restricted"] = restricted
            changed = True
        if access_request is not None and data_file.get("fileAccessRequest") != access_request:
            data_file["fileAccessRequest"] = access_request
            changed = True
        changed_records += int(changed)

    # Dataverse also stores a dataset-wide access-request switch beside the
    # license metadata. Keep it synchronized with all currently restricted
    # files or the dataset page can offer Request Access incorrectly.
    if pending:
        restricted_records = [
            record for record in file_records if record.get("restricted") is True
        ]
        if restricted_records:
            allow_dataset_access_requests = all(
                record.get("dataFile", {}).get("fileAccessRequest") is not False
                for record in restricted_records
            )
            version = get_version_block(data) or data
            version["fileAccessRequest"] = allow_dataset_access_requests
    return changed_records


def save_dataset_json(json_path, data):
    temporary_path = json_path.with_suffix(json_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    temporary_path.replace(json_path)


def index_dataset_jsons(json_dir):
    """Index existing exports by identifier without relying on a filename convention."""
    indexed = {}
    json_paths = sorted(json_dir.glob("*.json"))
    if not json_paths:
        raise DatasetValidationError(f"No dataset JSON files found in {json_dir}.")

    for json_path in json_paths:
        try:
            with json_path.open(encoding="utf-8") as handle:
                data = validate_dataset(json.load(handle))
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(f"Invalid JSON in {json_path}: {exc}.") from exc
        persistent_id = get_persistent_id(data)
        if persistent_id in indexed:
            raise DatasetValidationError(
                f"Duplicate dataset identifier {persistent_id!r} in "
                f"{indexed[persistent_id][0]} and {json_path}."
            )
        indexed[persistent_id] = (json_path, data)
    return indexed


def process_updates(csv_path, json_dir):
    rows = load_csv(csv_path)
    dataset_index = index_dataset_jsons(json_dir)
    updates_by_id = {}
    for row_number, row in enumerate(rows, start=2):
        persistent_id = str(row.get("doi", "")).strip()
        if not persistent_id:
            raise DatasetValidationError(f"CSV row {row_number} has no DOI/persistent identifier.")
        updates_by_id.setdefault(persistent_id, []).append((row_number, row))

    if not updates_by_id:
        raise DatasetValidationError("CSV contains no dataset rows.")

    updated_datasets = 0
    updated_files = 0
    for persistent_id, updates in updates_by_id.items():
        indexed_dataset = dataset_index.get(persistent_id)
        if indexed_dataset is None:
            raise DatasetValidationError(
                f"Dataset JSON not found for {persistent_id!r} in {json_dir}. "
                "This tool updates existing exports and will not create missing datasets."
            )
        json_path, original = indexed_dataset

        candidate = copy.deepcopy(validate_dataset(original, expected_id=persistent_id))
        changed_files = update_dataset_data(candidate, updates)
        if candidate != original:
            save_dataset_json(json_path, candidate)
            updated_datasets += 1
            updated_files += changed_files
            print(
                f"Updated {changed_files} file record(s) and synchronized dataset "
                f"access requests in {json_path}"
            )

    return updated_datasets, updated_files


def parse_args():
    parser = argparse.ArgumentParser(
        description="Apply reviewed CSV access values to existing dataset JSON exports."
    )
    parser.add_argument(
        "--config",
        default="config.ini",
        help="INI configuration file (default: config.ini).",
    )
    parser.add_argument("csv_file", help="CSV file containing reviewed access values.")
    parser.add_argument(
        "--json-dir",
        default=None,
        help="Directory containing existing dataset JSON exports.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    args.json_dir = args.json_dir or get_config_value(config, "files", "json_dir", "dataset_jsons")
    csv_path = Path(args.csv_file)
    json_dir = Path(args.json_dir)
    if not csv_path.is_file():
        sys.exit(f"CSV file not found: {csv_path}")
    if not json_dir.is_dir():
        sys.exit(f"JSON directory not found: {json_dir}")

    try:
        datasets, files = process_updates(csv_path, json_dir)
    except (DatasetValidationError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Updated {files} file record(s) across {datasets} dataset(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

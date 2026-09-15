#!/usr/bin/env python3
"""Convert a directory of supported Dataverse dataset JSON files to CSV."""

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    from .dataverse_json import CSV_FIELDNAMES, DatasetValidationError, dataset_to_rows
    from .security_utils import get_config_value, load_config
except ImportError:  # Support direct execution
    from dataverse_json import CSV_FIELDNAMES, DatasetValidationError, dataset_to_rows
    from security_utils import get_config_value, load_config


def write_csv(rows, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def convert_directory(json_dir, output_path):
    json_paths = sorted(json_dir.glob("*.json"))
    if not json_paths:
        raise DatasetValidationError(f"No JSON files found in {json_dir}.")

    rows = []
    errors = []
    for path in json_paths:
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            rows.extend(dataset_to_rows(data))
        except (json.JSONDecodeError, DatasetValidationError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        raise DatasetValidationError("Invalid dataset export(s): " + "; ".join(errors))
    if not rows:
        raise DatasetValidationError("The dataset exports contain no file records.")
    write_csv(rows, output_path)
    return len(json_paths), len(rows)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert Dataverse dataset JSON exports to an editable file-access CSV."
    )
    parser.add_argument("--config", default="config.ini", help="INI configuration file.")
    parser.add_argument("--json-dir", help="Directory containing JSON exports.")
    parser.add_argument("--output", help="Output CSV path.")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    args.json_dir = args.json_dir or get_config_value(config, "files", "json_dir", "dataset_jsons")
    args.output = args.output or get_config_value(
        config, "files", "output_csv", "dataset_files.csv"
    )
    json_dir = Path(args.json_dir)
    if not json_dir.is_dir():
        print(f"Error: JSON directory not found: {json_dir}", file=sys.stderr)
        return 1
    try:
        datasets, rows = convert_directory(json_dir, Path(args.output))
    except DatasetValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {rows} file row(s) from {datasets} dataset(s) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

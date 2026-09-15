#!/usr/bin/env python3
"""Legacy-compatible converter for explicitly named Dataverse JSON files."""

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    from .dataverse_json import CSV_FIELDNAMES, DatasetValidationError, dataset_to_rows
except ImportError:  # Support direct execution
    from dataverse_json import CSV_FIELDNAMES, DatasetValidationError, dataset_to_rows


def convert_files(json_paths, output_path):
    rows = []
    for path in json_paths:
        with path.open(encoding="utf-8") as handle:
            rows.extend(dataset_to_rows(json.load(handle)))
    if not rows:
        raise DatasetValidationError("The supplied dataset exports contain no file records.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Convert explicitly named Dataverse JSON exports to an editable CSV."
    )
    parser.add_argument("json_files", nargs="+", help="Dataset JSON files to process.")
    parser.add_argument("-o", "--output", default="dataset_files.csv")
    args = parser.parse_args()
    try:
        rows = convert_files([Path(path) for path in args.json_files], Path(args.output))
    except (OSError, json.JSONDecodeError, DatasetValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {rows} row(s) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

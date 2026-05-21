#!/usr/bin/env python3
"""
json_folder_to_csv.py

Read a folder of Dataverse dataset JSON files and export file-level rows to
a CSV that mirrors the output of collection_to_csv.py.

Two JSON shapes are supported:
  A) Modern Dataverse API export  — top-level keys + "latestVersion" block
     (produced by /api/datasets/export or --save-json in collection_to_csv.py)
  B) Legacy / custom flat format  — "datasetPersistentId" + "data" list
     (the doi10.5683_SP3_*.json style)

Usage
-----
  python3 json_folder_to_csv.py --json-dir /path/to/jsons --output dataset_files.csv

The output columns are identical to collection_to_csv.py:
  doi, dataset_title, file_id, file_name,
  restricted, file_access_request,
  restricted_new, file_access_request_new
"""

""" To run it
python3 json_folder_to_csv.py \
    --json-dir /Users/yourname/downloads/dataset_jsons \
    --output   /Users/yourname/downloads/dataset_files.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers shared with the previous json_to_csv.py fix
# ---------------------------------------------------------------------------

def _version_block(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Return whichever version block is present.

    Dataverse uses two different keys depending on the API endpoint:
      /api/search or newer exports  → "latestVersion"
      /api/datasets/export          → "datasetVersion"
    """
    for key in ("latestVersion", "datasetVersion"):
        block = data.get(key)
        if isinstance(block, dict) and block:
            return block
    return None


def _extract_doi(data: Dict[str, Any]) -> str:
    """Return the DOI / persistent identifier, trying multiple locations."""
    # Modern format: top-level datasetPersistentId
    if data.get("datasetPersistentId"):
        return data["datasetPersistentId"]
    # Modern format: version block
    vb = _version_block(data)
    if vb and vb.get("datasetPersistentId"):
        return vb["datasetPersistentId"]
    # Modern format: persistentUrl (https://doi.org/…)
    if data.get("persistentUrl"):
        return data["persistentUrl"]
    # Fallback
    if data.get("identifier"):
        return data["identifier"]
    return ""


def _extract_title(data: Dict[str, Any]) -> str:
    """Return the dataset title from whichever location Dataverse put it."""
    # Shortcut fields (legacy flat format)
    if data.get("datasetName"):
        return data["datasetName"]
    if data.get("title"):
        return data["title"]
    # Modern format: dig into metadataBlocks.citation.fields
    vb = _version_block(data)
    if vb:
        for field in vb.get("metadataBlocks", {}).get("citation", {}).get("fields") or []:
            if field.get("typeName") == "title":
                value = field.get("value")
                if isinstance(value, str):
                    return value
                if isinstance(value, list) and value:
                    first = value[0]
                    return first.get("value", "") if isinstance(first, dict) else str(first)
    return ""


def _extract_files(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return the raw file list from whichever location Dataverse put it.

    Priority:
      1. latestVersion.files / datasetVersion.files  (modern API)
      2. top-level data[]                             (legacy flat)
      3. top-level files[]
    """
    vb = _version_block(data)
    if vb:
        files = vb.get("files")
        if isinstance(files, list):
            return files

    if isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data.get("files"), list):
        return data["files"]

    return []


# ---------------------------------------------------------------------------
# Row extraction
# ---------------------------------------------------------------------------

def _dataset_file_access_request(data: Dict[str, Any]) -> bool:
    """
    Return the dataset-level fileAccessRequest flag.

    In the modern format this lives in the version block.
    The legacy flat format does not carry this flag, so we default to False.
    """
    vb = _version_block(data)
    if vb is not None:
        flag = vb.get("fileAccessRequest")
        if flag is not None:
            return bool(flag)
    return False


def extract_rows(data: Dict[str, Any], source_path: str = "") -> List[Dict[str, Any]]:
    """
    Convert one parsed JSON object into a list of CSV row dicts.

    Each row represents one file inside the dataset and matches the columns
    produced by collection_to_csv.py.
    """
    doi = _extract_doi(data)
    title = _extract_title(data)
    dataset_far = _dataset_file_access_request(data)
    file_entries = _extract_files(data)

    if not doi:
        print(f"  Warning: no DOI found  ({source_path})")
    if not title:
        print(f"  Warning: no title found ({source_path})")

    rows = []

    if not file_entries:
        # Still emit one row so the dataset shows up in the CSV
        rows.append({
            "doi": doi,
            "dataset_title": title,
            "file_id": "",
            "file_name": "",
            "restricted": "",
            "file_access_request": "",
            "restricted_new": "",
            "file_access_request_new": "",
        })
        return rows

    for entry in file_entries:
        # Modern format: outer entry holds restricted / label / dataFile sub-dict
        data_file = entry.get("dataFile")
        if isinstance(data_file, dict):
            # --- Modern Dataverse format ---
            file_id = data_file.get("id", "")
            file_name = entry.get("label") or data_file.get("filename", "")
            restricted = bool(entry.get("restricted", False))
            # file-level fileAccessRequest; fall back to dataset-level
            far = data_file.get("fileAccessRequest")
            file_access_request = bool(far) if far is not None else dataset_far
        else:
            # --- Legacy flat format (data[]) ---
            file_id = entry.get("id", "")
            file_name = entry.get("label") or entry.get("filename", "")
            # Legacy format does not carry restricted / fileAccessRequest —
            # leave them False (not None) so the CSV is consistent.
            restricted = bool(entry.get("restricted", False))
            far = entry.get("fileAccessRequest")
            file_access_request = bool(far) if far is not None else dataset_far

        rows.append({
            "doi": doi,
            "dataset_title": title,
            "file_id": str(file_id),
            "file_name": file_name,
            "restricted": restricted,
            "file_access_request": file_access_request,
            "restricted_new": "",
            "file_access_request_new": "",
        })

    return rows


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "doi",
    "dataset_title",
    "file_id",
    "file_name",
    "restricted",
    "file_access_request",
    "restricted_new",
    "file_access_request_new",
]


def write_csv(rows: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def load_json_files(json_dir: Path) -> List[Path]:
    files = sorted(json_dir.glob("*.json"))
    if not files:
        print(f"No .json files found in: {json_dir}", file=sys.stderr)
    return files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read a folder of Dataverse dataset JSON files and export "
            "file-level rows to a CSV (same format as collection_to_csv.py)."
        )
    )
    parser.add_argument(
        "--json-dir",
        required=True,
        metavar="DIR",
        help="Folder containing the dataset JSON files.",
    )
    parser.add_argument(
        "--output",
        default="dataset_files.csv",
        metavar="FILE",
        help="CSV output file path (default: dataset_files.csv).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    json_dir = Path(args.json_dir)

    if not json_dir.is_dir():
        sys.exit(f"Error: '{json_dir}' is not a directory or does not exist.")

    json_paths = load_json_files(json_dir)
    if not json_paths:
        sys.exit(1)

    all_rows: List[Dict[str, Any]] = []

    for path in json_paths:
        print(f"Processing: {path.name}")
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            print(f"  Skipping — invalid JSON: {exc}")
            continue

        rows = extract_rows(data, source_path=str(path))
        print(f"  → {len(rows)} file row(s)")
        all_rows.extend(rows)

    if not all_rows:
        sys.exit("No rows extracted. Check that the JSON files contain dataset metadata.")

    output_path = Path(args.output)
    write_csv(all_rows, output_path)
    print(f"\nWrote {len(all_rows)} rows to {output_path.resolve()}")


if __name__ == "__main__":
    main()

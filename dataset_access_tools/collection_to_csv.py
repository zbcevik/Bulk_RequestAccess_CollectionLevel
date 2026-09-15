#!/usr/bin/env python3
"""Fetch dataset metadata from a Dataverse collection and export file-level rows to CSV."""

import argparse
import csv
import json
from pathlib import Path

try:
    from .dataverse_json import DatasetValidationError, dataset_to_rows
    from .security_utils import (
        get_api_token,
        get_config_value,
        load_config,
        validate_server_url,
    )
except ImportError:  # Support direct execution
    from dataverse_json import DatasetValidationError, dataset_to_rows
    from security_utils import get_api_token, get_config_value, load_config, validate_server_url

try:
    from pyDataverse.api import NativeApi
except ImportError:
    NativeApi = None


def normalize_server_url(server_url):
    return validate_server_url(server_url)


def create_dataverse_apis(server_url, api_key=None):
    if NativeApi is None:
        raise SystemExit("pyDataverse is required. Install dependencies with `python3 -m pip install -r requirements.txt`.")
    native_api = NativeApi(server_url, api_token=api_key)
    return native_api


def search_collection_datasets(native_api, collection_alias):
    # Use the /contents endpoint to list datasets in the dataverse
    url = f"{native_api.base_url_api_native}/dataverses/{collection_alias}/contents"
    response = native_api.get_request(url)
    data = response.json() if hasattr(response, "json") else response
    if isinstance(data, dict) and 'data' in data:
        contents = data['data']
    else:
        contents = data
    # Filter for datasets
    datasets = [item for item in contents if isinstance(item, dict) and item.get('type') == 'dataset']
    return datasets


def extract_dataset_rows(dataset_data, source_identifier=""):
    if not isinstance(dataset_data, dict):
        return []
    if source_identifier and not any(
        dataset_data.get(key) for key in ("persistentId", "datasetPersistentId", "identifier")
    ):
        dataset_data = dict(dataset_data)
        dataset_data["persistentId"] = source_identifier
    try:
        return dataset_to_rows(dataset_data)
    except DatasetValidationError:
        return []


def save_json(dataset_json, output_dir, identifier):
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"dataset_{identifier}.json"
    with filename.open("w", encoding="utf-8") as handle:
        json.dump(dataset_json, handle, indent=2)
    return filename


def write_csv(rows, output_path):
    fieldnames = [
        "doi",
        "dataset_title",
        "file_id",
        "file_name",
        "restricted",
        "file_access_request",
        "restricted_new",
        "file_access_request_new",
    ]
    if output_path.parent and output_path.parent != Path(""):
        output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch all datasets in a Dataverse collection and export file-level rows to CSV."
    )
    parser.add_argument(
        "--config",
        default="config.ini",
        help="INI configuration file (default: config.ini).",
    )
    parser.add_argument(
        "--server-url",
        help="Base server URL for the Dataverse/Borealis instance.",
    )
    parser.add_argument(
        "--collection-alias",
        help="Collection alias to query for datasets.",
    )
    parser.add_argument(
        "--api-key",
        help="API token (discouraged: prefer config.ini or the hidden prompt).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="CSV output file path.",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save each retrieved dataset JSON locally.",
    )
    parser.add_argument(
        "--json-dir",
        default=None,
        help="Directory to save retrieved dataset JSON files when --save-json is used.",
    )
    return parser.parse_args()


def prompt_for_missing_args(args):
    config = load_config(args.config)
    args.server_url = args.server_url or get_config_value(config, "dataverse", "server_url")
    args.collection_alias = args.collection_alias or get_config_value(
        config, "dataverse", "collection_alias"
    )
    args.output = args.output or get_config_value(
        config, "files", "output_csv", "dataset_files.csv"
    )
    args.json_dir = args.json_dir or get_config_value(config, "files", "json_dir", "dataset_jsons")
    if not args.server_url:
        args.server_url = input("Server URL: ").strip()
    if not args.collection_alias:
        args.collection_alias = input("Collection alias: ").strip()
    args.api_key = get_api_token(
        args.api_key,
        get_config_value(config, "dataverse", "api_token"),
    )
    return args


def main():
    args = parse_args()
    args = prompt_for_missing_args(args)

    server_url = validate_server_url(normalize_server_url(args.server_url), args.api_key)
    native_api = create_dataverse_apis(server_url, args.api_key)

    print(f"Searching collection datasets for alias {args.collection_alias}...")
    docs = search_collection_datasets(native_api, args.collection_alias)

    if not docs:
        print("No datasets found for the collection alias.")
        return

    print(f"Found {len(docs)} dataset(s). Fetching dataset details...")
    all_rows = []
    saved_json_dir = Path(args.json_dir)
    if args.save_json:
        saved_json_dir.mkdir(parents=True, exist_ok=True)

    for doc in docs:
        pid = doc.get("persistentId")
        if not pid:
            authority = doc.get("authority")
            identifier = doc.get("identifier")
            if authority and identifier:
                pid = f"doi:{authority}/{identifier}"

        if not pid:
            print("Skipping dataset with missing persistentId:", doc)
            continue

        dataset_response = native_api.get_dataset(pid, is_pid=True)
        dataset_data = dataset_response.json() if hasattr(dataset_response, "json") else dataset_response
        dataset_data = dataset_data.get("data") or dataset_data

        if args.save_json:
            save_identifier = pid.replace("doi:", "").replace("/", "_")
            save_json(dataset_data, saved_json_dir, save_identifier)

        all_rows.extend(extract_dataset_rows(dataset_data, source_identifier=pid))

    if not all_rows:
        print("No file rows were extracted from the datasets.")
        return

    output_path = Path(args.output)
    write_csv(all_rows, output_path)
    print(f"Wrote {len(all_rows)} rows to {output_path}")

    if args.save_json:
        print(f"Saved dataset JSON files to {Path(args.json_dir).resolve()}")


if __name__ == "__main__":
    main()

import argparse
import csv
import glob
import json
from pathlib import Path


def extract_title(dataset_version):
    citation_block = dataset_version.get("metadataBlocks", {}).get("citation", {})
    fields = citation_block.get("fields", [])
    for field in fields:
        if field.get("typeName") == "title":
            value = field.get("value")
            if isinstance(value, str):
                return value
    return None


def extract_doi(dataset):
    doi = dataset.get("persistentUrl") or dataset.get("identifier")
    if doi and doi.startswith("https://doi.org/"):
        return doi
    return doi


def parse_dataset_file(dataset):
    doi = extract_doi(dataset) or ""
    version = dataset.get("datasetVersion", {})
    title = extract_title(version) or dataset.get("title") or ""
    file_access_request_dataset = version.get("fileAccessRequest")

    # Support file lists at the root or nested inside datasetVersion.
    file_records = dataset.get("files") or version.get("files") or []

    rows = []
    for file_record in file_records:
        file_item = file_record.get("dataFile", {})
        file_id = file_item.get("id")
        file_name = file_item.get("filename")
        restricted = file_record.get("restricted")
        file_access_request = file_item.get("fileAccessRequest")
        if file_access_request is None:
            file_access_request = file_access_request_dataset

        rows.append({
            "doi": doi,
            "dataset_title": title,
            "file_id": file_id,
            "file_name": file_name,
            "restricted": bool(restricted),
            "file_access_request": bool(file_access_request),
        })

    return rows


def load_json_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(
        description="Convert dataset export JSON files into a CSV of file rows with DOI, title, and access flags."
    )
    parser.add_argument(
        "json_files",
        nargs="*",
        help="JSON files to process. If omitted, all export*.json files in the current folder are used.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="dataset_files.csv",
        help="Output CSV file name.",
    )
    args = parser.parse_args()

    json_paths = args.json_files or sorted(glob.glob("export*.json"))
    if not json_paths:
        raise SystemExit("No JSON files found to process. Provide filenames or place export*.json files in the folder.")

    all_rows = []
    for json_path in json_paths:
        dataset = load_json_file(json_path)
        all_rows.extend(parse_dataset_file(dataset))

    fieldnames = ["doi", "dataset_title", "file_id", "file_name", "restricted", "file_access_request"]
    output_path = Path(args.output)
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {output_path}")


if __name__ == "__main__":
    main()

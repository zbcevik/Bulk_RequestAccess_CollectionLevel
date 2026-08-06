# Bulk Request Access - Collection Level

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)

A professional Python toolkit for applying bulk file-level access updates to Borealis/Dataverse datasets.

This repository helps you:
- export dataset file metadata to a CSV,
- review and edit access values in a spreadsheet,
- convert edited CSV rows back into dataset JSON,
- push the changes back to Dataverse in a controlled workflow.

---

## Project overview

The workflow is designed for collection-level administration tasks where you need to update file-level flags such as:
- restricted
- fileAccessRequest

It is especially useful for curators and administrators managing large collections of datasets.

---

## Repository structure

```text
.
├── dataset_access_tools/    # Runnable Python entry points for dataset access workflows
├── dataset_jsons/            # Generated dataset JSON output
├── examples/                 # Sample exports, notebooks, and reference files
├── requirements.txt          # Python dependencies
├── CONTRIBUTING.md           # Contribution guidance
└── README.md                 # Project documentation
```

---

## Prerequisites

1. Install Python 3.9+.
2. Create and activate a virtual environment.
3. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

4. Prepare your Borealis/Dataverse server URL and API key.

---

## Quick start

### 1) Export collection metadata

```bash
python3 dataset_access_tools/collection_to_csv.py \
  --server-url "https://demo.borealisdata.ca" \
  --collection-alias "your-collection-alias" \
  --api-key "YOUR_API_KEY" \
  --output dataset_files.csv \
  --save-json \
  --json-dir dataset_jsons
```

This creates a CSV containing file-level rows for the selected collection.

### 2) Edit the CSV

Open the exported CSV in Excel, Google Sheets, or any spreadsheet editor.

Use these columns to control updates:
- restricted_new
- file_access_request_new

Accepted values include:
- true / false
- yes / no
- 1 / 0

Leave a field blank if you do not want to change that value.


### 3) Generate updated dataset JSON

```bash
python3 dataset_access_tools/update_json_from_csv.py dataset_files.csv --json-dir dataset_jsons
```

### 4) Preview changes

```bash
python3 dataset_access_tools/push_json_to_dataverse.py \
  --server-url "https://demo.borealisdata.ca" \
  --api-key "YOUR_API_KEY" \
  --json-dir dataset_jsons \
  --dry-run
```

### 5) Push changes to Dataverse

```bash
python3 dataset_access_tools/push_json_to_dataverse.py \
  --server-url "https://demo.borealisdata.ca" \
  --api-key "YOUR_API_KEY" \
  --json-dir dataset_jsons
```

---

## Single dataset workflow

For testing or targeted updates, use the single-dataset script:

```bash
python3 dataset_access_tools/push_single_dataset.py \
  --server-url "https://demo.borealisdata.ca" \
  --api-key "YOUR_API_KEY" \
  --json-path /path/to/dataset.json \
  --dry-run
```

You can also run it interactively without passing arguments.

---

## Output files

The main workflow produces:
- a CSV file with file-level rows,
- dataset JSON files under dataset_jsons/,
- optional preview output from dry runs.

Typical CSV columns include:
- doi
- dataset_title
- file_id
- file_name
- restricted
- file_access_request
- restricted_new
- file_access_request_new

---

## Notes and troubleshooting

- Use --dry-run before applying any real changes.
- Some Dataverse instances may not support every file restriction endpoint in the same way.
- File access request updates are typically more reliable than file restriction updates on some servers.
- If a dataset file does not contain relevant access fields, it may be skipped.

---

## Scripts

- dataset_access_tools/collection_to_csv.py: export collection metadata to CSV and optionally save JSON
- dataset_access_tools/update_json_from_csv.py: apply edited CSV values back into dataset JSON
- dataset_access_tools/push_json_to_dataverse.py: push updated JSON files to Dataverse
- dataset_access_tools/push_single_dataset.py: push a single dataset JSON file for testing or targeted updates
- dataset_access_tools/json_to_csv.py: convert exported JSON files into CSV
- dataset_access_tools/json_folder_to_csv.py: convert a folder of JSON exports into CSV

---

## Contributing

Contributions are welcome. Please see CONTRIBUTING.md for the recommended workflow.

- Summary: Files processed, changes applied, errors encountered

---

### Utility Scripts

#### `json_to_csv.py`
**Purpose:** Convert dataset export JSON files (from Dataverse) into a CSV table for inspection and editing.

**Usage:**
```bash
python3 json_to_csv.py export1.json export2.json -o output.csv
```

or to convert all `export*.json` files:

```bash
python3 json_to_csv.py -o output.csv
```

**Key features:**
- Takes raw Dataverse export JSON files as input
- Extracts file metadata and converts to CSV format
- Useful if you have pre-downloaded export JSONs instead of using `collection_to_csv.py`

**Output:**
- CSV file with columns: `doi`, `dataset_title`, `file_id`, `file_name`, `restricted`, `file_access_request`

---

### Legacy/Development Scripts

#### `push_json_to_dataverse.py`
Superceded by Workflow Step 4. Use this for bulk dataset updates.

#### `res2json.json`, `pccfjson.json`
Sample dataset JSON files for testing purposes.

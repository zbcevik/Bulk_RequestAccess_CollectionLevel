# Bulk_RequestAccess_CollectionLevel

A small toolset for making bulk file-level `restricted` and `fileAccessRequest` updates in Borealis/Dataverse.

This repository helps you:
- export dataset file metadata to a CSV,
- edit restrictions and request-access values in a spreadsheet,
- convert the edited CSV back into dataset JSON,
- push the JSON changes back to Borealis/Dataverse.

---

## Prerequisites

1. Install Python 3.
2. Install `pyDataverse` if you plan to fetch or push data to Dataverse:

```bash
python3 -m pip install pyDataverse
```

3. Have your Borealis/Dataverse server URL and API key ready.

---

## Clone this repository locally

If you want to run the scripts from your own Mac or Git Bash environment, first clone this repository:

```bash
git clone https://github.com/zbcevik/Bulk_RequestAccess_CollectionLevel.git
cd Bulk_RequestAccess_CollectionLevel
```

No additional repository changes are required to use these scripts locally. After cloning, run the commands below from the cloned folder or from any path where you have the files.

---

## Workflow for a beginner

### Run everything locally on your Mac or Git Bash

These scripts are regular Python programs. You can run them from any local folder in your Mac Terminal or Git Bash.

Example from a local folder:

```bash
cd /Users/yourname/projects/Bulk_RequestAccess_CollectionLevel
python3 json_to_csv.py export1.json export2.json -o /Users/yourname/downloads/dataset_files.csv
```

When you use an output path, the script writes files to that local location instead of only inside the repo.

### Step 1: Get dataset export JSON files

If you already have export JSON files (for example, `export1.json`, `export2.json`), place them in the folder where you want to run the script.

If you do not have export files, use the collection export script in Step 2 to fetch them from your collection.

### Optional: Fetch dataset data directly from your collection

If you want to download file metadata and dataset JSON locally, use:

```bash
python3 collection_to_csv.py --server-url "https://demo.borealisdata.ca" --collection-alias "your-collection-alias" --api-key "YOUR_API_KEY" --output /Users/yourname/downloads/dataset_files.csv --save-json --json-dir /Users/yourname/downloads/dataset_jsons
```

This saves the exported CSV and dataset JSON files to the local paths you choose.

### Step 2: Convert export JSON to CSV

If you want to inspect or edit file metadata in a spreadsheet, convert export JSON into a CSV first.

Run:

```bash
python3 json_to_csv.py export1.json export2.json -o /Users/yourname/downloads/dataset_files.csv
```

If you want to convert every `export*.json` file in the current directory, run:

```bash
python3 json_to_csv.py -o /Users/yourname/downloads/dataset_files.csv
```

This will create the CSV at the path you choose with one row per file and these important columns:
- `doi`
- `dataset_title`
- `file_id`
- `file_name`
- `restricted`
- `file_access_request`


### Step 3: Edit the CSV

Open `dataset_files.csv` in Excel, Google Sheets, or another editor.

To change values, use these columns:
- `restricted_new`
- `file_access_request_new`

Only values in the `_new` columns are applied.

Accepted values:
- `true`, `false`
- `yes`, `no`
- `1`, `0`

Leave other rows blank if you do not want to change them.


### Step 4: Create or update JSON files from the CSV

Run:

```bash
python3 update_json_from_csv.py /Users/yourname/downloads/dataset_files.csv --json-dir /Users/yourname/downloads/dataset_jsons
```

What this does:
- reads `dataset_files.csv`
- creates `dataset_jsons/` if it does not exist
- generates or updates JSON files for each dataset
- writes the new values from `restricted_new` and `file_access_request_new`

If a dataset already exists in `dataset_jsons/`, it updates the matching file records.


### Step 5: Preview the changes with a dry run

Before you push changes, preview them with `--dry-run`.

```bash
python3 push_json_to_dataverse.py --server-url "https://demo.borealisdata.ca" --api-key "YOUR_API_KEY" --json-dir /Users/yourname/downloads/dataset_jsons --dry-run
```

This will print the file updates the script would perform without modifying anything on the server.

If you see only the files you expect, proceed to the next step.


### Step 6: Push changes to Borealis/Dataverse

Once the dry run looks correct, run:

```bash
python3 push_json_to_dataverse.py --server-url "https://demo.borealisdata.ca" --api-key "YOUR_API_KEY" --json-dir /Users/yourname/downloads/dataset_jsons
```

This applies the changes in `dataset_jsons/` to the server.


## Notes and troubleshooting

- The script only updates file records that contain `restricted` or `fileAccessRequest` values.
- If a dataset file does not include either field, it is skipped.
- Use `--dry-run` every time before real execution.
- If you see `415 Unsupported Media Type`, the API endpoint may not support the method or payload being used.
- If you see `404` for `unrestrict`, your server may not support the unrestrict endpoint or the file ID may be invalid.


## Script summary

### `json_to_csv.py`
- Converts dataset export JSON files into a CSV table.

### `collection_to_csv.py`
- Fetches metadata from a collection and writes dataset file rows to CSV.

### `update_json_from_csv.py`
- Reads an edited CSV and generates updated dataset JSON files.

### `push_json_to_dataverse.py`
- Pushes the updated JSON file metadata back to your Borealis/Dataverse server.

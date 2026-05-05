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
2. Install required packages:

```bash
python3 -m pip install pyDataverse httpx
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

## Workflows

### Collection-Level Updates (4-Step Workflow)

This workflow allows you to export multiple datasets from a collection, edit their file metadata in a spreadsheet, and push the changes back to Borealis/Dataverse.

#### Step 1: Export collection metadata to CSV

Run `collection_to_csv.py` to fetch dataset file metadata directly from your Borealis/Dataverse collection:

```bash
python3 collection_to_csv.py --server-url "https://demo.borealisdata.ca" --collection-alias "your-collection-alias" --api-key "YOUR_API_KEY" --output /Users/yourname/downloads/dataset_files.csv --save-json --json-dir /Users/yourname/downloads/dataset_jsons
```

**What this does:**
- Connects to your Borealis/Dataverse instance
- Fetches all datasets in the specified collection
- Extracts file metadata (file ID, filename, current restriction status, file access request status)
- Exports a CSV with columns: `doi`, `dataset_title`, `file_id`, `file_name`, `restricted`, `file_access_request`
- **Optional**: `--save-json` saves the full dataset JSON files to a local directory for reference
- **Optional**: `--json-dir` specifies where to save the dataset JSONs (e.g., `dataset_jsons/`)

**Alternative**: If you already have export JSON files from Dataverse, place them in your working directory and skip to Step 3 using `update_json_from_csv.py` instead. Then use `json_to_csv.py` to convert them to CSV for inspection.

---

#### Step 2: Edit the CSV file

Open the exported CSV in Excel, Google Sheets, or any spreadsheet editor.

**To make changes:**
- Find the rows for files you want to update
- Use the `restricted_new` and `file_access_request_new` columns to specify the new values
- Leave blank any rows you do NOT want to change

**Accepted values:**
- `true`, `false`
- `yes`, `no`
- `1`, `0`

**Example:**

| doi | file_id | file_name | restricted | restricted_new | file_access_request | file_access_request_new |
|-----|---------|-----------|------------|----------------|---------------------|-------------------------|
| 10.5683/SP3/ABC123 | 12345 | data.csv | true | false | false | true |
| 10.5683/SP3/ABC123 | 12346 | readme.pdf | false | | true | |

In this example:
- File 12345 will be unrestricted and have file access requests enabled
- File 12346 will not be changed (blank `_new` columns)

---

#### Step 3: Generate updated dataset JSON files

Run `update_json_from_csv.py` to convert your edited CSV back into dataset JSON files:

```bash
python3 update_json_from_csv.py /Users/yourname/downloads/dataset_files.csv --json-dir /Users/yourname/downloads/dataset_jsons
```

**What this does:**
- Reads the edited CSV file
- Creates or updates the `dataset_jsons/` directory
- Generates JSON files for each dataset with updated `restricted` and `fileAccessRequest` values
- Preserves all existing metadata (titles, descriptions, authors, etc.)
- Applies values from the `_new` columns only; ignores rows with blank `_new` columns

**Output:**
- JSON files named like: `dataset_10.5683_SP3_ABC123.json`
- Each file contains the full dataset structure with updated file metadata

---

#### Step 4a: Preview changes with a dry run

Before pushing to the server, test the changes with `--dry-run`:

```bash
python3 push_json_to_dataverse.py --server-url "https://demo.borealisdata.ca" --api-key "YOUR_API_KEY" --json-dir /Users/yourname/downloads/dataset_jsons --dry-run
```

**What this shows:**
- All the file updates that will be applied
- File IDs being updated
- New restriction and file access request values
- Any errors or warnings

If the output looks correct, proceed to Step 4b.

---

#### Step 4b: Push changes to Borealis/Dataverse

Once the dry run is verified, apply the changes to the server:

```bash
python3 push_json_to_dataverse.py --server-url "https://demo.borealisdata.ca" --api-key "YOUR_API_KEY" --json-dir /Users/yourname/downloads/dataset_jsons
```

**What this does:**
- Connects to your Borealis/Dataverse instance
- Updates file metadata for each file in the JSON files
- Applies both `restricted` and `fileAccessRequest` changes
- Provides feedback on each file (success/failure)
- Returns a summary of all updates

---

### Single Dataset Update (1-Step Workflow)

For testing, troubleshooting, or updating a single dataset, use `push_single_dataset.py`:

```bash
python3 push_single_dataset.py --json-path /path/to/dataset.json --server-url "https://demo.borealisdata.ca" --api-key "YOUR_API_KEY" --dry-run
```

Or run interactively:

```bash
python3 push_single_dataset.py
```

This will prompt you for:
- Server URL (default: https://demo.borealisdata.ca)
- API Key
- JSON file path

**What this does:**
- Takes a single dataset JSON file (generated from Step 3 or exported from Dataverse)
- Updates file metadata directly on the server
- Handles both `restricted` and `fileAccessRequest` updates
- Supports the same error handling as the bulk script
- Works with both JSON structures: `files` at top level or nested in `datasetVersion.files`

**Flags:**
- `--server-url`: Dataverse server URL (can be omitted to be prompted)
- `--api-key`: API authentication key (can be omitted to be prompted)
- `--json-path`: Path to the dataset JSON file (can be omitted to be prompted)
- `--dry-run`: Show what would be changed without making updates


## Notes and troubleshooting

- The script only updates file records that contain `restricted` or `fileAccessRequest` values.
- If a dataset file does not include either field, it is skipped.
- Use `--dry-run` every time before real execution.
- **File restriction updates (`restricted` field)**: Some servers (like demo.borealisdata.ca) may not support individual file restrict/unrestrict operations. If you see `404` errors for `/unrestrict`, this is a server limitation, not a script issue. File restriction changes may not work on all Dataverse instances.
- **File access request updates (`fileAccessRequest` field)**: These work reliably across all Dataverse/Borealis servers. The script uses proper multipart form-data encoding to avoid `415 Unsupported Media Type` errors.
- **"Already restricted/unrestricted" messages**: These are treated as successes (no change needed) rather than errors.
- For production use, test with `--dry-run` first and verify your server supports the required endpoints.

### Server Compatibility Notes

**Demo Borealis (demo.borealisdata.ca)**:
- ✅ **Restrict files**: Works (can change unrestricted → restricted)
- ❌ **Unrestrict files**: Not supported (404 error - endpoint missing)
- ✅ **File access requests**: Works perfectly

**Production Borealis/Dataverse**:
- ✅ **Restrict files**: Should work
- ✅ **Unrestrict files**: Should work (if server supports the endpoint)
- ✅ **File access requests**: Works reliably

If you need to unrestrict files on demo.borealisdata.ca, you'll need to do it manually through the web interface.


## Script Reference

### Collection-Level Scripts

#### `collection_to_csv.py`
**Purpose:** Export collection metadata to CSV and optionally save dataset JSON files locally.

**Main command:**
```bash
python3 collection_to_csv.py --server-url URL --collection-alias ALIAS --api-key KEY --output FILE.csv --save-json --json-dir DIR/
```

**Key features:**
- Fetches all datasets from a collection directly from your Borealis/Dataverse server
- Exports file metadata as CSV with current restriction and file access request status
- `--save-json`: Optionally downloads full dataset JSON files for reference or manual editing
- `--json-dir`: Directory to save dataset JSONs (useful for Step 3 of the workflow)

**Output:**
- CSV file with columns: `doi`, `dataset_title`, `file_id`, `file_name`, `restricted`, `file_access_request`
- Optional: Dataset JSON files in the specified directory

---

#### `update_json_from_csv.py`
**Purpose:** Convert edited CSV back into dataset JSON files with updated metadata.

**Main command:**
```bash
python3 update_json_from_csv.py CSVFILE.csv --json-dir DIR/
```

**Key features:**
- Reads edited CSV file with `_new` columns
- Creates or updates dataset JSON files with the changes
- Preserves all existing metadata (titles, authors, descriptions, etc.)
- Only applies values from `_new` columns; blank values mean no change
- Handles multiple files in one CSV

**Output:**
- Dataset JSON files in the specified directory, ready for pushing to Dataverse

---

#### `push_json_to_dataverse.py`
**Purpose:** Push all updated dataset JSON files to your Borealis/Dataverse server.

**Main command:**
```bash
python3 push_json_to_dataverse.py --server-url URL --api-key KEY --json-dir DIR/ [--dry-run]
```

**Key features:**
- Uses proper multipart form-data encoding for `fileAccessRequest` updates
- Supports both JSON structures: `files` at top level or nested in `datasetVersion.files`
- Handles "already restricted/unrestricted" responses as successes (no change needed)
- Comprehensive error reporting and feedback
- `--dry-run`: Test changes without modifying the server

**Output:**
- For each file: success message or error details
- Summary: Files processed, changes applied, errors encountered

---

### Single Dataset Scripts

#### `push_single_dataset.py`
**Purpose:** Push a single dataset JSON file to Dataverse for testing or individual updates.

**Interactive mode:**
```bash
python3 push_single_dataset.py
```

**Command-line mode:**
```bash
python3 push_single_dataset.py --server-url URL --api-key KEY --json-path FILE.json [--dry-run]
```

**Key features:**
- Best for testing or updating individual datasets
- Interactive prompts if arguments not provided
- Supports both `restricted` and `fileAccessRequest` updates simultaneously
- Same error handling and encoding as the bulk script
- `--dry-run`: Preview changes without applying them

**Arguments:**
- `--server-url`: Dataverse server URL
- `--api-key`: API authentication key
- `--json-path`: Path to a single dataset JSON file
- `--dry-run`: Show what would be changed (optional)

**Output:**
- For each file: success or error message
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

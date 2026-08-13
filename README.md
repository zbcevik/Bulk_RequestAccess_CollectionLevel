# Dataverse Bulk File-Access Tools

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)

Python tools for reviewing and updating the `restricted` and
`fileAccessRequest` settings of files across a Dataverse collection.

> [!CAUTION]
> Apply mode changes access settings on a live Dataverse server. Export and
> back up the source JSON, review the generated CSV, run preview mode, and test
> against a non-production Dataverse instance before using `--apply`.

## Supported environment

- Python 3.9 through 3.13 (covered by the repository CI matrix)
- A Dataverse-compatible API and an account permitted to read the collection
  and change file restrictions and access-request settings
- HTTPS for authenticated remote servers; HTTP is accepted only for localhost

Dataverse deployments can differ by version and local configuration. No exact
server version is certified by this project yet. Confirm the endpoints against
your institution's test or demo server before production use.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

For development:

```bash
python3 -m pip install -r requirements-dev.txt
```

## Configuration and API-token setup

The repository includes `config.sample.ini`. Copy it to the ignored local
configuration file and insert your own settings:

```bash
cp config.sample.ini config.ini
chmod 600 config.ini
```

```ini
[dataverse]
server_url = https://demo.borealisdata.ca
api_token = YOUR_API_TOKEN
collection_alias = your-collection-alias

[files]
output_csv = dataset_files.csv
json_dir = dataset_jsons
json_path = examples/sample_updated_dataset.json
```

`config.ini` is deliberately excluded by `.gitignore`; never commit or share
it. `config.sample.ini` contains placeholders only and is safe to publish.
Command-line values override configuration values. If `api_token` is missing
or still equals `YOUR_API_TOKEN`, the scripts request it through a hidden
prompt. `--api-key` remains available for compatibility but is discouraged
because it can appear in shell history and process listings. Use `--config`
to select a differently named INI file.

## Primary workflow

### 1. Export collection data

```bash
python3 dataset_access_tools/collection_to_csv.py \
  --save-json \
  --config config.ini
```

This creates an editable CSV and one source JSON export per dataset.

### 2. Back up the source JSON

Before editing or generating updates, make a separate backup:

```bash
cp -R dataset_jsons dataset_jsons.backup
```

Do not commit either directory; generated dataset JSON may contain real names,
filenames, contact details, identifiers, or other production metadata.

### 3. Review the CSV

The required columns are:

- `doi`
- `file_id`
- `file_name`
- `restricted_new`
- `file_access_request_new`

Accepted update values are `true`/`false`, `yes`/`no`, and `1`/`0`. Leave an
update field blank to keep that setting unchanged. Unknown values, missing
columns, missing datasets, and missing file IDs are errors.

See [sample_dataset_files.csv](examples/sample_dataset_files.csv) for dummy
input data.

### 4. Apply CSV values to the local JSON

```bash
python3 dataset_access_tools/update_json_from_csv.py \
  dataset_files.csv \
  --config config.ini
```

The updater modifies existing exports only. It will not create a dataset or
file record when the CSV does not match the JSON. Each dataset is validated
before it is written, and writes use a temporary file followed by replacement.

Supported file-list locations are:

- `files`
- `latestVersion.files`
- `datasetVersion.files`

### 5. Preview the server changes

Preview mode is the default and performs no update requests:

```bash
python3 dataset_access_tools/push_json_to_dataverse.py \
  --config config.ini
```

The older explicit `--dry-run` spelling is also accepted by the bulk command.

### 6. Apply the reviewed changes

Only add `--apply` after reviewing the preview and confirming the target server:

```bash
python3 dataset_access_tools/push_json_to_dataverse.py \
  --config config.ini \
  --apply
```

Apply mode prints the target server and input count, then requires you to type
`APPLY`. For deliberate non-interactive automation, use `--apply --yes`. The
command exits unsuccessfully if confirmation is declined, no JSON files are
found, or any dataset/update fails.

## Single-dataset workflow

`push_single_dataset.py` is an optional troubleshooting tool. It also previews
by default and requires `--apply` for changes:

```bash
python3 dataset_access_tools/push_single_dataset.py \
  --config config.ini
```

## Script status

Primary supported workflow:

- `collection_to_csv.py` — export a collection to CSV and JSON
- `update_json_from_csv.py` — validate and apply reviewed CSV values locally
- `push_json_to_dataverse.py` — preview or apply the JSON changes

Supported utilities:

- `json_folder_to_csv.py` — convert a directory of existing exports to the
  standard editable CSV
- `push_single_dataset.py` — preview or apply one dataset export

Legacy-compatible utility:

- `json_to_csv.py` — convert explicitly named JSON files; new workflows should
  normally use `json_folder_to_csv.py`

## Output and recovery

Normal output reports datasets/files processed, proposed or applied changes,
and failures. HTTP response bodies are not printed because they may include
sensitive server details. Direct metadata requests time out after 30 seconds
and do not follow redirects.

If local JSON was updated incorrectly, restore `dataset_jsons` from
`dataset_jsons.backup`, correct the CSV, and regenerate the local changes. If
incorrect settings were already applied to the server, restore the desired
values in the CSV/JSON, preview again, and apply a corrective run. This tool
does not provide an automatic server-side rollback.

## Testing and quality checks

```bash
python3 -m pytest
python3 -m ruff check .
```

Tests use dummy data and mocked HTTP calls; they must never connect to a live
Dataverse server. GitHub Actions runs tests, linting, CodeQL, dependency update
checks, and secret scanning.

## Security

Do not open a public issue containing a token, credential, private dataset
metadata, or vulnerability details. Follow [SECURITY.md](SECURITY.md).

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md). This project is licensed under the
[MIT License](LICENSE).

# Borealis/Dataverse Bulk Request Access Collection Level

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)
[![CI](https://github.com/zbcevik/Bulk_RequestAccess_CollectionLevel/actions/workflows/ci.yml/badge.svg)](https://github.com/zbcevik/Bulk_RequestAccess_CollectionLevel/actions/workflows/ci.yml)
[![CodeQL](https://github.com/zbcevik/Bulk_RequestAccess_CollectionLevel/actions/workflows/codeql.yml/badge.svg)](https://github.com/zbcevik/Bulk_RequestAccess_CollectionLevel/actions/workflows/codeql.yml)

This is a python tool for reviewing and updating the `restricted` and
`fileAccessRequest` settings of files across a Borealis/Dataverse collection.

> [!CAUTION]
> Review the generated CSV, run preview mode, and test
> against demo.borealisdata.ca before using `--apply`.

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

The single requirements file includes the runtime libraries and the lightweight
test/lint tools used by this repository.

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
changes_csv = dataset_files.csv
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

`file_access_request_new` is a file-by-file review field in the CSV, but
Dataverse exposes Request Access as a dataset-wide policy. After applying the
file rows locally, the updater synchronizes the JSON's dataset-level
`fileAccessRequest` value:

- if at least one restricted file has `fileAccessRequest: false`, dataset-level
  Request Access becomes `false`;
- if all restricted files allow requests, it becomes `true`;
- unrestricted files do not affect the calculation.

The dataset-level field is beside the `license` object in `latestVersion` or
`datasetVersion`; it is not inside the license object. The updater may therefore
report zero changed file records but one synchronized dataset.

Supported file-list locations are:

- `files`
- `latestVersion.files`
- `datasetVersion.files`

### 5. Preview the server changes

The push command reads `changes_csv` to identify explicit requests and validates
them against the JSON directory. Blank `restricted_new` and
`file_access_request_new` cells never produce API requests. Preview mode is the
default and performs no update requests:

```bash
python3 dataset_access_tools/push_json_to_dataverse.py \
  --config config.ini
```

The preview must list exactly the rows you changed in the CSV. If it lists more,
stop and do not use `--apply`. For access-request changes it also prints one
dataset-level line, including the numeric dataset ID, for example:

```text
PREVIEW: dataset=FK2/EXAMPLE id=12345 -> allowAccessRequest=False
```

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

Restriction updates use Dataverse's `/api/files/{id}/restrict` endpoint with an
explicit `true` or `false` request body. Request Access updates use
`/api/access/{dataset-id}/allowAccessRequest`; the numeric dataset ID is read
from the exported JSON for compatibility with installations that do not accept
the `:persistentId` route. If an older or simplified JSON export has a DOI but
no numeric `id` or `datasetId`, apply mode performs a read-only DOI lookup and
then uses the returned numeric ID. Preview mode reports that the lookup is
pending but makes no network request. Request Access is sent once per affected
dataset, not once per file. Existing JSON values are never treated as requested
changes.

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
and failures. For failed API calls, only a short Dataverse error message is
shown; arbitrary response bodies are not dumped. Direct requests time out after
30 seconds and do not follow redirects.

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

Tests use dummy data and mocked HTTP calls; they must never connect to a borealisdata.ca. GitHub Actions runs tests, linting, CodeQL, dependency update
checks, and secret scanning.

## Security

Do not open a public issue containing a token, credential, private dataset
metadata, or vulnerability details. If a token is exposed, revoke it immediately
and create a replacement; deleting the latest copy does not remove it from Git
history or third-party caches.

Before publishing changes, confirm that `git status` does not list
`config.ini`, generated CSV files, dataset JSON exports, or `.DS_Store`. Keep
Gitleaks and CodeQL enabled: they detect accidentally committed credentials and
security-sensitive code patterns; they do not replace `config.ini` and do not
need access to its ignored local contents.

For the GitHub account itself, enable two-factor authentication, review and
delete unused personal access tokens and SSH keys, and keep the commit email set
to GitHub's private `users.noreply.github.com` address. 

## Repository support files

- `.github/` contains GitHub-only automation: tests, linting, CodeQL, Gitleaks,
  and monthly dependency updates. It is hidden in normal macOS Finder views
  because its name begins with a dot, but GitHub reads it automatically. It is
  not required to run the scripts locally; it is retained to test and protect
  changes before they reach `main`.
- `pyproject.toml` identifies the project as an installable Python package,
  defines its command-line entry points, Python version, dependencies, and
  shared pytest/Ruff settings. It avoids scattering this configuration across
  several extra files.
- `requirements.txt` is the one-file installation list for local use and CI.

## License

[MIT License](LICENSE).

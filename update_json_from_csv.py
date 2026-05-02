#!/usr/bin/env python3
"""Update dataset JSON files with new restricted and file access request values from CSV."""

import argparse
import csv
import json
import sys
from pathlib import Path


def parse_bool(value):
    if value is None:
        return None
    value = str(value).strip().lower()
    if value in ('true', '1', 'yes'):
        return True
    if value in ('false', '0', 'no'):
        return False
    return None


def sanitize_filename(doi):
    safe = doi.replace('doi:', '').replace('/', '_').replace(':', '_')
    return f"dataset_{safe}.json"


def load_csv(csv_path):
    """Load CSV and return list of dicts."""
    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def ensure_json_dir(json_dir):
    if not json_dir.exists():
        json_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created JSON directory: {json_dir}")


def find_file_record(data, file_id, filename):
    for file_record in data.get('files', []):
        file_item = file_record.get('dataFile', {})
        if str(file_item.get('id')) == str(file_id):
            return file_record
        if file_item.get('filename') == filename:
            return file_record
        if file_record.get('label') == filename:
            return file_record
    return None


def create_file_record(row):
    return {
        'label': row.get('file_name', ''),
        'restricted': parse_bool(row.get('restricted')) or False,
        'dataFile': {
            'id': int(row['file_id']) if row.get('file_id') else None,
            'filename': row.get('file_name', ''),
            'fileAccessRequest': parse_bool(row.get('file_access_request')) or False,
        },
    }


def update_dataset_data(data, updates):
    if 'files' not in data:
        data['files'] = []

    changed = False
    for row in updates:
        file_id = row.get('file_id')
        if not file_id:
            continue

        file_record = find_file_record(data, file_id, row.get('file_name'))
        if file_record is None:
            file_record = create_file_record(row)
            data['files'].append(file_record)
            changed = True

        file_item = file_record.setdefault('dataFile', {})
        file_item.setdefault('id', int(file_id) if file_id else None)
        file_item.setdefault('filename', row.get('file_name', ''))

        new_restricted = parse_bool(row.get('restricted_new'))
        if new_restricted is not None and file_record.get('restricted') != new_restricted:
            file_record['restricted'] = new_restricted
            changed = True

        new_access_request = parse_bool(row.get('file_access_request_new'))
        if new_access_request is not None and file_item.get('fileAccessRequest') != new_access_request:
            file_item['fileAccessRequest'] = new_access_request
            changed = True

    return changed


def save_dataset_json(json_path, data):
    with json_path.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Saved {json_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Update dataset JSON files with new values from CSV."
    )
    parser.add_argument(
        'csv_file',
        help='Path to the CSV file with updated values.'
    )
    parser.add_argument(
        '--json-dir',
        default='dataset_jsons',
        help='Directory containing dataset JSON files or where new JSONs will be created.'
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    json_dir = Path(args.json_dir)

    if not csv_path.exists():
        sys.exit(f"CSV file not found: {csv_path}")

    ensure_json_dir(json_dir)

    rows = load_csv(csv_path)
    print(f"Loaded {len(rows)} rows from CSV")

    updates_by_doi = {}
    titles_by_doi = {}
    for row in rows:
        doi = row.get('doi', '').strip()
        if not doi:
            continue
        updates_by_doi.setdefault(doi, []).append(row)
        titles_by_doi.setdefault(doi, row.get('dataset_title', '').strip())

    updated_count = 0
    created_count = 0

    for doi, updates in updates_by_doi.items():
        json_filename = sanitize_filename(doi)
        json_path = json_dir / json_filename

        if json_path.exists():
            try:
                with json_path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as exc:
                print(f"Error reading {json_path}: {exc}")
                continue
        else:
            data = {
                'persistentId': doi,
                'title': titles_by_doi.get(doi, ''),
                'citation': {'fields': [{'typeName': 'title', 'value': titles_by_doi.get(doi, '')}]},
                'files': [],
            }
            created_count += 1
            print(f"Creating new dataset JSON for {doi}: {json_path}")

        if update_dataset_data(data, updates):
            save_dataset_json(json_path, data)
            updated_count += 1

    print(f"Created {created_count} dataset JSON files")
    print(f"Updated {updated_count} dataset JSON files")


if __name__ == '__main__':
    main()

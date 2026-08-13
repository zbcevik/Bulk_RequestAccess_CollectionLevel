import csv
import json

import pytest

from dataset_access_tools.dataverse_json import DatasetValidationError
from dataset_access_tools.update_json_from_csv import (
    load_csv,
    process_updates,
    sanitize_filename,
    update_dataset_data,
)


def dataset(shape="files"):
    record = {
        "label": "sample.csv",
        "restricted": False,
        "dataFile": {"id": 101, "filename": "sample.csv", "fileAccessRequest": False},
    }
    data = {"persistentId": "doi:10.0000/EXAMPLE", "title": "Example"}
    if shape == "files":
        data["files"] = [record]
    else:
        data[shape] = {"files": [record]}
    return data


def add_file(data, *, file_id, restricted, access_request):
    record = {
        "label": f"sample-{file_id}.csv",
        "restricted": restricted,
        "dataFile": {
            "id": file_id,
            "filename": f"sample-{file_id}.csv",
            "fileAccessRequest": access_request,
        },
    }
    records = data.get("files") or data.get("latestVersion", {}).get("files")
    records.append(record)


def update_row(file_id="101", restricted="true", access="true"):
    return {
        "doi": "doi:10.0000/EXAMPLE",
        "file_id": file_id,
        "file_name": "sample.csv",
        "restricted_new": restricted,
        "file_access_request_new": access,
    }


@pytest.mark.parametrize("shape", ["files", "latestVersion", "datasetVersion"])
def test_updates_each_supported_shape(shape):
    data = dataset(shape)
    assert update_dataset_data(data, [(2, update_row())]) == 1
    records = data[shape]["files"] if shape != "files" else data["files"]
    assert records[0]["restricted"] is True
    assert records[0]["dataFile"]["fileAccessRequest"] is True


@pytest.mark.parametrize("shape", ["files", "latestVersion", "datasetVersion"])
def test_restricted_file_without_access_request_disables_dataset_request_access(shape):
    data = dataset(shape)
    version = data if shape == "files" else data[shape]
    version["fileAccessRequest"] = True

    row = update_row(restricted="true", access="false")
    assert update_dataset_data(data, [(2, row)]) == 1

    assert version["fileAccessRequest"] is False


def test_unrestricted_file_without_access_request_does_not_disable_dataset_request_access():
    data = dataset("latestVersion")
    data["latestVersion"]["fileAccessRequest"] = True
    add_file(data, file_id=202, restricted=True, access_request=True)

    row = update_row(restricted="false", access="false")
    assert update_dataset_data(data, [(2, row)]) == 0

    assert data["latestVersion"]["fileAccessRequest"] is True


def test_one_of_multiple_restricted_files_disables_dataset_request_access():
    data = dataset("latestVersion")
    data["latestVersion"]["fileAccessRequest"] = True
    add_file(data, file_id=202, restricted=True, access_request=True)

    row = update_row(restricted="true", access="false")
    assert update_dataset_data(data, [(2, row)]) == 1

    assert data["latestVersion"]["fileAccessRequest"] is False


def test_missing_file_is_rejected_without_partial_update():
    data = dataset()
    rows = [(2, update_row()), (3, update_row(file_id="999", restricted="false"))]
    with pytest.raises(DatasetValidationError, match="not in the dataset JSON"):
        update_dataset_data(data, rows)
    assert data["files"][0]["restricted"] is False


def test_csv_requires_expected_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("doi,file_id\ndoi:10.0000/EXAMPLE,101\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="missing required"):
        load_csv(path)


def test_process_updates_existing_json(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    json_path = json_dir / sanitize_filename("doi:10.0000/EXAMPLE")
    json_path.write_text(json.dumps(dataset("datasetVersion")), encoding="utf-8")

    csv_path = tmp_path / "updates.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(update_row()))
        writer.writeheader()
        writer.writerow(update_row())

    assert process_updates(csv_path, json_dir) == (1, 1)
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["datasetVersion"]["files"][0]["restricted"] is True


def test_process_updates_finds_dataset_by_identifier_not_filename(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    json_path = json_dir / "arbitrary-export-name.json"
    json_path.write_text(json.dumps(dataset()), encoding="utf-8")
    csv_path = tmp_path / "updates.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(update_row()))
        writer.writeheader()
        writer.writerow(update_row())
    assert process_updates(csv_path, json_dir) == (1, 1)
    assert json.loads(json_path.read_text(encoding="utf-8"))["files"][0]["restricted"] is True


def test_process_updates_does_not_create_missing_dataset(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    unrelated = dataset()
    unrelated["persistentId"] = "doi:10.0000/UNRELATED"
    (json_dir / "unrelated.json").write_text(json.dumps(unrelated), encoding="utf-8")
    csv_path = tmp_path / "updates.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(update_row()))
        writer.writeheader()
        writer.writerow(update_row())
    with pytest.raises(DatasetValidationError, match="will not create"):
        process_updates(csv_path, json_dir)


def test_missing_file_id_is_rejected():
    with pytest.raises(DatasetValidationError, match="has no file_id"):
        update_dataset_data(dataset(), [(2, update_row(file_id=""))])


def test_invalid_csv_boolean_is_rejected(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    (json_dir / "dataset.json").write_text(json.dumps(dataset()), encoding="utf-8")
    csv_path = tmp_path / "updates.csv"
    row = update_row(restricted="maybe")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(DatasetValidationError, match="Unsupported boolean"):
        process_updates(csv_path, json_dir)


def test_sanitize_filename_handles_doi_prefix_and_separator():
    assert sanitize_filename("doi:10.0000/EXAMPLE") == "dataset_10.0000_EXAMPLE.json"

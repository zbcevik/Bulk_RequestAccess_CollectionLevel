import copy

import pytest

from dataset_access_tools.dataverse_json import (
    DatasetValidationError,
    dataset_to_rows,
    get_file_records,
    parse_optional_bool,
    validate_dataset,
)


def dataset(shape="root"):
    file_records = [
        {
            "label": "sample.csv",
            "restricted": False,
            "dataFile": {"id": 101, "filename": "sample.csv", "fileAccessRequest": False},
        }
    ]
    data = {"persistentId": "doi:10.0000/EXAMPLE", "title": "Example"}
    if shape == "root":
        data["files"] = file_records
    else:
        data[shape] = {"files": file_records}
    return data


@pytest.mark.parametrize(
    ("shape", "path"),
    [("root", "files"), ("latestVersion", "latestVersion.files"), ("datasetVersion", "datasetVersion.files")],
)
def test_supported_file_locations(shape, path):
    records, actual_path = get_file_records(dataset(shape))
    assert actual_path == path
    assert records[0]["dataFile"]["id"] == 101


def test_dataset_to_rows_is_consistent_across_shapes():
    expected = dataset_to_rows(dataset("root"))
    assert dataset_to_rows(dataset("latestVersion")) == expected
    assert dataset_to_rows(dataset("datasetVersion")) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("yes", True), ("1", True), ("false", False), ("no", False), ("0", False), ("", None)],
)
def test_parse_optional_bool(value, expected):
    assert parse_optional_bool(value) is expected


def test_invalid_boolean_is_rejected():
    with pytest.raises(DatasetValidationError, match="Unsupported boolean"):
        parse_optional_bool("maybe")


def test_missing_file_list_is_rejected():
    data = copy.deepcopy(dataset())
    data.pop("files")
    with pytest.raises(DatasetValidationError, match="no supported file list"):
        validate_dataset(data)

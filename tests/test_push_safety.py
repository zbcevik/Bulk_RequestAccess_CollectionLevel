import csv
import json
import sys

import httpx
import pytest

from dataset_access_tools import push_json_to_dataverse
from dataset_access_tools.dataverse_json import DatasetValidationError
from dataset_access_tools.security_utils import (
    put_dataset_access_request,
    put_file_restriction,
)


class FakeNativeApi:
    base_url = "https://example.test"
    api_token = "placeholder"


def dataset(restricted=True, access_request=False):
    return {
        "id": 777,
        "persistentId": "doi:10.0000/EXAMPLE",
        "fileAccessRequest": access_request,
        "files": [
            {
                "restricted": restricted,
                "dataFile": {
                    "id": 101,
                    "filename": "sample.csv",
                    "fileAccessRequest": access_request,
                },
            },
            {
                "restricted": True,
                "dataFile": {
                    "id": 102,
                    "filename": "unchanged.csv",
                    "fileAccessRequest": False,
                },
            },
        ],
    }


def write_csv(path, restricted_new="", access_new=""):
    fields = [
        "doi",
        "file_id",
        "file_name",
        "restricted_new",
        "file_access_request_new",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "doi": "doi:10.0000/EXAMPLE",
                "file_id": "101",
                "file_name": "sample.csv",
                "restricted_new": restricted_new,
                "file_access_request_new": access_new,
            }
        )
        writer.writerow(
            {
                "doi": "doi:10.0000/EXAMPLE",
                "file_id": "102",
                "file_name": "unchanged.csv",
                "restricted_new": "",
                "file_access_request_new": "",
            }
        )


def test_blank_update_cells_produce_no_actions(tmp_path):
    path = tmp_path / "changes.csv"
    write_csv(path)
    with pytest.raises(DatasetValidationError, match="contains no nonblank"):
        push_json_to_dataverse.load_explicit_changes(path)


def test_only_nonblank_update_row_becomes_action(tmp_path):
    path = tmp_path / "changes.csv"
    write_csv(path, restricted_new="true")
    changes = push_json_to_dataverse.load_explicit_changes(path)
    assert len(changes) == 1
    assert changes[0]["file_id"] == "101"
    assert changes[0]["restricted"] is True
    assert changes[0]["file_access_request"] is None


def test_csv_change_must_match_updated_json(tmp_path):
    path = tmp_path / "changes.csv"
    write_csv(path, restricted_new="true")
    changes = push_json_to_dataverse.load_explicit_changes(path)
    with pytest.raises(DatasetValidationError, match="does not match"):
        push_json_to_dataverse.validate_changes_against_json(
            changes,
            {"doi:10.0000/EXAMPLE": (tmp_path / "dataset.json", dataset(restricted=False))},
        )


def test_restrict_request_uses_restrict_endpoint_and_true_body(monkeypatch):
    captured = {}

    def fake_put(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(200)

    monkeypatch.setattr("dataset_access_tools.security_utils.httpx.put", fake_put)
    response = put_file_restriction(
        "https://example.test/api/files/101/restrict", "token", True
    )
    assert response.status_code == 200
    assert captured["url"].endswith("/api/files/101/restrict")
    assert captured["content"] == "true"
    assert captured["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert captured["headers"]["X-Dataverse-key"] == "token"
    assert captured["follow_redirects"] is False


def test_unrestrict_uses_same_endpoint_with_false_body(monkeypatch):
    captured = {}

    def fake_put(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(200)

    monkeypatch.setattr("dataset_access_tools.security_utils.httpx.put", fake_put)
    put_file_restriction("https://example.test/api/files/101/restrict", "token", False)
    assert captured["url"].endswith("/api/files/101/restrict")
    assert captured["content"] == "false"
    assert "/unrestrict" not in captured["url"]


def test_dataset_access_request_uses_dataset_endpoint_and_boolean_body(monkeypatch):
    captured = {}

    def fake_put(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(200)

    monkeypatch.setattr("dataset_access_tools.security_utils.httpx.put", fake_put)
    put_dataset_access_request(
        "https://example.test/api/access/:persistentId/allowAccessRequest", "token", False
    )
    assert captured["content"] == "false"
    assert captured["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_access_policy_is_read_once_per_affected_dataset(tmp_path):
    changes = [
        {"doi": "doi:10.0000/EXAMPLE", "file_access_request": False},
        {"doi": "doi:10.0000/EXAMPLE", "file_access_request": True},
    ]
    index = {"doi:10.0000/EXAMPLE": (tmp_path / "dataset.json", dataset())}
    assert push_json_to_dataverse.dataset_access_policies(changes, index) == [
        ("doi:10.0000/EXAMPLE", "777", False)
    ]


def test_access_policy_allows_json_without_numeric_dataset_id(tmp_path):
    data = dataset()
    del data["id"]
    changes = [{"doi": "doi:10.0000/EXAMPLE", "file_access_request": False}]
    index = {"doi:10.0000/EXAMPLE": (tmp_path / "dataset.json", data)}
    assert push_json_to_dataverse.dataset_access_policies(changes, index) == [
        ("doi:10.0000/EXAMPLE", None, False)
    ]


def test_missing_dataset_id_is_resolved_from_doi(monkeypatch):
    class LookupApi(FakeNativeApi):
        def get_dataset(self, persistent_id, is_pid=False):
            assert persistent_id == "doi:10.0000/EXAMPLE"
            assert is_pid is True
            return {"status": "OK", "data": {"id": 888}}

    calls = []

    def fake_update(url, token, allowed):
        calls.append((url, token, allowed))
        return httpx.Response(200)

    monkeypatch.setattr(push_json_to_dataverse, "put_dataset_access_request", fake_update)
    assert push_json_to_dataverse.apply_dataset_access_policy(
        LookupApi(), "doi:10.0000/EXAMPLE", None, False
    ) == (1, 0)
    assert calls == [
        ("https://example.test/api/access/888/allowAccessRequest", "placeholder", False)
    ]


def test_dataset_id_lookup_accepts_dataset_id_in_version():
    class LookupApi(FakeNativeApi):
        def get_dataset(self, persistent_id, is_pid=False):
            return {"data": {"latestVersion": {"datasetId": 889}}}

    assert push_json_to_dataverse.resolve_dataset_id(
        LookupApi(), "doi:10.0000/EXAMPLE"
    ) == "889"


def test_dataset_access_url_uses_numeric_dataset_id():
    assert push_json_to_dataverse.dataset_access_request_url(FakeNativeApi(), "777") == (
        "https://example.test/api/access/777/allowAccessRequest"
    )


def test_apply_change_sends_only_requested_field(monkeypatch):
    calls = []

    def fake_restrict(url, token, value):
        calls.append(("restricted", url, value))
        return httpx.Response(200)

    monkeypatch.setattr(push_json_to_dataverse, "put_file_restriction", fake_restrict)
    change = {
        "doi": "doi:10.0000/EXAMPLE",
        "file_id": "101",
        "file_name": "sample.csv",
        "restricted": True,
        "file_access_request": None,
    }
    assert push_json_to_dataverse.apply_change(FakeNativeApi(), change) == (1, 0)
    assert calls == [("restricted", "https://example.test/api/files/101/restrict", True)]


def test_file_access_change_is_not_sent_to_file_metadata_endpoint(monkeypatch):
    def forbidden_restrict(*args, **kwargs):
        raise AssertionError("No restriction was requested")

    monkeypatch.setattr(push_json_to_dataverse, "put_file_restriction", forbidden_restrict)
    change = {
        "doi": "doi:10.0000/EXAMPLE",
        "file_id": "101",
        "file_name": "sample.csv",
        "restricted": None,
        "file_access_request": False,
    }
    assert push_json_to_dataverse.apply_change(FakeNativeApi(), change) == (0, 0)


def test_preview_never_initializes_api_client(tmp_path, monkeypatch):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    (json_dir / "dataset.json").write_text(json.dumps(dataset()), encoding="utf-8")
    changes_csv = tmp_path / "changes.csv"
    write_csv(changes_csv, restricted_new="true")
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[dataverse]\nserver_url = https://example.test\napi_token = placeholder\n"
        f"[files]\njson_dir = {json_dir}\nchanges_csv = {changes_csv}\n",
        encoding="utf-8",
    )

    class ForbiddenApi:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Preview must not initialize the API client")

    monkeypatch.setattr(push_json_to_dataverse, "NativeApi", ForbiddenApi)
    monkeypatch.setattr(sys, "argv", ["push_json_to_dataverse.py", "--config", str(config_path)])
    assert push_json_to_dataverse.main() == 0


def test_bulk_cli_defaults_to_preview(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["push_json_to_dataverse.py"])
    assert push_json_to_dataverse.parse_args().apply is False

import csv
import json
import sys

import httpx
import pytest

from dataset_access_tools import push_json_to_dataverse
from dataset_access_tools.dataverse_json import DatasetValidationError
from dataset_access_tools.security_utils import post_file_access_request, put_file_restriction


class FakeNativeApi:
    base_url = "https://example.test"
    api_token = "placeholder"


def dataset(restricted=True, access_request=False):
    return {
        "persistentId": "doi:10.0000/EXAMPLE",
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
    assert captured["headers"]["Content-Type"] == "text/plain"
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


def test_apply_change_sends_only_requested_field(monkeypatch):
    calls = []

    def fake_restrict(url, token, value):
        calls.append(("restricted", url, value))
        return httpx.Response(200)

    def forbidden_access(*args, **kwargs):
        raise AssertionError("Blank file_access_request_new must not produce an API request")

    monkeypatch.setattr(push_json_to_dataverse, "put_file_restriction", fake_restrict)
    monkeypatch.setattr(push_json_to_dataverse, "post_file_access_request", forbidden_access)
    change = {
        "doi": "doi:10.0000/EXAMPLE",
        "file_id": "101",
        "file_name": "sample.csv",
        "restricted": True,
        "file_access_request": None,
    }
    assert push_json_to_dataverse.apply_change(FakeNativeApi(), change) == (1, 0)
    assert calls == [("restricted", "https://example.test/api/files/101/restrict", True)]


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


def test_direct_access_request_has_timeout(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200)

    monkeypatch.setattr("dataset_access_tools.security_utils.httpx.post", fake_post)
    post_file_access_request("https://example.test/api/files/101/metadata", "token", True)
    assert captured["timeout"] == 30.0
    assert captured["follow_redirects"] is False

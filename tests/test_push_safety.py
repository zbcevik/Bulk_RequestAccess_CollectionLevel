import json
import sys

import httpx

from dataset_access_tools import push_json_to_dataverse, push_single_dataset
from dataset_access_tools.security_utils import post_file_access_request


class FakeNativeApi:
    base_url = "https://example.test"
    api_token = "placeholder"

    def put_request(self, *args, **kwargs):
        raise AssertionError("Dry-run must not make a network request")


def write_dataset(path):
    path.write_text(
        json.dumps(
            {
                "persistentId": "doi:10.0000/EXAMPLE",
                "files": [
                    {
                        "restricted": True,
                        "dataFile": {"id": 101, "filename": "sample.csv", "fileAccessRequest": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_bulk_dry_run_never_calls_network(tmp_path):
    path = tmp_path / "dataset.json"
    write_dataset(path)
    assert push_json_to_dataverse.push_dataset_json(FakeNativeApi(), path, dry_run=True) == (1, 0)


def test_bulk_cli_defaults_to_preview(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["push_json_to_dataverse.py"])
    args = push_json_to_dataverse.parse_args()
    assert args.apply is False


def test_declined_apply_never_initializes_api_client(tmp_path, monkeypatch):
    write_dataset(tmp_path / "dataset.json")
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[dataverse]\n"
        "server_url = https://example.test\n"
        "api_token = private-placeholder\n"
        "[files]\n"
        f"json_dir = {tmp_path}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "push_json_to_dataverse.py",
            "--config",
            str(config_path),
            "--apply",
        ],
    )
    monkeypatch.setattr(push_json_to_dataverse, "confirm_apply", lambda *args, **kwargs: False)

    class ForbiddenApi:
        def __init__(self, *args, **kwargs):
            raise AssertionError("API client must not be initialized after declined confirmation")

    monkeypatch.setattr(push_json_to_dataverse, "NativeApi", ForbiddenApi)
    assert push_json_to_dataverse.main() == 1


def test_single_dry_run_never_calls_network(tmp_path):
    path = tmp_path / "dataset.json"
    write_dataset(path)
    assert push_single_dataset.push_dataset_json(FakeNativeApi(), path, dry_run=True) == (1, 0, 1)


def test_direct_request_has_timeout_and_does_not_follow_redirects(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200)

    monkeypatch.setattr("dataset_access_tools.security_utils.httpx.post", fake_post)
    response = post_file_access_request("https://example.test/api/files/101/metadata", "token", True)
    assert response.status_code == 200
    assert captured["timeout"] == 30.0
    assert captured["follow_redirects"] is False
    assert captured["headers"] == {"X-Dataverse-key": "token"}


def test_single_unrestrict_uses_unrestrict_endpoint():
    captured = {}

    class RecordingApi(FakeNativeApi):
        def put_request(self, url, **kwargs):
            captured["url"] = url
            return httpx.Response(200)

    push_single_dataset.push_restrict(RecordingApi(), 101, False)
    assert captured["url"].endswith("/api/files/101/unrestrict")

import httpx
import pytest

from dataset_access_tools.security_utils import (
    DataverseRequestError,
    confirm_apply,
    get_api_token,
    get_config_value,
    load_config,
    post_file_access_request,
    validate_server_url,
)


def test_config_token_is_used():
    assert get_api_token(config_token="private-placeholder") == "private-placeholder"


def test_config_file_is_loaded(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text(
        "[dataverse]\nserver_url = https://example.test\napi_token = private-placeholder\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert get_config_value(config, "dataverse", "server_url") == "https://example.test"
    assert get_config_value(config, "dataverse", "api_token") == "private-placeholder"


def test_hidden_prompt_token_is_not_printed(monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt: "private-placeholder")
    assert get_api_token() == "private-placeholder"
    captured = capsys.readouterr()
    assert "private-placeholder" not in captured.out
    assert "private-placeholder" not in captured.err


def test_command_line_warning_does_not_repeat_token(capsys):
    assert get_api_token("private-placeholder") == "private-placeholder"
    captured = capsys.readouterr()
    assert "private-placeholder" not in captured.err
    assert "shell history" in captured.err


def test_unchanged_sample_token_uses_hidden_prompt(monkeypatch):
    monkeypatch.setattr("getpass.getpass", lambda prompt: "prompt-token")
    assert get_api_token(config_token="YOUR_API_TOKEN") == "prompt-token"


def test_explicit_missing_config_is_rejected(tmp_path):
    with pytest.raises(SystemExit, match="Configuration file not found"):
        load_config(tmp_path / "missing.ini")


def test_authenticated_remote_http_is_rejected():
    with pytest.raises(SystemExit, match="Refusing"):
        validate_server_url("http://example.test", "placeholder")


def test_local_http_is_allowed_for_testing():
    assert validate_server_url("http://localhost:8080/", "placeholder") == "http://localhost:8080"


def test_direct_request_timeout_has_safe_error(monkeypatch):
    request = httpx.Request("POST", "https://example.test/api/files/101/metadata")

    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("sensitive upstream detail", request=request)

    monkeypatch.setattr("dataset_access_tools.security_utils.httpx.post", fail)
    with pytest.raises(DataverseRequestError, match="timed out") as captured:
        post_file_access_request(request.url, "token", True)
    assert "sensitive upstream detail" not in str(captured.value)


def test_connection_failure_has_safe_error(monkeypatch):
    request = httpx.Request("POST", "https://example.test/api/files/101/metadata")

    def fail(*args, **kwargs):
        raise httpx.ConnectError("sensitive DNS detail", request=request)

    monkeypatch.setattr("dataset_access_tools.security_utils.httpx.post", fail)
    with pytest.raises(DataverseRequestError, match="Could not connect") as captured:
        post_file_access_request(request.url, "token", True)
    assert "sensitive DNS detail" not in str(captured.value)


def test_apply_requires_exact_confirmation(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "APPLY")
    assert confirm_apply("https://example.test", 2) is True
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert confirm_apply("https://example.test", 2) is False


def test_noninteractive_apply_can_be_explicitly_approved():
    assert confirm_apply("https://example.test", 2, assume_yes=True) is True

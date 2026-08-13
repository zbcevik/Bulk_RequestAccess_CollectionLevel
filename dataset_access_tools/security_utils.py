"""Shared helpers for handling credentials and Dataverse connections safely."""

import configparser
import getpass
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

HTTP_TIMEOUT_SECONDS = 30.0
DEFAULT_CONFIG_PATH = "config.ini"


class DataverseRequestError(RuntimeError):
    """A safe, user-facing error raised for direct Dataverse HTTP failures."""


def confirm_apply(server_url, item_count, assume_yes=False):
    """Require an explicit confirmation before live updates."""
    if assume_yes:
        return True
    print(f"About to apply updates from {item_count} JSON file(s) to {server_url}.")
    response = input("Type APPLY to continue: ").strip()
    return response == "APPLY"


def load_config(config_path=DEFAULT_CONFIG_PATH):
    """Load an ignored INI configuration file, if present."""
    path = Path(config_path)
    parser = configparser.ConfigParser(interpolation=None)
    if path.is_file():
        try:
            with path.open(encoding="utf-8") as handle:
                parser.read_file(handle)
        except configparser.Error as exc:
            raise SystemExit(f"Invalid configuration file {path}: {exc}") from exc
    elif str(path) != DEFAULT_CONFIG_PATH:
        raise SystemExit(f"Configuration file not found: {path}")
    return parser


def get_config_value(config, section, option, default=None):
    """Return a stripped configuration value when it is present."""
    value = config.get(section, option, fallback="").strip()
    return value or default


def get_api_token(command_line_token=None, config_token=None):
    """Get an API token without displaying it during interactive entry."""
    if command_line_token:
        print(
            "Warning: --api-key can expose the token in shell history and process listings. "
            "Prefer config.ini or the hidden prompt.",
            file=sys.stderr,
        )
        return command_line_token

    configured_token = (config_token or "").strip()
    if configured_token and configured_token != "YOUR_API_TOKEN":
        return configured_token

    token = getpass.getpass("API token: ").strip()
    if not token:
        raise SystemExit("An API token is required.")
    return token


def validate_server_url(server_url, api_token=None):
    """Normalize a server URL and prevent credentials from crossing plain HTTP."""
    normalized = server_url.strip().rstrip("/")
    parsed = urlparse(normalized)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("Server URL must be a complete http:// or https:// URL.")

    is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if api_token and parsed.scheme != "https" and not is_local:
        raise SystemExit(
            "Refusing to send an API token over HTTP. Use HTTPS, or use localhost for local testing."
        )

    return normalized


def post_file_access_request(url, api_token, new_value):
    """Send a file-access metadata update with a timeout and safe failures."""
    # Dataverse expects JSON in the multipart jsonData field.
    files = {"jsonData": (None, json.dumps({"fileAccessRequest": new_value}))}
    headers = {"X-Dataverse-key": api_token} if api_token else {}

    try:
        return httpx.post(
            url,
            files=files,
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise DataverseRequestError(
            f"Dataverse request timed out after {HTTP_TIMEOUT_SECONDS:g} seconds."
        ) from exc
    except httpx.RequestError as exc:
        raise DataverseRequestError(
            f"Could not connect to the Dataverse server ({type(exc).__name__})."
        ) from exc


def put_file_restriction(url, api_token, restricted):
    """Restrict or unrestrict one file using Dataverse's boolean request body."""
    headers = {
        "Content-Type": "text/plain",
        **({"X-Dataverse-key": api_token} if api_token else {}),
    }
    try:
        return httpx.put(
            url,
            content="true" if restricted else "false",
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise DataverseRequestError(
            f"Dataverse request timed out after {HTTP_TIMEOUT_SECONDS:g} seconds."
        ) from exc
    except httpx.RequestError as exc:
        raise DataverseRequestError(
            f"Could not connect to the Dataverse server ({type(exc).__name__})."
        ) from exc


def response_error_summary(response):
    """Return status information without printing a potentially sensitive body."""
    status_code = getattr(response, "status_code", "unknown")
    reason = getattr(response, "reason_phrase", "")
    return f"HTTP {status_code}{f' {reason}' if reason else ''}"

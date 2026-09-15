"""Shared parsing and validation for supported Dataverse dataset JSON shapes."""

from typing import Any, Dict, List, Optional, Tuple

VERSION_KEYS = ("latestVersion", "datasetVersion")
CSV_FIELDNAMES = [
    "doi",
    "dataset_title",
    "file_id",
    "file_name",
    "restricted",
    "file_access_request",
    "restricted_new",
    "file_access_request_new",
]


class DatasetValidationError(ValueError):
    """Raised when dataset JSON cannot be updated safely."""


def parse_optional_bool(value: Any) -> Optional[bool]:
    """Parse a supported boolean value; blank values mean no requested change."""
    if value is None or str(value).strip() == "":
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise DatasetValidationError(
        f"Unsupported boolean value {value!r}; use true/false, yes/no, 1/0, or blank."
    )


def get_version_block(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for key in VERSION_KEYS:
        block = data.get(key)
        if isinstance(block, dict):
            return block
    return None


def get_file_records(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """Return the mutable file list and the JSON path where it was found."""
    if isinstance(data.get("files"), list):
        return data["files"], "files"
    for key in VERSION_KEYS:
        block = data.get(key)
        if isinstance(block, dict) and isinstance(block.get("files"), list):
            return block["files"], f"{key}.files"
    raise DatasetValidationError(
        "Dataset JSON has no supported file list (files, latestVersion.files, or datasetVersion.files)."
    )


def get_persistent_id(data: Dict[str, Any]) -> str:
    for key in ("persistentId", "datasetPersistentId", "identifier"):
        value = data.get(key)
        if value:
            return str(value)
    version = get_version_block(data)
    if version:
        for key in ("datasetPersistentId", "persistentId"):
            value = version.get(key)
            if value:
                return str(value)
    persistent_url = data.get("persistentUrl")
    return str(persistent_url) if persistent_url else ""


def get_title(data: Dict[str, Any]) -> str:
    for key in ("title", "datasetName"):
        value = data.get(key)
        if value:
            return str(value)
    version = get_version_block(data) or data
    fields = version.get("metadataBlocks", {}).get("citation", {}).get("fields", [])
    for field in fields:
        if field.get("typeName") == "title" and isinstance(field.get("value"), str):
            return field["value"]
    return ""


def validate_dataset(data: Any, expected_id: str = "") -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise DatasetValidationError("Dataset JSON must contain a JSON object.")
    persistent_id = get_persistent_id(data)
    if not persistent_id:
        raise DatasetValidationError("Dataset JSON is missing a persistent identifier.")
    if expected_id and persistent_id != expected_id:
        raise DatasetValidationError(
            f"Dataset identifier mismatch: CSV has {expected_id!r}, JSON has {persistent_id!r}."
        )
    get_file_records(data)
    return data


def find_file_record(
    file_records: List[Dict[str, Any]], file_id: str, filename: str = ""
) -> Optional[Dict[str, Any]]:
    """Find a file by ID, using filename only for records that have no ID."""
    wanted_id = str(file_id).strip()
    for record in file_records:
        data_file = record.get("dataFile", {})
        record_id = data_file.get("id") or data_file.get("persistentId")
        if record_id is not None and str(record_id) == wanted_id:
            return record

    if filename:
        matches = []
        for record in file_records:
            data_file = record.get("dataFile", {})
            record_id = data_file.get("id") or data_file.get("persistentId")
            record_name = data_file.get("filename") or record.get("label")
            if record_id is None and record_name == filename:
                matches.append(record)
        if len(matches) == 1:
            return matches[0]
    return None


def dataset_to_rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert a supported dataset JSON object to editable CSV rows."""
    validate_dataset(data)
    persistent_id = get_persistent_id(data)
    title = get_title(data)
    version = get_version_block(data) or {}
    dataset_access_request = version.get("fileAccessRequest")
    file_records, _ = get_file_records(data)
    rows = []

    for record in file_records:
        data_file = record.get("dataFile", {})
        file_access_request = data_file.get("fileAccessRequest")
        if file_access_request is None:
            file_access_request = dataset_access_request
        rows.append(
            {
                "doi": persistent_id,
                "dataset_title": title,
                "file_id": data_file.get("id") or data_file.get("persistentId") or "",
                "file_name": data_file.get("filename") or record.get("label") or "",
                "restricted": bool(record.get("restricted", False)),
                "file_access_request": bool(file_access_request),
                "restricted_new": "",
                "file_access_request_new": "",
            }
        )
    return rows

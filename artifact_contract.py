"""Producer-side artifact manifest v2 validation and emission helpers.

The helpers are intentionally additive and side-effect free except for the
explicit emission function.  They never infer a primary from filenames.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_ROLES = {"primary_deliverable", "supporting", "source", "verification_report"}


def _invalid(reason: str, **extra: Any) -> dict:
    return {"valid": False, "reason": reason, **extra}


def _safe_basename(value: Any) -> bool:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        return False
    path = Path(value)
    return path.name == value and not path.is_absolute() and "\\" not in value and "\x00" not in value


def _regular_local_file(result_dir: Path, file_name: str) -> tuple[Path | None, str | None]:
    if not _safe_basename(file_name):
        return None, "invalid_file_name"
    candidate = result_dir / file_name
    try:
        if candidate.is_symlink():
            return None, "symlink_rejected"
        if not candidate.is_file() or not os.path.isfile(candidate):
            return None, "file_missing_or_not_regular"
        resolved_dir = result_dir.resolve()
        resolved = candidate.resolve()
        if resolved.parent != resolved_dir:
            return None, "path_escape_rejected"
    except OSError:
        return None, "file_stat_failed"
    return candidate, None


def validate_artifact_manifest(envelope: dict, result_dir: str | Path) -> dict:
    """Validate a v2 envelope and its primary content against local bytes."""
    if not isinstance(envelope, dict) or envelope.get("artifact_schema_version") != 2:
        return _invalid("unsupported_schema")
    manifest = envelope.get("artifact_manifest")
    if not isinstance(manifest, dict):
        return _invalid("manifest_missing")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return _invalid("artifacts_missing")
    primary = [item for item in artifacts if isinstance(item, dict) and item.get("role") == "primary_deliverable"]
    if len(primary) != 1:
        return _invalid("primary_count_invalid", primary_count=len(primary))
    top_id = manifest.get("primary_artifact_id")
    top_version = manifest.get("primary_artifact_version")
    if not isinstance(top_id, str) or not top_id or not isinstance(top_version, str) or not SHA256_RE.fullmatch(top_version):
        return _invalid("top_level_primary_pair_invalid")
    for item in artifacts:
        if not isinstance(item, dict) or item.get("role") not in ALLOWED_ROLES:
            return _invalid("artifact_item_invalid")
        if not isinstance(item.get("artifact_id"), str) or not item["artifact_id"]:
            return _invalid("artifact_id_invalid")
        version = item.get("artifact_version")
        digest = item.get("content_sha256")
        if not isinstance(version, str) or not SHA256_RE.fullmatch(version):
            return _invalid("artifact_version_invalid", artifact_id=item.get("artifact_id"))
        if not isinstance(digest, str) or not HEX_RE.fullmatch(digest):
            return _invalid("content_sha256_invalid", artifact_id=item.get("artifact_id"))
        if version != "sha256:" + digest:
            return _invalid("version_digest_mismatch", artifact_id=item.get("artifact_id"))
        if not _safe_basename(item.get("file_name")):
            return _invalid("file_name_invalid", artifact_id=item.get("artifact_id"))
    primary_item = primary[0]
    if (primary_item["artifact_id"], primary_item["artifact_version"]) != (top_id, top_version):
        return _invalid("top_level_primary_mismatch")
    primary_path = None
    for item in artifacts:
        path, reason = _regular_local_file(Path(result_dir), item["file_name"])
        if reason:
            return _invalid(reason, artifact=item)
        assert path is not None
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["content_sha256"]:
            return _invalid("content_digest_mismatch", artifact=item,
                            expected=item["content_sha256"], actual=digest)
        if item is primary_item:
            primary_path = path
    return {"valid": True, "artifact": dict(primary_item), "path": str(primary_path), "reason": None}


def emit_artifact_manifest(artifact_path: str | Path, artifact_id: str, *, role: str = "primary_deliverable",
                           media_type: str | None = None) -> dict:
    """Build a v2 manifest after a producer has written the final bytes."""
    path = Path(artifact_path)
    if role not in ALLOWED_ROLES or not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("invalid artifact role or id")
    if not _safe_basename(path.name) or path.is_symlink() or not path.is_file():
        raise ValueError("artifact path must be an existing regular non-symlink file")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    item = {"artifact_id": artifact_id, "artifact_version": "sha256:" + digest,
            "role": role, "file_name": path.name,
            "media_type": media_type or _media_type(path), "content_sha256": digest}
    return {"artifact_schema_version": 2,
            "artifact_manifest": {"primary_artifact_id": artifact_id if role == "primary_deliverable" else None,
                                  "primary_artifact_version": "sha256:" + digest if role == "primary_deliverable" else None,
                                  "artifacts": [item]}}


def _media_type(path: Path) -> str:
    return {".html": "text/html", ".htm": "text/html", ".md": "text/markdown",
            ".json": "application/json", ".txt": "text/plain"}.get(path.suffix.lower(), "application/octet-stream")


def exact_target(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, dict):
        return None, None
    target = value.get("target_artifact") if isinstance(value.get("target_artifact"), dict) else value
    if not isinstance(target, dict):
        return None, None
    artifact_id, version = target.get("artifact_id"), target.get("artifact_version")
    return (artifact_id if isinstance(artifact_id, str) and artifact_id else None,
            version if isinstance(version, str) and version else None)


def exact_target_match(value: Any, artifact: dict | None) -> bool:
    artifact_id, version = exact_target(value)
    return bool(artifact and artifact_id and version and
                artifact_id == artifact.get("artifact_id") and version == artifact.get("artifact_version"))

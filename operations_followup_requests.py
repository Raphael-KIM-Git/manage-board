"""Auditable, additive follow-up request intake persistence.

This module deliberately does not mutate canonical task records or dispatch anything.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REQUESTS_DIR = Path(os.environ.get("OPS_FOLLOWUP_REQUESTS_DIR", "/home/raphael/myproject/operations/follow-up-requests"))
SERVER_ACTOR = os.environ.get("OPS_DASHBOARD_ACTOR", "Raphael")
AUTH_SOURCE = os.environ.get("OPS_DASHBOARD_AUTH_SOURCE", "dashboard-local")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
ALLOWED_TARGETS = {"task", "stage", "artifact"}
ALLOWED_TYPES = {"supplement", "research", "revision", "verification", "new_artifact", "other"}
ALLOWED_PRIORITIES = {"low", "medium", "high"}
_WRITE_LOCK = threading.RLock()


class FollowUpError(ValueError):
    status = 400


class FollowUpConflict(FollowUpError):
    status = 409


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not TASK_ID_RE.fullmatch(text):
        raise FollowUpError(f"invalid {label}")
    return text


def _text(value: Any, label: str, limit: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise FollowUpError(f"{label} is required")
    if len(text) > limit:
        raise FollowUpError(f"{label} is too long")
    return text


def _list(value: Any, label: str, limit: int = 12) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise FollowUpError(f"{label} must be an array")
    if len(value) > limit:
        raise FollowUpError(f"{label} has too many items")
    result = []
    for item in value:
        text = _text(item, label, 160, required=True)
        if text not in result:
            result.append(text)
    return result


def _request_path(parent_task_id: str, request_id: str) -> Path:
    return REQUESTS_DIR / parent_task_id / f"{request_id}.json"


def _safe_root(root: Path) -> Path:
    root = Path(root)
    try:
        info = root.lstat()
    except FileNotFoundError:
        root.mkdir(parents=True, exist_ok=True)
        info = root.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise FollowUpError("follow-up request root is not a real directory")
    return root.resolve()


def _safe_parent(root: Path, parent: str, *, create: bool = False) -> Path:
    root = _safe_root(root)
    folder = root / parent
    try:
        info = folder.lstat()
    except FileNotFoundError:
        if not create:
            return folder
        folder.mkdir(mode=0o700)
        info = folder.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise FollowUpError("follow-up request parent directory is unsafe")
    if folder.resolve().parent != root:
        raise FollowUpError("follow-up request path escapes storage root")
    return folder


def _payload_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise FollowUpError("invalid follow-up request record")
    return data


def list_requests(parent_task_id: str, requests_dir: Path | None = None) -> list[dict[str, Any]]:
    parent = _safe_id(parent_task_id, "parent_task_id")
    root = requests_dir or REQUESTS_DIR
    folder = _safe_parent(root, parent)
    if not folder.is_dir():
        return []
    records = []
    for path in sorted(folder.glob("*.json")):
        try:
            if stat.S_ISLNK(path.lstat().st_mode) or path.resolve().parent != _safe_root(root) / parent:
                continue
        except OSError:
            continue
        try:
            record = _read(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if record.get("parent_task_id") == parent:
            records.append(record)
    return sorted(records, key=lambda item: (item.get("submitted_at", ""), item.get("request_id", "")), reverse=True)


def submit_request(
    parent_task_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    *,
    actor_id: str = SERVER_ACTOR,
    auth_source: str = AUTH_SOURCE,
    requests_dir: Path | None = None,
    task_exists: Callable[[str], bool] | None = None,
) -> tuple[dict[str, Any], bool]:
    parent = _safe_id(parent_task_id, "parent_task_id")
    if not isinstance(payload, dict):
        raise FollowUpError("JSON object required")
    key = _text(idempotency_key, "Idempotency-Key", 160, required=True)
    if not IDEMPOTENCY_RE.fullmatch(key):
        raise FollowUpError("invalid Idempotency-Key")
    if task_exists is not None and not task_exists(parent):
        raise FileNotFoundError(parent)
    target = payload.get("target") or {}
    if not isinstance(target, dict):
        raise FollowUpError("target must be an object")
    kind = _text(target.get("kind") or "task", "target.kind", 20)
    if kind not in ALLOWED_TARGETS:
        raise FollowUpError("invalid target.kind")
    target_id = _safe_id(target.get("id") or parent, "target.id")
    if kind == "task" and target_id != parent:
        raise FollowUpError("task target must match parent_task_id")
    request_type = _text(payload.get("request_type") or "other", "request_type", 30)
    if request_type not in ALLOWED_TYPES:
        raise FollowUpError("invalid request_type")
    clean = {
        "target": {"kind": kind, "id": target_id},
        "request_type": request_type,
        "title": _text(payload.get("title"), "title", 240, required=True),
        "desired_outcome": _text(payload.get("desired_outcome"), "desired_outcome", 4000, required=True),
        "context": _text(payload.get("context"), "context", 4000),
        "constraints": _text(payload.get("constraints"), "constraints", 2000),
        "priority_requested": _text(payload.get("priority_requested") or "medium", "priority_requested", 20),
        "owner_role_requested": _text(payload.get("owner_role_requested"), "owner_role_requested", 80),
        "verification_requested": _list(payload.get("verification_requested"), "verification_requested"),
    }
    if clean["priority_requested"] not in ALLOWED_PRIORITIES:
        raise FollowUpError("invalid priority_requested")
    root = _safe_root(requests_dir or REQUESTS_DIR)
    fingerprint = _payload_fingerprint(clean)
    with _WRITE_LOCK:
        for existing in list_requests(parent, root):
            if existing.get("idempotency_key") != key:
                continue
            if existing.get("payload_fingerprint") != fingerprint:
                raise FollowUpConflict("idempotency key already used with different payload")
            return existing, False
        request_id = f"FR-{uuid.uuid4().hex}"
        submitted_at = now_iso()
        record = {
            "schema_version": 1,
            "request_id": request_id,
            "version": 1,
            "parent_task_id": parent,
            **clean,
            "state": "pending_pm_review",
            "submitted_by": {"actor_id": _text(actor_id, "actor_id", 120, required=True), "auth_source": _text(auth_source, "auth_source", 120, required=True)},
            "submitted_at": submitted_at,
            "idempotency_key": key,
            "payload_fingerprint": fingerprint,
            "supersedes": None,
            "decision": None,
            "links": [],
            "events": [{"event": "submitted", "at": submitted_at, "actor_id": actor_id, "from": None, "to": "pending_pm_review"}],
        }
        _atomic_write(_request_path_for(root, parent, request_id), record)
        return record, True


def _request_path_for(root: Path, parent: str, request_id: str) -> Path:
    safe_request = _safe_id(request_id, "request_id")
    return _safe_parent(root, parent, create=True) / f"{safe_request}.json"


def capabilities() -> dict[str, Any]:
    enabled = os.environ.get("OPS_FOLLOWUP_REQUEST_WRITE", "1").lower() not in {"0", "false", "off", "no"}
    return {"write_enabled": enabled, "auth_source": AUTH_SOURCE, "actor_id": SERVER_ACTOR, "origin_required": True}

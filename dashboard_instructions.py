"""Append-only dashboard instruction intake.

Instructions are observations for PM review. They never mutate task records or
imply dispatch, approval, stage completion, or result receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

INSTRUCTIONS_DIR = Path(os.environ.get("OPS_DASHBOARD_INSTRUCTIONS_DIR", "/home/raphael/myproject/operations/instructions"))
ACTOR_ID = os.environ.get("OPS_DASHBOARD_ACTOR", "Raphael")
AUTH_SOURCE = os.environ.get("OPS_DASHBOARD_AUTH_SOURCE", "dashboard-local")
WRITE_ENABLED = os.environ.get("OPS_DASHBOARD_INSTRUCTION_WRITE", "1").lower() not in {"0", "false", "off", "no"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
TYPE_VALUES = {"new_task_brief", "additional_instruction"}
TARGET_VALUES = {"task", "stage", "project", "none"}
_LOCK = threading.RLock()

class InstructionError(ValueError):
    status = 400
    code = "invalid_instruction"
    retryable = False

class InstructionConflict(InstructionError):
    status = 409
    code = "idempotency_conflict"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: Any, label: str, limit: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise InstructionError(f"{label} is required")
    if len(text) > limit:
        raise InstructionError(f"{label} is too long")
    return text


def _id(value: Any, label: str, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text and not required:
        return None
    if not ID_RE.fullmatch(text):
        raise InstructionError(f"invalid {label}")
    return text


def capabilities() -> dict[str, Any]:
    return {"schema_version": 1, "write_enabled": WRITE_ENABLED, "actor_id": ACTOR_ID,
            "auth_source": AUTH_SOURCE, "origin_required": True, "allowed_instruction_types": sorted(TYPE_VALUES)}


def _fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _record_path(root: Path, instruction_id: str) -> Path:
    return root / f"{instruction_id}.json"


def list_instructions(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or INSTRUCTIONS_DIR
    if not root.is_dir():
        return []
    records = []
    for path in root.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(record, dict) and record.get("instruction_id"):
                records.append(record)
        except (OSError, ValueError, TypeError):
            continue
    return sorted(records, key=lambda item: (item.get("submitted_at", ""), item.get("instruction_id", "")), reverse=True)


def submit_instruction(payload: dict[str, Any], idempotency_key: str, *, root: Path | None = None,
                       actor_id: str = ACTOR_ID, auth_source: str = AUTH_SOURCE,
                       task_exists: Callable[[str], bool] | None = None) -> tuple[dict[str, Any], bool]:
    if not isinstance(payload, dict):
        raise InstructionError("JSON object required")
    key = _text(idempotency_key, "Idempotency-Key", 160, required=True)
    if not ID_RE.fullmatch(key):
        raise InstructionError("invalid Idempotency-Key")
    instruction_type = _text(payload.get("instruction_type"), "instruction_type", 40, required=True)
    if instruction_type not in TYPE_VALUES:
        raise InstructionError("invalid instruction_type")
    target_type = _text(payload.get("target_type") or "none", "target_type", 20)
    if target_type not in TARGET_VALUES:
        raise InstructionError("invalid target_type")
    target_id = _id(payload.get("target_id"), "target_id")
    if target_type != "none" and not target_id:
        raise InstructionError("target_id is required for targeted instruction")
    if target_type == "task" and task_exists is not None:
        assert target_id is not None
        if not task_exists(target_id):
            raise FileNotFoundError(target_id)
    clean = {
        "instruction_type": instruction_type,
        "target_type": target_type,
        "target_id": target_id,
        "target_raw_status": payload.get("target_raw_status"),
        "text": _text(payload.get("text"), "text", 10000, required=True),
        "conversation_context_id": _id(payload.get("conversation_context_id"), "conversation_context_id"),
        "client_created_at": _text(payload.get("client_created_at"), "client_created_at", 80),
    }
    fingerprint = _fingerprint(clean)
    root = root or INSTRUCTIONS_DIR
    with _LOCK:
        for old in list_instructions(root):
            if old.get("idempotency_key") != key:
                continue
            if old.get("payload_fingerprint") != fingerprint:
                raise InstructionConflict("idempotency key already used with different payload")
            return old, False
        submitted_at = now_iso()
        record = {
            "schema_version": 1, "instruction_id": f"DI-{uuid.uuid4().hex}", "version": 1,
            **clean, "state": "submitted_pending_pm_review", "submitted_at": submitted_at,
            "submitted_by": {"actor_id": _text(actor_id, "actor_id", 120, required=True), "auth_source": _text(auth_source, "auth_source", 120, required=True)},
            "idempotency_key": key, "payload_fingerprint": fingerprint, "parent_changed": False,
            "events": [{"event": "submitted", "at": submitted_at, "state": "submitted_pending_pm_review"}],
        }
        _atomic_write(_record_path(root, record["instruction_id"]), record)
        return record, True

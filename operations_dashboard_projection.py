"""Read-only raw task -> Dashboard projection.

This module deliberately performs no I/O and never mutates the supplied task.  The
raw task view remains the canonical source; this is an additive presentation model.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from artifact_contract import exact_target_match, validate_artifact_manifest


PIPELINE_LABELS = {
    "full": "조사→작성→검증→최종본",
    "write_verify": "작성→검증",
    "research_verify": "조사→검증",
    "analyze_verify": "분석→검증",
    "research_only": "조사만",
}
WORK_GROUPS = {
    "intake_clarifying", "planning", "in_progress", "verification",
    "pm_review", "done", "blocked", "unknown",
}
SYNC_FRESHNESS_SECONDS = 900
WATCHDOG_FRESHNESS_SECONDS = 900


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _exact_task_transition_match(value: Any, task_id: Any) -> bool:
    """Accept only unambiguous, schema-shaped evidence for this exact task."""
    if not isinstance(task_id, str) or not task_id.strip():
        return False
    expected = task_id.strip()
    if isinstance(value, str):
        parts = value.strip().split(":", 1)
        return len(parts) == 2 and parts[0].strip() == expected and bool(parts[1].strip())
    if not isinstance(value, dict) or not isinstance(value.get("task_id"), str):
        return False
    if value["task_id"].strip() != expected:
        return False
    if any(key in value and not isinstance(value[key], str) for key in ("status", "transition", "stage")):
        return False
    return any(isinstance(value.get(key), str) and value[key].strip() for key in ("status", "transition", "stage"))


def _evidence_health(raw: Any, task: dict, *, kind: str, now: datetime | None = None,
                     freshness_seconds: int | None = None) -> dict:
    """Normalize observational evidence; raw task/stage remains authoritative."""
    threshold = freshness_seconds if freshness_seconds is not None else (
        SYNC_FRESHNESS_SECONDS if kind == "sync" else WATCHDOG_FRESHNESS_SECONDS
    )
    base = {"state": "never_observed", "observed_at": None, "freshness_seconds": threshold,
            "source_limitation": "snapshot_missing", "task_transition_evidence": []}
    if raw is None or raw == {}:
        return base
    if isinstance(raw, dict) and raw.get("_malformed_snapshot") is True:
        return {**base, "state": "unknown", "source_limitation": "malformed_snapshot"}
    if not isinstance(raw, dict):
        return {**base, "state": "unknown", "source_limitation": "malformed_snapshot"}
    observed_at = raw.get("observed_at")
    observed = _parse_timestamp(observed_at)
    if observed is None:
        return {**base, "state": "unknown", "observed_at": observed_at,
                "source_limitation": "observed_at_missing_or_invalid"}
    now = now or datetime.now(timezone.utc)
    now = (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    age = max(0, int((now - observed).total_seconds()))
    task_updated = _parse_timestamp(task.get("updated_at"))
    older_than_task = bool(task_updated and observed < task_updated)
    stale = age > threshold or older_than_task
    if kind == "sync":
        state = "success" if raw.get("last_result") == "success" else "error" if raw.get("last_result") == "error" or raw.get("pull_exit") not in (None, 0) else "unknown"
    else:
        state = "success"
    if stale:
        state = "stale"
    limitation = "snapshot_older_than_task_raw" if older_than_task else ("freshness_threshold_exceeded" if age > threshold else None)
    transitions = []
    if kind == "sync":
        values = raw.get("task_transition_evidence") or raw.get("transition_evidence") or raw.get("status_updates") or []
        if isinstance(values, (str, dict)):
            values = [values]
        for value in values:
            if _exact_task_transition_match(value, task.get("task_id")):
                transitions.append(deepcopy(value))
    result = {"state": state, "observed_at": observed_at, "freshness_seconds": threshold,
              "age_seconds": age, "source_limitation": limitation,
              "task_transition_evidence": transitions}
    if kind == "sync":
        result["last_result"] = raw.get("last_result")
        result["pull_exit"] = raw.get("pull_exit")
    if kind == "watchdog":
        result["active_task"] = next((deepcopy(item) for item in raw.get("active_tasks", [])
                                       if isinstance(item, dict) and item.get("task_id") == task.get("task_id")), None)
        if not result["active_task"]:
            result["source_limitation"] = result["source_limitation"] or "task_not_in_snapshot"
    return result


def project_operations_evidence(task: dict, sync: Any = None, watchdog: Any = None, *, now: datetime | None = None,
                                sync_freshness_seconds: int | None = None,
                                watchdog_freshness_seconds: int | None = None) -> dict:
    return {
        "schema_version": 1,
        "sync": _evidence_health(sync, task, kind="sync", now=now, freshness_seconds=sync_freshness_seconds),
        "watchdog": _evidence_health(watchdog, task, kind="watchdog", now=now, freshness_seconds=watchdog_freshness_seconds),
    }


def classify_raw(mapping: dict, key: str, allowed: set[str] | None = None) -> dict:
    """Classify key presence without collapsing missing, null, and unknown."""
    if key not in mapping:
        return {"state": "missing", "raw": None}
    value = mapping[key]
    if value is None or value == "":
        return {"state": "null", "raw": value}
    if allowed is not None and value not in allowed:
        return {"state": "unknown", "raw": value}
    return {"state": "known", "raw": value}


def project_pipeline_shape(task: dict) -> dict:
    value = task.get("pipeline_shape") if "pipeline_shape" in task else None
    quality = classify_raw(task, "pipeline_shape", set(PIPELINE_LABELS))
    if quality["state"] == "known":
        return {"raw": value, "label": PIPELINE_LABELS[value], "confidence": "direct", "quality": None}
    warning = {"kind": quality["state"], "field": "pipeline_shape", "raw": quality["raw"]}
    label = {"missing": "파이프라인 정보 없음", "null": "파이프라인 정보 비어 있음", "unknown": "알 수 없는 파이프라인(raw)"}[quality["state"]]
    return {"raw": quality["raw"], "label": label, "confidence": "unavailable" if quality["state"] != "unknown" else "ambiguous", "quality": warning}


def _active_hold(task: dict) -> dict | None:
    for stage in task.get("stages") or []:
        status = stage.get("status")
        if status in {"entry_hold", "gate_hold"}:
            scope = "entry" if status == "entry_hold" or stage.get("id") == "research" and stage.get("entry_gate") else f"gate:{stage.get('id', 'unknown')}"
            return {"source": "stage", "scope": scope, "raw": status, "reason": stage.get("entry_hold_reason") or stage.get("gate_hold_reason") or stage.get("last_error")}
        gate = stage.get("gate") or {}
        if gate.get("decision") == "hold":
            return {"source": "stage.gate", "scope": f"gate:{stage.get('id', 'unknown')}", "raw": "hold", "reason": gate.get("reason") or gate.get("feedback")}
    entry = task.get("entry_gate") or {}
    if entry.get("decision") == "hold":
        return {"source": "entry_gate", "scope": "entry", "raw": "hold", "reason": entry.get("reason")}
    return None


def project_work_group(task: dict) -> dict:
    raw_status = task.get("status")
    if _active_hold(task):
        return {"value": "blocked", "confidence": "direct", "raw_status": raw_status}
    mapping = {
        "queued": "intake_clarifying", "planned": "planning", "dispatched": "in_progress",
        "partially_dispatched": "in_progress", "results_received": "verification",
        "waiting_verification": "verification", "needs_pm_review": "pm_review",
        "completed": "done", "cancelled": "done", "dispatch_blocked": "blocked",
        "dispatch_failed": "blocked", "in_progress": "in_progress",
    }
    value = mapping.get(raw_status, "unknown")
    return {"value": value, "confidence": "direct" if value != "unknown" else "ambiguous", "raw_status": raw_status}


def _row(source: str, value: Any, scope: str, normalized: str | None, confidence: str = "direct", reason: Any = None) -> dict:
    return {"source_mechanism": source, "source_value": value, "scope": scope, "normalized_decision": normalized, "confidence": confidence, "reason": reason}


def project_gate_rows(task: dict) -> list[dict]:
    rows = []
    entry = task.get("entry_gate")
    if not entry:
        research = next((s for s in task.get("stages") or [] if s.get("id") == "research"), {})
        entry = research.get("entry_gate")
    if isinstance(entry, dict) and "decision" in entry:
        value = entry.get("decision")
        normalized = {"proceed": "approve", "skip_research": "approve", "hold": "hold"}.get(value)
        rows.append(_row("entry_gate", value, "entry", normalized, "direct" if normalized else "ambiguous", entry.get("reason")))
    for stage in task.get("stages") or []:
        gate = stage.get("gate")
        if not isinstance(gate, dict) or "decision" not in gate:
            continue
        value = gate.get("decision")
        normalized = {"proceed": "approve", "revise": "rework", "hold": "hold"}.get(value)
        stage_id = stage.get("id")
        scope = f"gate:{stage_id}" if stage_id else "gate:unknown"
        rows.append(_row("hermes_gate", value, scope, normalized, "direct" if normalized and stage_id else "ambiguous", gate.get("reason") or gate.get("feedback")))
    return rows


def project_final_review(task: dict) -> dict:
    review = task.get("pm_final_review")
    if not isinstance(review, dict):
        return {"state": "not_run", "source": "pm_final_review", "raw_verdict": None, "normalized_decision": None, "scope": "final-review", "confidence": "unavailable", "quality": {"kind": "missing", "field": "pm_final_review"}}
    verdict = review.get("verdict")
    normalized = {"meets": "approve", "partial": "approve", "not_meets": "hold"}.get(verdict)
    if normalized is None:
        quality = {"kind": "null" if verdict in (None, "") else "unknown", "field": "pm_final_review.verdict", "raw": verdict}
        return {"state": "unknown", "source": "pm_final_review", "raw_verdict": verdict, "normalized_decision": None, "scope": "final-review", "confidence": "ambiguous", "quality": quality}
    return {"state": "available", "source": "pm_final_review", "raw_verdict": verdict, "normalized_decision": normalized, "scope": "final-review", "confidence": "direct", "comment": review.get("comment"), "gaps": review.get("gaps"), "override": bool(review.get("override")), "quality": None}


def project_artifacts(task: dict, result_files: list[dict], verification_files: list[dict]) -> dict:
    if not result_files:
        artifact = {"state": "none", "items": [], "latest": None}
    elif len(result_files) == 1:
        artifact = {"state": "available", "items": deepcopy(result_files), "latest": deepcopy(result_files[0])}
    else:
        artifact = {"state": "ambiguous", "items": deepcopy(result_files), "latest": None, "quality": {"kind": "artifact_ambiguous"}}
    verification = {"state": "available_unstructured", "items": deepcopy(verification_files)} if verification_files else {"state": "not_run", "items": []}
    return {"artifact": artifact, "verification": verification}


def _safe_result_metadata(task: dict) -> list[dict]:
    """Return sidecar metadata only when it is already present in the API view."""
    values = task.get("result_metadata") or []
    return [item for item in values if isinstance(item, dict) and isinstance(item.get("metadata"), dict)]


def _stage_from_name(name: str, task_id: str) -> str | None:
    lowered = name.lower()
    for marker, stage in (("-writing", "writing"), ("-verify", "verification"),
                          ("-verification", "verification"), ("-final", "final_write")):
        if marker in lowered:
            return stage
    return "research" if lowered.startswith(task_id.lower()) else None


def _result_progress(task: dict) -> dict:
    stages = task.get("stages") or []
    task_id = str(task.get("task_id") or "")
    expected_agents = {stage.get("id"): set(stage.get("agents") or []) for stage in stages if stage.get("id")}
    files = {item.get("name"): item for item in task.get("result_files") or [] if isinstance(item, dict)}
    stage_ids: dict[str, str] = {}
    historical_ids: dict[str, set[str]] = {}
    for stage in stages:
        stage_id = stage.get("id")
        if not stage_id:
            continue
        default_id = task_id if stage_id == "research" else f"{task_id}-{stage_id if stage_id != 'verification' else 'verify'}"
        stage_ids[stage_id] = str(stage.get("derived_task_id") or default_id)
        historical_ids[stage_id] = {default_id}
    bundles: dict[str, dict] = {}
    ambiguous = []
    scoped_unknown: dict[str, set[str]] = {}
    for sidecar in _safe_result_metadata(task):
        metadata = sidecar["metadata"]
        derived_id = metadata.get("task_id")
        stage_value = metadata.get("stage_id") or metadata.get("stage")
        stage = str(stage_value) if stage_value else None
        if not stage:
            stage = next((sid for sid, ids in stage_ids.items() if derived_id in ids or derived_id in historical_ids[sid]), None)
        worker = metadata.get("worker") or metadata.get("worker_name")
        report_value = metadata.get("report_file")
        report = str(report_value) if report_value else None
        stage_key = stage or ""
        active_id = stage_ids.get(stage_key)
        legacy_parent_result = bool(stage and not next((s.get("derived_task_id") for s in stages if s.get("id") == stage), None)
                                   and stage != "research" and derived_id == task_id)
        is_active = bool(stage and (derived_id == active_id or legacy_parent_result))
        is_history = bool(stage and derived_id in historical_ids.get(stage_key, set()) and not is_active)
        if not worker or not report or report not in files or stage_key not in expected_agents or worker not in expected_agents[stage_key] or not (is_active or is_history):
            ambiguous.append({"name": sidecar.get("name"), "reason": "worker/stage/report_file unlinked", "stage": stage, "worker": worker})
            if isinstance(stage, str) and stage in expected_agents and worker in expected_agents[stage]:
                scoped_unknown.setdefault(stage, set()).add(worker)
            continue
        key = f"{stage}::{worker}" if is_active else f"history::{stage}::{worker}::{derived_id}"
        bundle = bundles.setdefault(key, {"stage": stage, "worker": worker, "derived_task_id": derived_id, "files": [], "status": None, "metadata": metadata, "history": is_history})
        bundle["files"].extend([sidecar.get("name"), report])
        status = metadata.get("status")
        if status in {"failed", "blocked"}:
            bundle["status"] = "failed_or_blocked"
        elif bundle["status"] != "failed_or_blocked" and status == "completed":
            bundle["status"] = "result_received"
        else:
            bundle["status"] = "unknown"
    stage_states = {}
    for stage, workers in expected_agents.items():
        states = {}
        for worker in workers:
            bundle = bundles.get(f"{stage}::{worker}")
            if bundle:
                states[worker] = bundle["status"]
            else:
                dispatch = (task.get("dispatches") or {}).get(worker)
                states[worker] = "dispatch_confirmed" if dispatch in {"dispatched", "dispatch_confirmed"} else "not_dispatched"
        stage_bundles = [bundle for bundle in bundles.values() if bundle["stage"] == stage and not bundle.get("history")]
        task_stage = next((item for item in stages if item.get("id") == stage), {})
        received = sum(bundle["status"] == "result_received" for bundle in stage_bundles)
        failed = any(bundle["status"] == "failed_or_blocked" for bundle in stage_bundles)
        if failed:
            maturity = "ambiguous"
        elif received == 0:
            maturity = "none"
        elif task_stage.get("completion_policy") == "any" and received >= 1:
            maturity = "reviewable"
        elif received < len(workers):
            maturity = "partial_received"
        else:
            maturity = "reviewable"
        states["_maturity"] = maturity
        states["_received"] = received
        states["_expected"] = len(workers)
        states["_failed"] = failed
        # Preserve explicit stage completion separately from artifact maturity.
        states["_raw_status"] = next((s.get("status") for s in stages if s.get("id") == stage), None)
        states["_bundles"] = stage_bundles
        states["_ambiguous"] = [item for item in ambiguous if item.get("name")]
        states["_dispatch"] = {worker: (task.get("dispatches") or {}).get(worker) for worker in workers}
        stage_states[stage] = states
    referenced = {name for bundle in bundles.values() for name in bundle["files"] if name}
    for name in files:
        if name not in referenced:
            if name.lower().endswith(".html") and any(name.startswith(str(bundle.get("derived_task_id"))) for bundle in bundles.values()):
                continue
            ambiguous.append({"name": name, "reason": "result file has no safely linked metadata"})
    # A filename-only/unlinked artifact cannot be safely attributed to a worker.
    # Limit the downgrade to dispatched workers in the active stage; explicit
    # evidence scoped to another stage must not poison unrelated agents.
    if any(item.get("reason") == "result file has no safely linked metadata" for item in ambiguous):
        active = next((stage for stage in stages if stage.get("status") in {"in_progress", "entry_hold", "gate_hold"}), None)
        if active and active.get("id") in expected_agents:
            stage_id = active["id"]
            dispatched = {worker for worker in expected_agents[stage_id]
                          if (task.get("dispatches") or {}).get(worker) in {"dispatched", "dispatch_confirmed"}}
            if dispatched:
                scoped_unknown.setdefault(stage_id, set()).update(dispatched)
    limitation = "결과 파일의 작업자·단계 귀속을 안전하게 확인할 수 없음"
    for stage, workers in scoped_unknown.items():
        states = stage_states.get(stage)
        if not states:
            continue
        for worker in workers:
            if states.get(worker) in {"dispatch_confirmed", "not_dispatched"}:
                states[worker] = "unknown"
                states.setdefault("_limitations", {})[worker] = limitation
        if workers:
            states["_maturity"] = "ambiguous"
    ordered_bundles = sorted(bundles.values(), key=lambda bundle: bool(bundle.get("history")))
    return {"stages": stage_states, "bundles": ordered_bundles, "ambiguous": ambiguous}


def _verification_state(task: dict, progress: dict, artifacts: dict) -> str:
    files = task.get("verification_files") or task.get("verification_metadata") or []
    if not files:
        return "not_run"
    # Verification files are never verified merely because they exist.
    for item in task.get("verification_metadata") or task.get("verification_files") or []:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        if not isinstance(metadata, dict):
            continue
        verdict = metadata.get("verdict") or metadata.get("status")
        binding = metadata.get("artifact_id") or metadata.get("result_artifact_id") or metadata.get("artifact_version")
        if verdict in {"verified", "passed", "meets", "complete", "completed"} and binding:
            for bundle in progress["bundles"]:
                candidate = bundle.get("metadata") or {}
                if binding in {candidate.get("artifact_id"), candidate.get("artifact_version"), candidate.get("report_file")}:
                    return "verified"
    return "available_unstructured"


def _binding_value(value: dict | None) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("artifact_id", "result_artifact_id", "artifact_version", "result_version", "report_file"):
        candidate = value.get(key)
        if candidate not in (None, ""):
            return str(candidate)
    return None


def _binding_fields(value: dict | None) -> tuple[str | None, str | None]:
    if not isinstance(value, dict):
        return None, None
    target = value.get("target_artifact")
    if isinstance(target, dict):
        identity = target.get("artifact_id")
        version = target.get("artifact_version")
        return (str(identity) if identity not in (None, "") else None,
                str(version) if version not in (None, "") else None)
    identity = value.get("artifact_id") or value.get("result_artifact_id")
    version = value.get("artifact_version") or value.get("result_version")
    return (str(identity) if identity not in (None, "") else None,
            str(version) if version not in (None, "") else None)


def _stage_default_task_id(task_id: str, stage_id: str) -> str:
    return task_id if stage_id == "research" else f"{task_id}-{stage_id if stage_id != 'verification' else 'verify'}"


def _final_deliverable_artifact(file: dict, metadata: dict, bundle_key: str) -> dict:
    name = file.get("name") if isinstance(file, dict) else None
    suffix = str(name or "").lower().rsplit(".", 1)[-1]
    media = {"html": "html", "htm": "html", "md": "markdown", "markdown": "markdown",
             "json": "json", "txt": "text"}.get(suffix, "unknown")
    artifact_id, version = _binding_fields(metadata)
    return {"name": name, "dir": "results", "artifact_id": artifact_id, "version": version,
            "media_type": media, "bundle_key": bundle_key, "source_envelope": metadata,
            "openable": bool(name)}


def project_final_deliverable(task: dict, progress: dict | None = None) -> dict:
    """Classify a final artifact using only exact active envelopes and bindings.

    This is deliberately conservative: filenames, ordering, mtime, and positive
    unbound review text never promote a candidate to the final deliverable.
    """
    task_id = str(task.get("task_id") or "")
    stages = [stage for stage in task.get("stages") or [] if isinstance(stage, dict)]
    by_id = {str(stage.get("id")): stage for stage in stages if stage.get("id")}
    final_stage = by_id.get("final_write")
    final_skipped = bool(final_stage and (final_stage.get("skipped") is True or final_stage.get("status") == "skipped"))
    final_completed = bool(final_stage and final_stage.get("status") == "completed" and not final_skipped)
    source_mode = "final_write" if final_completed else "skipped_final_write_fallback" if final_skipped else "unresolved"
    stage = final_stage if final_completed else by_id.get("writing") if final_skipped else None
    if stage is None and final_skipped and task.get("pipeline_shape") == "research_only":
        stage = by_id.get("research")
        source_mode = "no_final_write_pipeline"
    if stage is None:
        return {"state": "unavailable", "reason_code": "deliverable_stage_not_completed", "label": "최종 결과물 확인 불가",
                "source_mode": source_mode, "deliverable_stage": None, "artifact": None, "candidates": [],
                "verification": {"state": "not_run", "artifact_id": None, "version": None, "matched": False},
                "pm_final_review": {"state": "not_run", "verdict": None, "artifact_id": None, "version": None, "matched": False},
                "evidence": [], "limitations": ["deliverable_stage_not_completed"]}
    stage_id = str(stage.get("id"))
    derived_id = str(stage.get("derived_task_id") or _stage_default_task_id(task_id, stage_id))
    stage_info = {"id": stage_id, "raw_status": stage.get("status"), "derived_task_id": derived_id}
    if stage.get("status") != "completed":
        return {"state": "unavailable", "reason_code": "deliverable_stage_not_completed", "label": "최종 결과물 확인 불가",
                "source_mode": source_mode, "deliverable_stage": stage_info, "artifact": None, "candidates": [],
                "verification": {"state": "not_run", "artifact_id": None, "version": None, "matched": False},
                "pm_final_review": {"state": "not_run", "verdict": None, "artifact_id": None, "version": None, "matched": False},
                "evidence": [], "limitations": ["deliverable_stage_not_completed"]}

    progress = progress or _result_progress(task)
    bundles = [bundle for bundle in progress.get("bundles", [])
               if bundle.get("derived_task_id") == derived_id and bundle.get("status") == "result_received"]
    if len(bundles) != 1:
        reason = "active_attempt_unresolved" if not bundles else "multiple_equal_candidates"
        return {"state": "unavailable" if not bundles else "ambiguous", "reason_code": reason,
                "label": "최종 결과물 확인 불가", "source_mode": source_mode, "deliverable_stage": stage_info,
                "artifact": None, "candidates": [], "verification": {"state": "not_run", "artifact_id": None, "version": None, "matched": False},
                "pm_final_review": {"state": "not_run", "verdict": None, "artifact_id": None, "version": None, "matched": False},
                "evidence": [], "limitations": [reason]}
    bundle = bundles[0]
    metadata = bundle.get("metadata") or {}
    result_files = {str(item.get("name")): item for item in task.get("result_files") or [] if isinstance(item, dict) and item.get("name")}
    v2_check = None
    if metadata.get("artifact_schema_version") == 2:
        manifest = metadata.get("artifact_manifest")
        primary_items = [item for item in manifest.get("artifacts", [])
                         if isinstance(item, dict) and item.get("role") == "primary_deliverable"] \
            if isinstance(manifest, dict) else []
        primary_name = primary_items[0].get("file_name") if len(primary_items) == 1 else None
        primary_path = result_files.get(primary_name or "", {}).get("path")
        result_dir = Path(primary_path).parent if primary_path else Path("/nonexistent")
        v2_check = validate_artifact_manifest(metadata, result_dir)
        if not v2_check.get("valid"):
            return {"state": "unavailable", "reason_code": "artifact_manifest_" + str(v2_check.get("reason", "invalid")),
                    "label": "최종 결과물 확인 불가", "source_mode": source_mode, "deliverable_stage": stage_info,
                    "artifact": None, "candidates": [], "verification": {"state": "not_run", "artifact_id": None, "version": None, "matched": False},
                    "pm_final_review": {"state": "not_run", "verdict": None, "artifact_id": None, "version": None, "matched": False},
                    "evidence": [], "limitations": ["artifact_manifest_invalid"]}
    explicit_id, explicit_version = _binding_fields(metadata)
    names = [name for name in bundle.get("files", []) if name in result_files and not name.lower().endswith(".json")]
    # HTML (or other sibling) outputs are linked to the active envelope by its
    # derived task id, but never selected by lexical order.
    names.extend(name for name in result_files if name.lower().startswith(derived_id.lower()) and name not in names and not name.lower().endswith(".json"))
    names = list(dict.fromkeys(names))
    if v2_check and v2_check.get("valid"):
        primary = v2_check["artifact"]
        primary_file = result_files.get(primary["file_name"], {"name": primary["file_name"]})
        candidates = [{**_final_deliverable_artifact(primary_file, metadata, f"{stage_id}::{bundle.get('worker', '')}"),
                       "artifact_id": primary["artifact_id"], "version": primary["artifact_version"],
                       "artifact_version": primary["artifact_version"], "content_sha256": primary["content_sha256"],
                       "file_name": primary["file_name"]}]
    else:
        candidates = [_final_deliverable_artifact(result_files[name], metadata, f"{stage_id}::{bundle.get('worker', '')}") for name in names]
    if explicit_id:
        target_names = {explicit_id, str(metadata.get("report_file") or "")}
        candidates = [item for item in candidates if item.get("name") in target_names]
    elif explicit_version:
        report_name = str(metadata.get("report_file") or "")
        report_candidates = [item for item in candidates if item.get("name") == report_name]
        candidates = report_candidates or [item for item in candidates if item.get("version") == explicit_version]
    artifact = candidates[0] if len(candidates) == 1 else None
    review = task.get("pm_final_review") if isinstance(task.get("pm_final_review"), dict) else {}
    review_id, review_version = _binding_fields(review)
    verification_records = task.get("verification_metadata") or task.get("verification_files") or []
    verification = next((item.get("metadata") for item in verification_records if isinstance(item, dict) and isinstance(item.get("metadata"), dict)), {}) or {}
    verification_id, verification_version = _binding_fields(verification)
    verification_bound = bool(verification.get("verdict") or verification.get("status")) and bool(verification_id or verification_version)
    verification_match = (exact_target_match(verification, artifact) if v2_check else
                          bool(artifact and verification_bound and ((verification_id and verification_id in {artifact.get("name"), artifact.get("artifact_id")}) or (verification_version and verification_version == artifact.get("version")))))
    review_bound = bool(review_id or review_version)
    review_match = (exact_target_match(review, artifact) if v2_check else
                    bool(artifact and review_bound and ((review_id and review_id in {artifact.get("name"), artifact.get("artifact_id")}) or (review_version and review_version == artifact.get("version")))))
    verification_view = {"state": "bound" if verification_match else "result_received_unbound" if verification_records else "not_run", "artifact_id": verification_id, "version": verification_version, "matched": verification_match}
    review_view = {"state": "bound" if review_match else "review_recorded_unbound" if review else "not_run", "verdict": review.get("verdict"), "artifact_id": review_id, "version": review_version, "matched": review_match}
    evidence = [{"source_type": "stage_raw", "source_id": stage_id, "field": "status", "raw_value": stage.get("status"), "scope": stage_id, "confidence": "direct"},
                {"source_type": "result_envelope", "source_id": derived_id, "field": "report_file", "raw_value": metadata.get("report_file"), "scope": stage_id, "confidence": "direct"}]
    if final_completed:
        if not candidates:
            state, reason = "unavailable", "artifact_identity_missing"
        elif len(candidates) > 1:
            state, reason = "ambiguous", "multiple_equal_candidates"
        elif artifact and ((verification_bound and not verification_match) or (review_bound and not review_match)):
            state, reason = "conflict", "verification_pm_binding_conflict"
        else:
            state, reason = "confirmed", None
    elif len(candidates) > 1:
        state, reason = "ambiguous", "multiple_equal_candidates"
    elif not candidates:
        state, reason = "unavailable", "artifact_identity_missing"
    elif verification_match and review_match and review.get("verdict") in {"meets", "partial"} and not _active_hold(task):
        state, reason = "confirmed", None
    elif verification_bound and review_bound and artifact and not (verification_match and review_match):
        state, reason = "conflict", "verification_pm_binding_conflict"
    else:
        state, reason = "candidate_unconfirmed", "binding_insufficient"
    return {"state": state, "reason_code": reason, "label": "확인됨" if state == "confirmed" else "최종 결과물 확인 불가",
            "source_mode": source_mode, "deliverable_stage": stage_info, "artifact": artifact,
            "candidates": candidates, "verification": verification_view, "pm_final_review": review_view,
            "evidence": evidence, "limitations": [] if reason is None else [reason]}


def project_progress(task: dict) -> dict:
    progress = _result_progress(task)
    current = next((stage for stage in task.get("stages") or [] if stage.get("status") in {"in_progress", "entry_hold", "gate_hold"}), None)
    current_id = current.get("id") if current else None
    current_state = progress["stages"].get(current_id, {}) if current_id else {}
    verification = _verification_state(task, progress, { })
    hold = _active_hold(task)
    failed = any(state.get("_failed") for state in progress["stages"].values())
    unknown = bool(progress["ambiguous"] or any(state.get("_maturity") == "ambiguous" for state in progress["stages"].values()))
    dispatch_wait = any((current_state.get("_dispatch") or {}).get(worker) in {"dispatched", "dispatch_confirmed"}
                        and current_state.get(worker) not in {"result_received", "failed_or_blocked"}
                        for worker in (current_state.get("_dispatch") or {}))
    missing_dispatch = any(current_state.get(worker) in {"not_dispatched", "unknown"}
                           for worker in (current_state.get("_dispatch") or {}))
    if hold or failed:
        action = {"kind": "blocked", "label": "차단 근거 확인", "scope": current_id or "task", "target": "task_detail"}
    elif unknown:
        action = {"kind": "unknown", "label": "raw 상태 확인", "scope": current_id or "task", "target": "task_detail"}
    elif missing_dispatch:
        action = {"kind": "dispatch", "label": "전송 상태 확인", "scope": current_id or "task", "target": "task_detail"}
    elif dispatch_wait:
        action = {"kind": "wait_for_result", "label": "작성 결과 도착 확인" if current_id == "writing" else "결과 도착 확인", "scope": f"stage:{current_id}", "target": "task_detail"}
    elif current_state.get("_maturity") == "partial_received":
        action = {"kind": "partial", "label": "미도착 결과 확인", "scope": f"stage:{current_id}", "target": "task_detail"}
    elif current_state.get("_maturity") == "reviewable" and verification == "not_run":
        action = {"kind": "verification", "label": "검증 시작/확인", "scope": f"stage:{current_id}", "target": "task_detail"}
    elif verification == "verified" and not task.get("pm_final_review"):
        action = {"kind": "final_review", "label": "최종 검토", "scope": "final-review", "target": "task_detail"}
    elif task.get("status") in {"completed", "cancelled"}:
        action = {"kind": "done", "label": "결과 보기", "scope": "task", "target": "task_detail"}
    else:
        action = {"kind": "progress", "label": "진행 상세 보기", "scope": current_id or "task", "target": "task_detail"}
    return {"schema_version": 1, "current_stage": current_id, "agent_states": progress["stages"],
            "bundles": progress["bundles"], "ambiguous_files": progress["ambiguous"],
            "verification_state": verification, "next_pm_action": action}


def _decision_queue(group: str, hold: dict | None, final: dict, artifacts: dict, task: dict) -> dict | None:
    if hold:
        return {"kind": "active_hold", "question": "진행을 위해 활성 보류를 확인해 주세요", "scope": hold["scope"], "reason": hold.get("reason"), "primary_action": "게이트 상세 보기"}
    if final.get("raw_verdict") == "not_meets":
        return {"kind": "final_review", "question": "최종 검토 결과를 확인하고 재작업 여부를 판단해 주세요", "scope": "final-review", "reason": final.get("gaps") or final.get("comment"), "primary_action": "최종 검토 보기"}
    if group in {"verification", "pm_review"} and (artifacts["artifact"]["state"] != "none" or artifacts["verification"]["state"] != "not_run"):
        return {"kind": "reviewable", "question": "검토 가능한 산출물과 검증 근거를 확인해 주세요", "scope": "final-review", "reason": None, "primary_action": "산출물 검토"}
    return None


def project_task(task_view: dict) -> dict:
    task = deepcopy(task_view)
    group = project_work_group(task)
    pipeline = project_pipeline_shape(task)
    gates = project_gate_rows(task)
    final = project_final_review(task)
    artifacts = project_artifacts(task, task.get("result_files") or [], task.get("verification_files") or [])
    progress = project_progress(task)
    final_deliverable = project_final_deliverable(task, progress)
    hold = _active_hold(task)
    quality = [pipeline["quality"]] if pipeline.get("quality") else []
    status_quality = classify_raw(task, "status", {"queued", "planned", "dispatched", "partially_dispatched", "results_received", "waiting_verification", "needs_pm_review", "completed", "cancelled", "dispatch_blocked", "dispatch_failed", "in_progress"})
    if status_quality["state"] != "known":
        quality.append({"kind": status_quality["state"], "field": "status", "raw": status_quality["raw"]})
    if final.get("quality"): quality.append(final["quality"])
    if artifacts["artifact"].get("quality"): quality.append(artifacts["artifact"]["quality"])
    if hold and final.get("raw_verdict") in {"meets", "partial"}:
        quality.append({"kind": "conflict", "scope": hold["scope"], "reason": "active hold takes precedence"})
    review = task.get("pm_final_review") if isinstance(task.get("pm_final_review"), dict) else {}
    review = review or {}
    override = task.get("final_review_override")
    artifact_binding = review.get("artifact_id") or review.get("artifact_version") or review.get("result_artifact_id") or review.get("result_version")
    latest_artifact = artifacts["artifact"].get("latest") or {}
    binding_matches = bool(artifact_binding and artifacts["artifact"]["state"] == "available" and (
        (review.get("artifact_id") and review.get("artifact_id") in {latest_artifact.get("name"), latest_artifact.get("id")})
        or (review.get("result_artifact_id") and review.get("result_artifact_id") in {latest_artifact.get("name"), latest_artifact.get("id")})
        or (review.get("artifact_version") and review.get("artifact_version") == latest_artifact.get("version"))
        or (review.get("result_version") and review.get("result_version") == latest_artifact.get("version"))
    ))
    if final.get("state") in {"available", "unknown"} or override in {"accept", "rework"}:
        if not binding_matches:
            quality.append({"kind": "artifact_ambiguous", "scope": "final-review", "reason": "final review/override is not explicitly bound to an artifact or version"})
    for gate in gates:
        if gate["scope"] == "gate:unknown":
            quality.append({"kind": "scope_missing", "field": "stage.id", "scope": gate["scope"]})
    effective_final = bool(binding_matches and (final.get("raw_verdict") in {"meets", "partial"} or override == "accept") and not hold)
    compact = group["value"] == "done"
    audit_rows = list(gates)
    for note in task.get("pm_live_notes") or []:
        if isinstance(note, dict):
            audit_rows.append(_row("pm_live_notes", note.get("note"), "task/current", None, "direct"))
    if "pm_final_review" in task:
        audit_rows.append(_row("pm_final_review", final.get("raw_verdict"), "final-review", final.get("normalized_decision"), final.get("confidence", "unavailable")))
    if override in {"accept", "rework"}:
        audit_rows.append(_row("final_review_override", override, "final-review", "approve" if override == "accept" else "rework"))
    decision_queue = _decision_queue(group["value"], hold, final, artifacts, task)
    if decision_queue is None or (progress["next_pm_action"]["kind"] in {"blocked", "unknown"} and final.get("raw_verdict") != "not_meets"):
        decision_queue = progress["next_pm_action"]
    verification_summary = artifacts["verification"]
    if progress["verification_state"] == "verified":
        verification_summary = {**verification_summary, "state": "verified"}
    operations_evidence = task.get("operations_evidence") or project_operations_evidence(task)
    return {
        "schema_version": 1,
        "work_group": group["value"],
        "work_group_detail": group,
        "pipeline_shape": pipeline,
        "decision_queue_item": decision_queue,
        "task_card": {"title": task.get("title", ""), "objective": task.get("objective", ""), "status": task.get("status"), "work_group": group["value"], "updated_at": task.get("updated_at")},
        "artifact_summary": artifacts["artifact"],
        "final_deliverable": final_deliverable,
        "verification_summary": verification_summary,
        "operations_evidence": operations_evidence,
        "progress": progress,
        "authority_summary": {"effective_final_approved": effective_final, "label": "현재 raw 근거", "history": "history_unavailable"},
        "audit_rows": audit_rows,
        "data_quality": quality,
        "compact": compact,
        "compact_hide_gate_details": compact,
    }


def build_dashboard_summary(task_views: list[dict]) -> dict:
    projections = [t.get("dashboard_projection") or project_task(t) for t in task_views]
    counts = {"active": 0, "decision_needed": 0, "reviewable": 0, "blocked": 0, "done": 0, "unknown": 0}
    for projection in projections:
        group = projection.get("work_group", "unknown")
        if group in {"done"}: counts["done"] += 1
        elif group == "blocked": counts["blocked"] += 1
        elif group == "unknown": counts["unknown"] += 1
        else: counts["active"] += 1
        item = projection.get("decision_queue_item")
        if item: counts["decision_needed"] += 1
        if item and item.get("kind") == "reviewable": counts["reviewable"] += 1
    return {"schema_version": 1, "counts": counts, "task_count": len(projections)}

"""Read-only raw task -> Dashboard projection.

This module deliberately performs no I/O and never mutates the supplied task.  The
raw task view remains the canonical source; this is an additive presentation model.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


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
    expected_agents = {stage.get("id"): set(stage.get("agents") or []) for stage in stages if stage.get("id")}
    files = {item.get("name"): item for item in task.get("result_files") or [] if isinstance(item, dict)}
    bundles: dict[str, dict] = {}
    ambiguous = []
    scoped_unknown: dict[str, set[str]] = {}
    for sidecar in _safe_result_metadata(task):
        metadata = sidecar["metadata"]
        if metadata.get("task_id") != task.get("task_id"):
            ambiguous.append({"name": sidecar.get("name"), "reason": "task_id mismatch or missing"})
            continue
        worker = metadata.get("worker") or metadata.get("worker_name")
        report = metadata.get("report_file")
        stage = metadata.get("stage_id") or metadata.get("stage") or _stage_from_name(str(report or sidecar.get("name", "")), str(task.get("task_id", "")))
        if not worker or not report or report not in files or stage not in expected_agents or worker not in expected_agents[stage]:
            ambiguous.append({"name": sidecar.get("name"), "reason": "worker/stage/report_file unlinked", "stage": stage, "worker": worker})
            if isinstance(stage, str) and stage in expected_agents and worker in expected_agents[stage]:
                scoped_unknown.setdefault(stage, set()).add(worker)
            continue
        key = f"{stage}::{worker}"
        bundle = bundles.setdefault(key, {"stage": stage, "worker": worker, "files": [], "status": None, "metadata": metadata})
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
        stage_bundles = [bundle for bundle in bundles.values() if bundle["stage"] == stage]
        received = sum(bundle["status"] == "result_received" for bundle in stage_bundles)
        failed = any(bundle["status"] == "failed_or_blocked" for bundle in stage_bundles)
        if failed:
            maturity = "ambiguous"
        elif received == 0:
            maturity = "none"
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
    return {"stages": stage_states, "bundles": list(bundles.values()), "ambiguous": ambiguous}


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
    return {
        "schema_version": 1,
        "work_group": group["value"],
        "work_group_detail": group,
        "pipeline_shape": pipeline,
        "decision_queue_item": decision_queue,
        "task_card": {"title": task.get("title", ""), "objective": task.get("objective", ""), "status": task.get("status"), "work_group": group["value"], "updated_at": task.get("updated_at")},
        "artifact_summary": artifacts["artifact"],
        "verification_summary": verification_summary,
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

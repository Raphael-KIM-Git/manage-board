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
    return {
        "schema_version": 1,
        "work_group": group["value"],
        "work_group_detail": group,
        "pipeline_shape": pipeline,
        "decision_queue_item": _decision_queue(group["value"], hold, final, artifacts, task),
        "task_card": {"title": task.get("title", ""), "objective": task.get("objective", ""), "status": task.get("status"), "work_group": group["value"], "updated_at": task.get("updated_at")},
        "artifact_summary": artifacts["artifact"],
        "verification_summary": artifacts["verification"],
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

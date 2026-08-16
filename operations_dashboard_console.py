"""Pure v2 console projection built from one task snapshot."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable
import uuid
import re

from operations_dashboard_projection import project_task


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _status_quality(task: dict[str, Any]) -> str:
    if "status" not in task:
        return "missing"
    if task.get("status") in (None, ""):
        return "null"
    known = {"queued", "planned", "dispatched", "partially_dispatched", "results_received", "waiting_verification", "needs_pm_review", "completed", "cancelled", "dispatch_blocked", "dispatch_failed", "in_progress"}
    return "known" if task.get("status") in known else "unknown"


def _safe_agent_metadata(metadata: Any) -> dict[str, str]:
    """Keep only bounded, display-safe labels supplied by the local registry."""
    if not isinstance(metadata, dict):
        return {}
    return {
        key: value.strip()
        for key in ("model", "provider")
        if isinstance(value := metadata.get(key), str)
        and ".." not in value.strip()
        and re.fullmatch(r"[A-Za-z0-9._/-]{1,80}", value.strip())
    }


def _project_ref(task: dict[str, Any]) -> dict[str, Any]:
    ref = task.get("project_ref")
    if not isinstance(ref, dict) or not ref.get("project_id"):
        return {"project_id": "unassigned", "name": "프로젝트 미지정", "bound": False, "source": "unassigned"}
    project_id = str(ref["project_id"]).strip()
    if not project_id:
        return {"project_id": "unassigned", "name": "프로젝트 미지정", "bound": False, "source": "unassigned"}
    return {"project_id": project_id, "name": str(ref.get("name") or project_id), "bound": True, "source": "task.project_ref"}


def _agent_rows(tasks: list[dict[str, Any]], projections: dict[str, dict[str, Any]], availability: dict[str, Any] | None,
                agent_registry: dict[str, Any] | list[str] | None = None,
                agent_metadata: dict[str, dict[str, Any]] | None = None,
                local_profile_agents: set[str] | None = None) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    availability = availability or {}
    agent_metadata = agent_metadata or {}
    local_profile_agents = local_profile_agents or set()
    if isinstance(agent_registry, dict):
        registry_names = set(agent_registry)
    else:
        registry_names = set(agent_registry or [])

    def configuration_state(agent: str) -> str:
        value = availability.get(agent)
        if value == "needs_config":
            return "needs_config"
        if agent in registry_names or value is not None:
            return "configured"
        return "unknown"

    def ensure(agent: str) -> dict[str, Any]:
        agent = str(agent)
        metadata = (agent_metadata.get(agent) if agent in local_profile_agents else {})
        metadata = metadata if isinstance(metadata, dict) else {}
        safe_metadata = _safe_agent_metadata(metadata)
        return rows.setdefault(agent, {"agent_id": agent, "name": agent, **safe_metadata,
                                        "availability": availability.get(agent, "unknown"),
                                        "configuration_state": configuration_state(agent),
                                        "dispatch_state": "not_dispatched", "execution_state": "idle",
                                        "active_count": 0, "review_count": 0, "blocked_count": 0,
                                        "completed_count": 0, "dispatch": [], "results": [],
                                        "latest_evidence_at": None, "task_ids": []})

    # Registry identity is configuration evidence, not task execution evidence.
    # Seed it before processing tasks so an empty brief directory remains honest.
    for agent in registry_names:
        ensure(str(agent))

    for task in tasks:
        task_id = str(task.get("task_id") or "")
        projection = projections.get(task_id) or {}
        progress = projection.get("progress") or {}
        # Assignment/configuration is identity evidence, not execution evidence.
        # Keep an assigned-but-undispatched agent visible without copying task status.
        for agent in task.get("assigned_workers") or []:
            row = ensure(str(agent))
            if task_id and task_id not in row["task_ids"]:
                row["task_ids"].append(task_id)
        if task.get("reviewer"):
            row = ensure(str(task["reviewer"]))
            if task_id and task_id not in row["task_ids"]:
                row["task_ids"].append(task_id)
        for stage in task.get("stages") or []:
            stage_id = stage.get("id")
            state = (progress.get("agent_states") or {}).get(stage_id, {})
            for agent in stage.get("agents") or []:
                row = ensure(str(agent))
                if task_id and task_id not in row["task_ids"]:
                    row["task_ids"].append(task_id)
                worker_state = state.get(agent, "not_dispatched")
                dispatch_state = (state.get("_dispatch") or {}).get(agent)
                row["dispatch"].append({"task_id": task_id, "stage_id": stage_id, "state": dispatch_state or "not_dispatched"})
                row["results"].append({"task_id": task_id, "stage_id": stage_id, "state": worker_state})
                if dispatch_state:
                    row["dispatch_state"] = dispatch_state
                if worker_state != "not_dispatched":
                    row["execution_state"] = worker_state
                if worker_state in {"failed_or_blocked"}:
                    row["blocked_count"] += 1
                elif worker_state == "result_received":
                    row["completed_count"] += 1
                elif stage_id == "verification" or task.get("reviewer") == agent:
                    row["review_count"] += 1
                elif dispatch_state in {"dispatched", "dispatch_confirmed"} or worker_state == "unknown":
                    row["active_count"] += 1
    return sorted(rows.values(), key=lambda row: row["name"])


def _project_rows(tasks: list[dict[str, Any]], projections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        ref = _project_ref(task)
        project_id = ref["project_id"]
        row = grouped.setdefault(project_id, {**ref, "active_count": 0, "done_count": 0, "unknown_count": 0, "task_ids": [], "latest_evidence_at": None})
        if task_id:
            row["task_ids"].append(task_id)
        group = (projections.get(task_id) or {}).get("work_group", "unknown")
        if group == "done": row["done_count"] += 1
        elif group == "unknown": row["unknown_count"] += 1
        else: row["active_count"] += 1
        changed = task.get("updated_at") or task.get("created_at")
        if changed and (row["latest_evidence_at"] is None or str(changed) > str(row["latest_evidence_at"])):
            row["latest_evidence_at"] = changed
    return sorted(grouped.values(), key=lambda row: (row["project_id"] == "unassigned", row["project_id"]))


def _mission_for_task(task: dict[str, Any], projection: dict[str, Any]) -> list[dict[str, Any]]:
    task_id = str(task.get("task_id") or "")
    rows = []
    progress = projection.get("progress") or {}
    queue = projection.get("decision_queue_item")
    if queue:
        kind = "blocker" if queue.get("kind") in {"active_hold", "blocked"} else "unknown" if queue.get("kind") == "unknown" else "decision"
        rows.append({"kind": kind, "question": queue.get("question") or queue.get("label") or "판단 근거를 확인하세요", "target": {"type": "task", "id": task_id}, "scope": queue.get("scope", "task"), "raw_status": task.get("status"), "evidence": [queue.get("reason")] if queue.get("reason") else [], "evidence_at": task.get("updated_at"), "limitation": None, "recommended_action": queue.get("primary_action") or queue.get("label") or "상세 근거 확인", "dedupe_key": f"task:{task_id}:{queue.get('scope','task')}:{queue.get('kind','unknown')}"})
    if projection.get("final_deliverable", {}).get("state") in {"confirmed", "candidate_unconfirmed", "ambiguous"} and not queue:
        rows.append({"kind": "reviewable", "question": "검토 가능한 결과물을 확인하세요", "target": {"type": "task", "id": task_id}, "scope": "final-review", "raw_status": task.get("status"), "evidence": [projection["final_deliverable"].get("reason_code")], "evidence_at": task.get("updated_at"), "limitation": None, "recommended_action": "산출물 binding 확인", "dedupe_key": f"task:{task_id}:final-review:reviewable"})
    if projection.get("data_quality") or progress.get("ambiguous_files"):
        rows.append({"kind": "unknown", "question": "원시 근거와 귀속을 확인할 수 없습니다", "target": {"type": "task", "id": task_id}, "scope": "data-quality", "raw_status": task.get("status"), "evidence": [item.get("kind") for item in projection.get("data_quality", [])], "evidence_at": task.get("updated_at"), "limitation": "projection data quality requires raw review", "recommended_action": "raw evidence 확인", "dedupe_key": f"task:{task_id}:data-quality:unknown"})
    return rows


def _safe_pane(name: str, factory: Callable[[], Any], limitations: list[str]) -> Any:
    try:
        return factory()
    except Exception as exc:
        limitations.append(f"{name}: {type(exc).__name__}")
        return {"state": "unknown", "items": [], "limitation": "pane projection unavailable"}


def project_console_snapshot(task_views: list[dict[str, Any]], *, instruction_records: list[dict[str, Any]] | None = None,
                             availability: dict[str, Any] | None = None,
                             agent_registry: dict[str, Any] | list[str] | None = None,
                             agent_metadata: dict[str, dict[str, Any]] | None = None,
                             local_profile_agents: set[str] | None = None,
                             generated_at: str | None = None) -> dict[str, Any]:
    raw_tasks = deepcopy(task_views or [])
    limitations: list[str] = []
    projections: dict[str, dict[str, Any]] = {}
    tasks_by_id: dict[str, dict[str, Any]] = {}
    for task in raw_tasks:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            continue
        try:
            projection = task.get("dashboard_projection") or project_task(task)
            projections[task_id] = projection
            tasks_by_id[task_id] = {"task_id": task_id, "title": task.get("title", ""), "objective": task.get("objective", ""), "status": task.get("status"), "status_quality": _status_quality(task), "updated_at": task.get("updated_at"), "project_ref": deepcopy(task.get("project_ref")) if isinstance(task.get("project_ref"), dict) else None, "projection": projection}
        except Exception:
            limitations.append(f"task:{task_id}: projection unavailable")
    instructions = [deepcopy(item) for item in (instruction_records or []) if isinstance(item, dict)]
    def pm_pane():
        return {"state": "ready", "current_context": {"target_type": "none", "target_id": None, "target_raw_status": None}, "recent_instructions": instructions[:20]}
    def agents_pane(): return {"state": "ready", "items": _agent_rows(raw_tasks, projections, availability, agent_registry, agent_metadata, local_profile_agents)}
    def projects_pane(): return {"state": "ready", "items": _project_rows(raw_tasks, projections)}
    def mission_pane():
        rows = []
        seen = set()
        for task in raw_tasks:
            task_id = str(task.get("task_id") or "")
            for row in _mission_for_task(task, projections.get(task_id, {})):
                if row["dedupe_key"] not in seen:
                    seen.add(row["dedupe_key"]); rows.append(row)
        for instruction in instructions:
            if instruction.get("state") == "submitted_pending_pm_review":
                key = f"instruction:{instruction.get('instruction_id')}"
                if key not in seen:
                    seen.add(key); rows.append({"kind": "decision", "question": "지시가 PM 검토 대기입니다", "target": {"type": instruction.get("target_type"), "id": instruction.get("target_id")}, "scope": "instruction-review", "raw_status": instruction.get("state"), "evidence": [instruction.get("text", "")[:240]], "evidence_at": instruction.get("submitted_at"), "limitation": None, "recommended_action": "instruction record 보기", "instruction_id": instruction.get("instruction_id"), "dedupe_key": key})
        order = {"blocker": 0, "decision": 1, "unknown": 2, "reviewable": 3}
        return {"state": "ready", "items": sorted(rows, key=lambda row: (order.get(row.get("kind"), 9), row.get("evidence_at") or ""),)}
    panes = {"pm_instruction": _safe_pane("pm_instruction", pm_pane, limitations), "agents": _safe_pane("agents", agents_pane, limitations), "projects": _safe_pane("projects", projects_pane, limitations), "mission_control": _safe_pane("mission_control", mission_pane, limitations)}
    timestamp = generated_at or _now()
    return {"schema_version": 2, "snapshot_id": f"console-{uuid.uuid4().hex}", "generated_at": timestamp, "source_freshness": {"tasks": timestamp, "agents": timestamp, "sync": None, "watchdog": None}, "panes": panes, "tasks_by_id": tasks_by_id, "limitations": limitations}

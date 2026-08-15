from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .registry import Registry, db_snapshot, fingerprint, save_registry

STALE_EDGES = [
    ("t_5dec0067", "t_79b27437"),
    ("t_30a3d533", "t_1f8c9314"),
    ("t_1631cefc", "t_18fc1fe8"),
    ("t_4d067679", "t_a1b18044"),
    ("t_44e06f2c", "t_4382ece8"),
]

@dataclass
class ReconcilePlan:
    actions: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    writes: int = 0
    mode: str = "dry_run"

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "mode": self.mode, "actions": self.actions,
                "conflicts": self.conflicts, "writes": self.writes}

class Reconciler:
    def __init__(self, db_path: Path, registry: Registry, registry_path: Path | None = None):
        self.db_path, self.registry, self.registry_path = db_path, registry, registry_path

    def review_ready(self, workflow_id: str) -> dict[str, Any]:
        wf = self.registry.workflows[workflow_id]
        developer = wf.get("tasks", {}).get("developer")
        reviewer = wf.get("tasks", {}).get("reviewer")
        con = sqlite3.connect(self.db_path); con.row_factory = sqlite3.Row
        try:
            dev = con.execute("select id,status,block_kind from tasks where id=?", (developer,)).fetchone()
            rev = con.execute("select id,status from tasks where id=?", (reviewer,)).fetchone() if reviewer else None
            if not dev: return {"eligible": False, "reason": "developer_missing"}
            comments = [r[0] for r in con.execute("select body from task_comments where task_id=? order by id", (developer,))]
            handoff = next((body for body in reversed(comments) if body.startswith("review-required handoff:")), None)
            eligible = bool(handoff) and (dev["status"] == "blocked" or dev["block_kind"] == "needs_input")
            links = ([dict(r) for r in con.execute("select parent_id,child_id from task_links where child_id=?", (reviewer,))]
                     if reviewer else [])
            independent = all(link["parent_id"] != developer for link in links)
            eligible = eligible and independent
            return {"eligible": eligible, "developer": developer, "reviewer": reviewer, "handoff": handoff,
                    "reviewer_parents": links, "independent": independent,
                    "reason": None if eligible else ("reviewer_parent_invariant" if not independent else "missing_review_required_handoff")}
        finally: con.close()

    def plan(self, *, expected_state_version: int | None = None) -> ReconcilePlan:
        plan = ReconcilePlan()
        if expected_state_version is not None and expected_state_version != self.registry.state_version:
            plan.conflicts.append({"kind": "optimistic_conflict", "expected": expected_state_version, "actual": self.registry.state_version})
            return plan
        for parent, child in STALE_EDGES:
            plan.actions.append({"kind": "unlink_stale_edge", "parent": parent, "child": child,
                                 "evidence_preserved": True, "requires_dispatcher_pause": True})
        graph = db_snapshot(self.db_path)
        for wf_id, wf in self.registry.workflows.items():
            reviewer = wf.get("tasks", {}).get("reviewer")
            if reviewer:
                gate = self.review_ready(wf_id)
                if gate["eligible"]:
                    plan.actions.append({"kind": "pm_promote_reviewer", "workflow_id": wf_id, "reviewer": reviewer,
                                         "developer": wf["tasks"]["developer"], "parent_mutation": False,
                                         "reason": "PM-held reviewer; independent from developer"})
                else:
                    plan.actions.append({"kind": "hold_reviewer", "workflow_id": wf_id, "reviewer": reviewer,
                                         "reason": gate["reason"]})
            downstream = wf.get("tasks", {}).get("downstream", [])
            approved = self._latest_pass(wf)
            if approved:
                plan.actions.append({"kind": "atomic_replace_parents", "child_ids": downstream,
                                     "parents": [approved["reviewer"]], "candidate_binding": wf.get("candidate_key"),
                                     "candidate_hash": approved["candidate_hash"], "remove_obsolete": True,
                                     "expected_edge_fingerprint": graph["edge_fingerprint"]})
            elif wf.get("latest_approved_reviewer") is not None:
                # An untrusted reviewer result must fail closed for the whole
                # apply, rather than allowing unrelated cleanup writes.
                plan.conflicts.append({"kind": "reviewer_authorization",
                                       "workflow_id": wf_id,
                                       "configured_reviewer": reviewer})
            if self._terminal_ready(wf):
                if wf.get("state") != "closed":
                    plan.actions.append({"kind": "workflow.closed", "workflow_id": wf_id,
                                         "reason": "required gates terminal and latest reviewer PASS/waiver"})
        return plan

    def _latest_pass(self, wf: dict[str, Any]) -> dict[str, str] | None:
        approved = wf.get("latest_approved_reviewer")
        if not isinstance(approved, dict):
            # Do not trust a bare reviewer ID.  A structured result may live
            # in the reviewer result or in its most recent comment.
            reviewer_id = approved if isinstance(approved, str) else wf.get("tasks", {}).get("reviewer")
            approved = self._structured_reviewer_result(reviewer_id)
        if not isinstance(approved, dict) or approved.get("verdict") != "PASS":
            return None
        reviewer = approved.get("reviewer_id") or approved.get("id")
        configured_reviewer = wf.get("tasks", {}).get("reviewer")
        candidate_key = approved.get("candidate_key")
        candidate_hash = approved.get("candidate_hash")
        if reviewer != configured_reviewer or candidate_key != wf.get("candidate_key") or not candidate_hash:
            return None
        if wf.get("candidate_hash") is not None and candidate_hash != wf.get("candidate_hash"):
            return None
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute("select status from tasks where id=?", (reviewer,)).fetchone()
            if not row or row[0] not in {"done", "completed", "archived"}:
                return None
        finally:
            con.close()
        return {"reviewer": reviewer, "candidate_hash": candidate_hash}

    def _structured_reviewer_result(self, reviewer_id: str | None) -> dict[str, Any] | None:
        if not reviewer_id:
            return None
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute("select result from tasks where id=?", (reviewer_id,)).fetchone()
            candidates = [row[0]] if row and row[0] else []
            try:
                comments = con.execute("select body from task_comments where task_id=? order by id desc", (reviewer_id,)).fetchall()
            except sqlite3.OperationalError:
                comments = []
            candidates.extend(r[0] for r in comments)
        finally:
            con.close()
        for raw in candidates:
            text = str(raw).strip()
            if text.startswith("review-result:"):
                text = text.split(":", 1)[1].strip()
            try:
                value = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("verdict"):
                value.setdefault("reviewer_id", reviewer_id)
                return value
        return None

    def _terminal_ready(self, wf: dict[str, Any]) -> bool:
        if wf.get("state") != "active" or not self._latest_pass(wf):
            return False
        ids = wf.get("tasks", {}).get("downstream", [])
        if not ids:
            return False
        con = sqlite3.connect(self.db_path)
        try:
            statuses = [r[0] for r in con.execute(
                "select status from tasks where id in (%s)" % ",".join("?" * len(ids)), tuple(ids))]
            gates = wf.get("gate_statuses", {})
            required = wf.get("expected_terminal_gates", [])
            gates_ok = all(gates.get(g) in {"pass", "passed", "waived", "cancelled", "done"}
                           for g in required if g != "review_pass")
            preflight = wf.get("delivery_preflight", {}).get("status") if isinstance(wf.get("delivery_preflight"), dict) else None
            preflight_ok = preflight in {None, "ok", "ready", "degraded"} or bool(wf.get("delivery_outbox_id"))
            return (len(statuses) == len(ids) and all(s in {"done", "completed", "archived", "cancelled"} for s in statuses)
                    and gates_ok and preflight_ok and not wf.get("held") and not wf.get("correction_required"))
        finally:
            con.close()

    def apply(self, plan: ReconcilePlan, *, confirm: bool = False, expected_state_version: int | None = None) -> ReconcilePlan:
        if not confirm or self.registry.mode != "write":
            plan.mode = "dry_run"; plan.writes = 0; return plan
        if plan.conflicts:
            # Do not apply stale-edge cleanup alongside an authorization or
            # optimistic conflict; the safe result is zero writes.
            plan.writes = 0
            return plan
        if expected_state_version is not None and expected_state_version != self.registry.state_version:
            plan.conflicts.append({"kind": "optimistic_conflict", "expected": expected_state_version, "actual": self.registry.state_version}); return plan
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("BEGIN IMMEDIATE")
            # Check all graph preconditions before any delete/insert.  A race
            # therefore produces zero writes, including stale-edge actions.
            for action in plan.actions:
                if action["kind"] != "atomic_replace_parents":
                    continue
                con.row_factory = sqlite3.Row
                links = [dict(r) for r in con.execute("select parent_id,child_id from task_links")]
                links.sort(key=lambda row: (row["parent_id"], row["child_id"]))
                actual = fingerprint(links)
                if actual != action.get("expected_edge_fingerprint"):
                    plan.conflicts.append({"kind": "edge_conflict", "expected": action.get("expected_edge_fingerprint"), "actual": actual})
                    con.rollback(); plan.writes = 0; return plan
            for action in plan.actions:
                if action["kind"] == "unlink_stale_edge":
                    con.execute("delete from task_links where parent_id=? and child_id=?", (action["parent"], action["child"]))
                    plan.writes += 1
                    continue
                if action["kind"] != "atomic_replace_parents": continue
                for child in action["child_ids"]:
                    con.execute("delete from task_links where child_id=?", (child,))
                    for parent in action["parents"]: con.execute("insert or ignore into task_links(parent_id,child_id) values (?,?)", (parent, child))
                    plan.writes += 1
            for action in plan.actions:
                if action["kind"] == "workflow.closed":
                    workflow = self.registry.workflows[action["workflow_id"]]
                    workflow["state"] = "closed"
                    workflow["closed_at"] = datetime.now(timezone.utc).isoformat()
                    workflow["close_event_emitted"] = True
                    self.registry.state_version += 1
            con.commit(); plan.mode = "write"
            if self.registry_path is not None:
                save_registry(self.registry, self.registry_path)
        except Exception:
            con.rollback(); raise
        finally: con.close()
        return plan


def queue_outbox(registry: Registry, event: dict[str, Any], *, preflight_ok: bool = False) -> dict[str, Any]:
    record = {"id": f"outbox-{fingerprint(event)[:16]}", "created_at": datetime.now(timezone.utc).isoformat(),
              "event": event, "status": "ready" if preflight_ok else "degraded", "attempts": 0}
    if not any(item.get("id") == record["id"] for item in registry.outbox): registry.outbox.append(record)
    return record

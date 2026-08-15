from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .registry import Registry, fingerprint, save_registry

ALLOWLIST = {
    "done", "blocked", "failed", "timed_out", "review_ready", "review_pass", "review_needs_changes",
    "stage_changed", "dependency_conflict", "invalid_handoff", "duplicate_reviewer", "workflow.closed",
}

@dataclass
class MonitorResult:
    events: list[dict[str, Any]]
    stdout: str
    baseline: bool
    heartbeat: bool = False

class WorkflowMonitor:
    def __init__(self, db_path: Path, registry: Registry, state_path: Path):
        self.db_path, self.registry, self.state_path = db_path, registry, state_path

    def _rows(self) -> dict[str, dict[str, Any]]:
        con = sqlite3.connect(self.db_path); con.row_factory = sqlite3.Row
        try:
            ids = {tid for wf in self.registry.workflows.values() for tid in (
                [wf.get("tasks", {}).get("developer"), wf.get("tasks", {}).get("reviewer")] + wf.get("tasks", {}).get("downstream", []) + wf.get("candidate_tasks", [])) if tid}
            if not ids: return {}
            q = ",".join("?" for _ in ids)
            return {r["id"]: dict(r) for r in con.execute(f"select id,title,status,result,current_run_id,completed_at,last_heartbeat_at from tasks where id in ({q})", tuple(ids))}
        finally: con.close()

    def _comments(self, task_id: str) -> list[dict[str, Any]]:
        con = sqlite3.connect(self.db_path); con.row_factory = sqlite3.Row
        try: return [dict(r) for r in con.execute("select id,body,created_at from task_comments where task_id=? order by id", (task_id,))]
        finally: con.close()

    def _event_candidates(self, rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        events = []
        for wf_id, wf in self.registry.workflows.items():
            if wf.get("state") != "active":
                continue
            task_ids = [wf.get("tasks", {}).get("developer"), wf.get("tasks", {}).get("reviewer")] + wf.get("tasks", {}).get("downstream", [])
            for tid in filter(None, task_ids):
                task = rows.get(tid)
                if not task: continue
                status = task.get("status")
                if status in {"done", "completed", "blocked", "failed", "timed_out"}:
                    kind = "done" if status in {"done", "completed"} else status
                    events.append(self._event(wf_id, kind, tid, {"status": status, "result": task.get("result")}))
                for comment in self._comments(tid):
                    body = str(comment.get("body", ""))
                    if body.startswith("review-required handoff:") or "review_ready" in body:
                        events.append(self._event(wf_id, "review_ready", tid, {"comment_id": comment["id"], "body": body[:1000]}))
                    if '"verdict": "PASS"' in body or "verdict: PASS" in body:
                        events.append(self._event(wf_id, "review_pass", tid, {"comment_id": comment["id"], "body": body[:1000]}))
        return events

    @staticmethod
    def _event(wf_id: str, kind: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {"namespace": "workflow", "workflow_id": wf_id, "kind": kind, "task_id": task_id, "payload": payload}
        event["fingerprint"] = fingerprint(event)
        return event

    def run(self, *, now: datetime | None = None, rebaseline: bool = False) -> MonitorResult:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        rows = self._rows()
        current = self._event_candidates(rows)
        old = {}
        if self.state_path.exists():
            try: old = json.loads(self.state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError: old = {}
        baseline = not old or rebaseline or old.get("schema_version") != 1
        current_by_fp = {e["fingerprint"]: e for e in current if e["kind"] in ALLOWLIST}
        events = [] if baseline else [e for fp, e in current_by_fp.items() if fp not in set(old.get("fingerprints", []))]
        active = [wf for wf in self.registry.workflows.values() if wf.get("state") == "active"]
        heartbeat = False
        if not baseline and active:
            last = old.get("last_meaningful_event_at")
            last_dt = None
            if last:
                try: last_dt = datetime.fromisoformat(last)
                except ValueError: pass
            if last_dt is None or now - last_dt >= timedelta(minutes=30):
                heartbeat = True
                events.append({"namespace": "workflow", "kind": "heartbeat", "workflow_id": next(iter(self.registry.workflows)),
                               "fingerprint": fingerprint({"kind": "heartbeat", "at": now.date().isoformat()}),
                               "payload": {"active_workflows": len(active), "monitor_health": "ok"}})
        state = {"schema_version": 1, "baseline_created_at": old.get("baseline_created_at") or now.isoformat(),
                 "registry_hash": self.registry.digest(), "last_event_id": self.registry.last_event_id,
                 "fingerprints": sorted(current_by_fp), "last_meaningful_event_at": now.isoformat() if baseline or events else old.get("last_meaningful_event_at"),
                 "active_workflows": sorted(k for k,v in self.registry.workflows.items() if v.get("state") == "active")}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        save_registry(self.registry, self.state_path.with_name("workflows.v1.json"))
        if baseline: return MonitorResult([], "", True, False)
        visible = [e for e in events if e.get("namespace") == "workflow"]
        return MonitorResult(visible, "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in visible), False, heartbeat)


def service_timeout_event(detail: str) -> dict[str, Any]:
    return {"namespace": "service.dashboard", "kind": "timeout", "workflow_mutation": False,
            "project_failure": False, "detail": detail}

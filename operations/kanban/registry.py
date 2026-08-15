from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_REGISTRY = Path(__file__).with_name("workflows.v1.json")
PLAN_PATH = Path(__file__).parents[2] / "Agent-Hub-Kanban-Lifecycle-Autocontinue-Plan-ko.md"
ACTIVE_TASKS = {
    "wf-v11-followup": {"developer": "t_1631cefc", "reviewer": "t_18fc1fe8", "downstream": ["t_1fdb2444"]},
    "wf-v11-artifact": {"developer": "t_4d067679", "reviewer": "t_a1b18044", "downstream": ["t_5b823723"], "candidates": ["t_3b629b40"]},
    "wf-v12-console": {"developer": "t_44e06f2c", "reviewer": None, "downstream": ["t_4382ece8"]},
    "wf-v11-producer": {"developer": "t_3b629b40", "reviewer": "t_a1b18044", "downstream": ["t_5b823723"]},
}

@dataclass
class Registry:
    schema_version: int = SCHEMA_VERSION
    workflows: dict[str, dict[str, Any]] = field(default_factory=dict)
    mode: str = "dry_run"
    state_version: int = 1
    last_event_id: int = 0
    outbox: list[dict[str, Any]] = field(default_factory=list)

    def canonical(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "mode": self.mode,
                "state_version": self.state_version, "last_event_id": self.last_event_id,
                "workflows": self.workflows, "outbox": self.outbox}

    def digest(self) -> str:
        data = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(data).hexdigest()


def load_registry(path: Path = DEFAULT_REGISTRY) -> Registry:
    if not path.exists():
        return Registry(workflows=build_default_workflows())
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Registry(schema_version=raw.get("schema_version", 0), mode=raw.get("mode", "dry_run"),
                    state_version=raw.get("state_version", 1), last_event_id=raw.get("last_event_id", 0),
                    workflows=raw.get("workflows", {}), outbox=raw.get("outbox", []))


def save_registry(registry: Registry, path: Path = DEFAULT_REGISTRY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(registry.canonical(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def build_default_workflows() -> dict[str, dict[str, Any]]:
    result = {}
    for workflow_id, roles in ACTIVE_TASKS.items():
        result[workflow_id] = {
            "workflow_id": workflow_id, "schema_version": 1, "state": "active", "generation": 1,
            "tasks": {"developer": roles["developer"], "reviewer": roles.get("reviewer"), "downstream": roles["downstream"]},
            "candidate_key": "workspace-or-commit+diff-manifest", "candidate_tasks": roles.get("candidates", []),
            "latest_approved_reviewer": None, "expected_terminal_gates": ["review_pass", "qa_pass", "release_decision"],
            "heartbeat_minutes": 30, "delivery_target": None, "last_event_cursor": 0,
            "last_event_fingerprint": None, "last_heartbeat_at": None, "delivery_preflight": {"status": "not_run"},
            "superseded_tasks": [], "replacement_mapping": {}, "closed_at": None,
        }
    return result


def db_snapshot(db_path: Path) -> dict[str, Any]:
    """Read task graph/evidence metadata without mutation."""
    con = sqlite3.connect(db_path); con.row_factory = sqlite3.Row
    try:
        tasks = [dict(r) for r in con.execute("select * from tasks")]
        links = [dict(r) for r in con.execute("select parent_id, child_id from task_links")]
        counts = {t: con.execute(f"select count(*) from {t}").fetchone()[0]
                  for t in ("tasks", "task_links", "task_comments", "task_runs", "task_events", "task_attachments")
                  if _table_exists(con, t)}
        links.sort(key=lambda row: (row["parent_id"], row["child_id"]))
        return {"tasks": tasks, "links": links, "edge_fingerprint": fingerprint(links),
                "evidence_counts": counts}
    finally:
        con.close()


def blocked_inventory(db_path: Path, plan_path: Path = PLAN_PATH) -> dict[str, Any]:
    """Extract the plan's authoritative 34-row classification and join live state."""
    text = plan_path.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    pattern = re.compile(r"\|\s*`(t_[0-9a-f]+)`\s*\|\s*(active workflow|superseded|irrecoverable|historical evidence)\s*\|([^|]*)\|([^|]*)\|")
    for m in pattern.finditer(text):
        rows.append({"task_id": m.group(1), "category": m.group(2), "reason": m.group(3).strip(), "action": m.group(4).strip()})
    snapshot = db_snapshot(db_path)
    live = {row["id"]: row for row in snapshot["tasks"]}
    for row in rows:
        task = live.get(row["task_id"], {})
        row["live_status"] = task.get("status")
        row["evidence_preserved"] = "yes"
    counts: dict[str, int] = {}
    for row in rows: counts[row["category"]] = counts.get(row["category"], 0) + 1
    return {"schema_version": 1, "source": str(plan_path), "rows": rows, "counts": counts,
            "total": len(rows), "evidence_counts": snapshot["evidence_counts"], "writes": 0}


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None

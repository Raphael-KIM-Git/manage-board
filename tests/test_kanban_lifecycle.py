import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from operations.kanban.monitor import WorkflowMonitor, service_timeout_event
from operations.kanban.reconciler import Reconciler, queue_outbox
from operations.kanban.registry import Registry, blocked_inventory, build_default_workflows, load_registry, save_registry

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "kanban.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
        create table tasks(id text primary key,title text,status text,result text,current_run_id integer,completed_at integer,last_heartbeat_at integer,block_kind text);
        create table task_links(parent_id text, child_id text, primary key(parent_id,child_id));
        create table task_comments(id integer primary key,task_id text,body text,created_at integer);
        """)
        con.executemany("insert into tasks values (?,?,?,?,?,?,?,?)", [
            ("dev", "developer", "blocked", None, None, None, None, "needs_input"),
            ("rev", "reviewer", "todo", None, None, None, None, None),
            ("qa", "qa", "todo", None, None, None, None, None),
        ])
        con.execute("insert into task_comments values (1,'dev',?,1)", ("review-required handoff:\n{\"candidate_key\":\"abc\"}",))
        con.commit(); con.close()
        self.reg = Registry(workflows={"wf": {"workflow_id":"wf", "schema_version":1,"state":"active","generation":1,
            "tasks":{"developer":"dev","reviewer":"rev","downstream":["qa"]},"candidate_key":"abc","candidate_tasks":[],
            "latest_approved_reviewer":None,"expected_terminal_gates":["review_pass","qa_pass","release_decision"],"heartbeat_minutes":30}})

    def tearDown(self): self.tmp.cleanup()

    def test_first_and_second_snapshot_are_silent(self):
        state = Path(self.tmp.name) / "state.json"
        mon = WorkflowMonitor(self.db, self.reg, state)
        first = mon.run(now=datetime(2026,1,1,tzinfo=timezone.utc))
        second = mon.run(now=datetime(2026,1,1,0,1,tzinfo=timezone.utc))
        self.assertTrue(first.baseline); self.assertEqual(first.stdout, ""); self.assertEqual(second.events, [])

    def test_review_ready_is_deduplicated(self):
        state = Path(self.tmp.name) / "state.json"; mon = WorkflowMonitor(self.db, self.reg, state)
        con = sqlite3.connect(self.db)
        con.execute("delete from task_comments")
        con.commit(); con.close()
        mon.run(now=datetime(2026,1,1,tzinfo=timezone.utc))
        con = sqlite3.connect(self.db)
        con.execute("insert into task_comments values (1,'dev',?,2)", ("review-required handoff:\n{}",))
        con.commit(); con.close()
        event = mon.run(now=datetime(2026,1,1,0,1,tzinfo=timezone.utc))
        self.assertEqual([e["kind"] for e in event.events], ["review_ready"])
        self.assertEqual(mon.run(now=datetime(2026,1,1,0,2,tzinfo=timezone.utc)).events, [])

    def test_reconciler_holds_reviewer_and_is_dry_run(self):
        plan = Reconciler(self.db, self.reg).plan()
        self.assertEqual(plan.writes, 0)
        self.assertEqual(len([a for a in plan.actions if a["kind"] == "unlink_stale_edge"]), 5)
        self.assertTrue(any(a["kind"] == "pm_promote_reviewer" for a in plan.actions))
        self.assertEqual(sqlite3.connect(self.db).execute("select count(*) from task_links").fetchone()[0], 0)

    def test_outbox_dedup_and_service_timeout_is_not_workflow_failure(self):
        e = service_timeout_event("HTTP timeout")
        self.assertFalse(e["workflow_mutation"]); self.assertFalse(e["project_failure"])
        a = queue_outbox(self.reg, e); b = queue_outbox(self.reg, e)
        self.assertEqual(a["id"], b["id"]); self.assertEqual(len(self.reg.outbox), 1)

    def test_inventory_has_authoritative_34_rows(self):
        result = blocked_inventory(Path.home()/".hermes/kanban.db")
        self.assertEqual(result["total"], 34)
        self.assertEqual(result["counts"], {"active workflow":4,"superseded":16,"irrecoverable":2,"historical evidence":12})
        self.assertEqual(result["writes"], 0)

    def test_done_reviewer_needs_changes_has_no_replacement(self):
        self.reg.workflows["wf"]["latest_approved_reviewer"] = {
            "reviewer_id": "rev", "verdict": "NEEDS_CHANGES",
            "candidate_key": "abc", "candidate_hash": "h1"}
        con = sqlite3.connect(self.db)
        con.execute("update tasks set status='done' where id='rev'")
        con.commit(); con.close()
        plan = Reconciler(self.db, self.reg).plan()
        self.assertFalse(any(a["kind"] == "atomic_replace_parents" for a in plan.actions))

    def test_pass_candidate_hash_mismatch_is_fail_closed(self):
        self.reg.workflows["wf"]["candidate_hash"] = "expected"
        self.reg.workflows["wf"]["latest_approved_reviewer"] = {
            "reviewer_id": "rev", "verdict": "PASS",
            "candidate_key": "abc", "candidate_hash": "stale"}
        con = sqlite3.connect(self.db)
        con.execute("update tasks set status='done' where id='rev'")
        con.commit(); con.close()
        plan = Reconciler(self.db, self.reg).plan()
        self.assertFalse(any(a["kind"] == "atomic_replace_parents" for a in plan.actions))

    def test_external_reviewer_pass_cannot_replace_parents_or_write_cleanup(self):
        self.reg.workflows["wf"]["latest_approved_reviewer"] = {
            "reviewer_id": "evil", "verdict": "PASS",
            "candidate_key": "abc", "candidate_hash": "h1"}
        con = sqlite3.connect(self.db)
        con.execute("insert into tasks values (?,?,?,?,?,?,?,?)",
                    ("evil", "unrelated reviewer", "done", None, None, None, None, None))
        con.execute("insert into task_links values ('old','qa')")
        con.commit(); con.close()

        reconciler = Reconciler(self.db, self.reg)
        plan = reconciler.plan()
        self.assertFalse(any(a["kind"] == "atomic_replace_parents" for a in plan.actions))
        self.assertTrue(any(c["kind"] == "reviewer_authorization" for c in plan.conflicts))

        self.reg.mode = "write"
        result = reconciler.apply(plan, confirm=True)
        self.assertEqual(result.writes, 0)
        self.assertEqual({tuple(r) for r in sqlite3.connect(self.db).execute(
            "select parent_id,child_id from task_links")}, {('old', 'qa')})

    def test_close_is_single_durable_transition(self):
        wf = self.reg.workflows["wf"]
        wf["latest_approved_reviewer"] = {"reviewer_id":"rev", "verdict":"PASS",
            "candidate_key":"abc", "candidate_hash":"h1"}
        wf["gate_statuses"] = {"qa_pass":"pass", "release_decision":"pass"}
        con = sqlite3.connect(self.db)
        con.execute("update tasks set status='done' where id in ('rev','qa')")
        con.commit(); con.close()
        reconciler = Reconciler(self.db, self.reg)
        plan = reconciler.plan()
        self.assertEqual([a["kind"] for a in plan.actions if a["kind"] == "workflow.closed"], ["workflow.closed"])
        self.reg.mode = "write"
        reconciler.apply(plan, confirm=True)
        self.assertEqual(wf["state"], "closed")
        self.assertFalse(any(a["kind"] == "workflow.closed" for a in reconciler.plan().actions))

    def test_edge_race_causes_zero_writes(self):
        wf = self.reg.workflows["wf"]
        wf["latest_approved_reviewer"] = {"reviewer_id":"rev", "verdict":"PASS",
            "candidate_key":"abc", "candidate_hash":"h1"}
        con = sqlite3.connect(self.db)
        con.execute("update tasks set status='done' where id='rev'")
        con.execute("insert into task_links values ('old','qa')")
        con.commit(); con.close()
        reconciler = Reconciler(self.db, self.reg)
        plan = reconciler.plan()
        con = sqlite3.connect(self.db)
        con.execute("insert into task_links values ('racer','qa')")
        con.commit(); con.close()
        self.reg.mode = "write"
        result = reconciler.apply(plan, confirm=True)
        self.assertEqual(result.writes, 0)
        self.assertTrue(any(c["kind"] == "edge_conflict" for c in result.conflicts))
        self.assertEqual({tuple(r) for r in sqlite3.connect(self.db).execute("select parent_id,child_id from task_links")},
                         {('old','qa'), ('racer','qa')})

if __name__ == "__main__": unittest.main()

#!/usr/bin/env python3
"""CLI for the registry-scoped lifecycle sidecar; all commands are dry-run by default."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .monitor import WorkflowMonitor
from .reconciler import Reconciler
from .registry import Registry, blocked_inventory, build_default_workflows, load_registry, save_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "inventory", "monitor", "reconcile"))
    parser.add_argument("--db", type=Path, default=Path.home() / ".hermes/kanban.db")
    parser.add_argument("--state-dir", type=Path, default=Path("operations/kanban"))
    parser.add_argument("--rebaseline", action="store_true")
    args = parser.parse_args(argv)
    registry_path = args.state_dir / "workflows.v1.json"
    if args.command == "init":
        reg = Registry(workflows=build_default_workflows())
        save_registry(reg, registry_path)
        print(json.dumps(reg.canonical(), ensure_ascii=False, indent=2)); return 0
    if args.command == "inventory":
        print(json.dumps(blocked_inventory(args.db), ensure_ascii=False, indent=2)); return 0
    reg = load_registry(registry_path)
    if not reg.workflows: reg.workflows = build_default_workflows()
    if args.command == "monitor":
        result = WorkflowMonitor(args.db, reg, args.state_dir / "state.json").run(rebaseline=args.rebaseline)
        if result.stdout: print(result.stdout)
        return 0
    reconciler = Reconciler(args.db, reg, registry_path=registry_path)
    plan = reconciler.plan()
    print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Hermes-runtime bridge for the dashboard's ephemeral PM assist turn."""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import sys

if importlib.util.find_spec('run_agent') is None:
    hermes_root = Path(sys.executable).resolve().parents[2]
    if (hermes_root / 'run_agent.py').exists():
        sys.path.insert(0, str(hermes_root))

from run_agent import AIAgent


def main() -> int:
    envelope = json.load(sys.stdin)
    prompt = str(envelope.get('prompt') or '')[:24000]
    agent = AIAgent(
        model='gpt-5.6-terra',
        provider='openai-codex',
        quiet_mode=True,
        skip_context_files=True,
        load_soul_identity=False,
        skip_memory=True,
        skip_background_review=True,
        enabled_toolsets=[],
        max_iterations=1,
        session_db=None,
    )
    agent._persist_disabled = True
    agent._session_db = None
    agent._session_json_enabled = False
    try:
        result = agent.run_conversation(json.dumps({'prompt': prompt}, ensure_ascii=False))
        output = str((result or {}).get('final_response') or '').strip()
        if len(output) > 50000:
            return 2
        sys.stdout.write(output)
        return 0
    finally:
        close = getattr(agent, 'close', None)
        if callable(close):
            close()


if __name__ == '__main__':
    raise SystemExit(main())

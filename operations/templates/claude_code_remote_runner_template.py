#!/usr/bin/env python3
from __future__ import annotations

# Template runner for a remote MacBook Claude Code worker.
# This file is not wired yet; it is a starter template for later deployment on the MacBook.

import json
from pathlib import Path

INBOX = Path.home() / 'agent-hub' / 'inbox' / 'claude-code'
RESULTS = Path.home() / 'agent-hub' / 'results'
LOGS = Path.home() / 'agent-hub' / 'logs'

for d in [INBOX, RESULTS, LOGS]:
    d.mkdir(parents=True, exist_ok=True)

print('Claude Code remote inbox runner template')
print('Inbox:', INBOX)
print('Results:', RESULTS)
print('Next step: implement actual Claude Code CLI invocation per brief JSON.')

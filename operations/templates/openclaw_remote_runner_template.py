#!/usr/bin/env python3
from __future__ import annotations

# Template runner for a remote MacBook OpenClaw worker.
# This file is not wired yet; it is a starter template for later deployment on the MacBook.

from pathlib import Path

INBOX = Path.home() / 'agent-hub' / 'inbox' / 'openclaw'
RESULTS = Path.home() / 'agent-hub' / 'results'
LOGS = Path.home() / 'agent-hub' / 'logs'

for d in [INBOX, RESULTS, LOGS]:
    d.mkdir(parents=True, exist_ok=True)

print('OpenClaw remote inbox runner template')
print('Inbox:', INBOX)
print('Results:', RESULTS)
print('Next step: implement actual OpenClaw invocation per brief JSON or gateway contract.')

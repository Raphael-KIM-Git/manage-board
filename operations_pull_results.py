#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

REMOTE = 'raphael@100.120.123.120:~/agent-hub/results/*'
LOCAL_DIR = Path('/home/raphael/myproject/operations/results')
KEY = '/home/raphael/.ssh/id_ed25519'

LOCAL_DIR.mkdir(parents=True, exist_ok=True)

cmd = [
    'scp',
    '-i', KEY,
    '-o', 'BatchMode=yes',
    '-o', 'IdentitiesOnly=yes',
    '-P', '22',
    REMOTE,
    str(LOCAL_DIR) + '/',
]

print('Running:', ' '.join(cmd))
proc = subprocess.run(cmd, text=True, capture_output=True)
print('exit_code:', proc.returncode)
if proc.stdout:
    print('stdout:\n' + proc.stdout)
if proc.stderr:
    print('stderr:\n' + proc.stderr)

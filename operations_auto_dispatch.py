#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path('/home/raphael/myproject/operations_dashboard_server.py')

spec = importlib.util.spec_from_file_location('ops_dashboard_server', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

result = module.auto_dispatch_queued()
print(json.dumps(result, ensure_ascii=False, indent=2))

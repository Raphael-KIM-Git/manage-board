# Slice A Dashboard browser retest (FIX-PROGRESS-1C)

## Verdict

**PASS for the scoped card-surface fix; review required before merge.** The task-card renderer now sanitizes projection action labels and exposes only a read-only detail-opening Next PM action plus the existing expand/collapse affordance. Resend, gate, live-note, final-review, and approval write controls are not rendered on task cards.

## Scope and safety

- Source: `/home/raphael/myproject`
- Isolated fixture: `/tmp/qa-fixture` served at `http://127.0.0.1:18766/`
- Fixture refresh: copied only `operations_dashboard/app.js` from the candidate tree; server endpoints and operational data were unchanged.
- Browser executable: `/home/raphael/.local/bin/playwright-chromium-userlocal`
- No production deployment, commit, push, or state-changing HTTP request was made.

## Source/static assertion

Command:

```bash
python3 -m unittest -v tests.test_dashboard_static_contract
```

Result: **28 tests passed**. The new `test_task_cards_only_expose_read_only_detail_actions` assertion covers the card renderer, detail-opening handler, and forbidden resend/gate/live-note/final-review/override control paths.

## Browser matrix

Command:

```bash
uv run --with playwright python3 qa_slice_a_browser.py
```

Result: **PASS**.

| Viewport | Cards | innerWidth | scrollWidth | Forbidden controls |
|---|---:|---:|---:|---|
| 1440 x 1000 | 24 | 1440 | 1440 | none |
| 1024 x 1000 | 24 | 1024 | 1024 | none |
| 390 x 844 | 24 | 390 | 390 | none |

The script observed no console errors, no failed requests, and no non-GET requests. Evidence JSON: `docs/qa/evidence-slice-a/QA-PROGRESS-1C-browser-matrix.json`.

## Representative interaction

Command:

```bash
uv run --with playwright python3 qa_slice_a_interaction.py
```

Result: **PASS**.

- Representative card: `T-20260729-001` / 삼성펀드.
- Read-only primary action: `작성 결과 도착 확인`.
- Click opened the task detail with the expected representative title and progress/evidence body.
- Escape closed the task detail and returned focus to the originating card action.
- No non-GET request occurred.

Evidence JSON: `docs/qa/evidence-slice-a/QA-PROGRESS-1C-interaction.json`; screenshot: `docs/qa/evidence-slice-a/interaction.png`.

## Regression and syntax checks

Commands and results:

```bash
uv run --with pytest python3 -m pytest -q
# 64 passed in 0.18s

node --check operations_dashboard/app.js
# exit 0

python3 -m compileall -q operations_dashboard_projection.py operations_dashboard_server.py tests
# exit 0

git diff --check
# exit 0
```

## Changed implementation

- `operations_dashboard/app.js`: added `cardDetailActionLabel(task)` to prevent mutation-oriented projection labels from becoming card controls; task cards retain one detail-opening primary action and the existing secondary expand/collapse control.
- `tests/test_dashboard_static_contract.py`: added static regression coverage for forbidden card controls and shared detail-opening behavior.

Existing unrelated working-tree modifications were preserved.

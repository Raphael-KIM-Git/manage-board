# Dashboard dirty-worktree review manifest

- Snapshot root: `/home/raphael/myproject`
- Snapshot basis: working tree at inspection time; `HEAD=26b3fa476462c1eef5df70b2594a1e8a75f548c1`, branch `main`.
- Safety: read-only inspection only. No file was staged, committed, pushed, deployed, restarted, or otherwise mutated by this review. The two manifest files are the only new review artifacts written by this task.
- Source of task attribution: exact Kanban handoffs/comments for `t_86a63115`, `t_1631cefc`, and `t_44e06f2c`. A path is not attributed merely because its name looks related.
- SHA-256 values and complete machine-readable inventory are in `DASHBOARD-REVIEW-MANIFEST.json`.

## Executive verdict

The worktree is not safely reviewable as three independent code candidates. The three candidates share `operations_dashboard_server.py` and the browser shell (`app.js`, `styles.css`; Slice 1 also changes `index.html`), while artifact/viewer contracts and producer changes cross the same projection/UI paths. Review must therefore be read-only and manifest-driven, not a file-by-file merge from the dirty tree.

Safe order:

1. Freeze this snapshot and review the baseline boundary against `26b3fa4`.
2. Review the isolated Slice 1 evidence lane (`t_86a63115`) first: sync/watchdog and projection/API contracts, then its UI additions.
3. Review the artifact/producer lane only after Slice 1 projection semantics are accepted; it shares final-deliverable projection and viewer/static-contract files.
4. Review follow-up intake (`t_1631cefc`) after the shared server/UI boundary is understood; verify sidecar writes and parent invariance independently.
5. Review Console v2 backend (`t_44e06f2c`) after v1.1 semantics; its server integration overlaps both previous candidates.
6. Any implementation merge must be reconstructed in an isolated branch/worktree or from an explicit allowlisted patch. Do not stage/commit this shared tree.

Prerequisite graph: `26b3fa4 baseline -> t_86a63115 Slice 1 -> artifact/viewer contract -> t_1631cefc follow-up intake -> t_44e06f2c Console v2 backend`. The last three arrows are review-order dependencies, not claims that the Kanban board currently links them.

## Candidate allowlists and exact snapshot locators

### C1 — `t_86a63115` (v1.1 Slice 1 sync/watchdog evidence)

Allowlist from its handoff and current evidence:

- `operations_dashboard_projection.py` — `project_operations_evidence`, `project_final_deliverable`, derived-attempt projection; current lines 1–1300, exact changed hunks in `git diff --unified=0`.
- `operations_dashboard_server.py` — additive operations-evidence loading/API projection integration; **shared** with C2 and C3.
- `operations_dashboard/app.js` — operations evidence and final-deliverable rendering; **shared** with artifact/viewer and C2.
- `operations_dashboard/index.html` — operations evidence panel and modal layer hooks; **shared** with artifact/viewer.
- `operations_dashboard/styles.css` — evidence/detail styling; **shared** with C2 and viewer styling.
- `tests/test_dashboard_projection.py` — operations evidence, final-deliverable and derived-attempt regression cases.
- `tests/test_dashboard_static_contract.py` — **shared** with viewer/modal contract tests.
- `operations_sync.py`, `test_operations_sync.py` — research policy, exact stage-envelope correlation, sync evidence.
- `operations_watchdog.py`, `tests/test_operations_watchdog.py`, `operations/config/research-evidence-policy.v1.json`, `operations/sync/latest.json`, `operations/watchdog/latest.json`, `operations/watchdog/state.json` — watchdog/policy/evidence runtime snapshot lane.

Exact symbol locators in this snapshot: `operations_dashboard_projection.py:96` (`project_operations_evidence`), `operations_dashboard_projection.py:395` (`project_final_deliverable`), `operations_sync.py:306` (`stage_result_envelopes`), `operations_dashboard/app.js:1709` (`renderOperationsEvidence`).

Review status: C1 is independently reviewable only for the sync/watchdog and pure projection portions. Server/browser files are coupled to C2 and artifact/viewer and require a split patch before merge.

### C2 — `t_1631cefc` (v1.1 follow-up request intake)

Allowlist from its handoff and current evidence:

- `operations_followup_requests.py`
- `operations_dashboard_server.py` — **shared** with C1 and C3; follow-up routes must be reviewed separately from console routes.
- `operations_dashboard/app.js`, `operations_dashboard/styles.css` — **shared** with C1 and artifact/viewer.
- `tests/test_operations_followup_requests.py`
- `tests/test_dashboard_http_writes.py`

Required safety checks: append-only sidecar, same-origin and JSON gates, idempotency retry/conflict, atomic write cleanup, draft retention on failed save, `pending_pm_review`, `parent_task_changed=false`, no dispatch/approval/reopen. Existing handoff reports 89 focused tests passed and browser startup was blocked by missing `libnspr4.so`; that limitation remains a prerequisite for browser acceptance.

Exact symbol locators in this snapshot: `operations_followup_requests.py:113` (`list_requests`), `operations_followup_requests.py:130` (`submit_request`), `operations_dashboard_server.py:1412` (`_followup_origin_allowed`), `operations_dashboard_server.py:1513` (`Handler.do_POST` follow-up route), `operations_dashboard/app.js:1487` (`renderFollowUpPanel`).

Review status: backend/domain can be reviewed independently. Server and UI cannot be accepted as an isolated candidate until the overlapping C1/C3 hunks are split.

### C3 — `t_44e06f2c` (v1.2 Console projection/API and instruction store)

Allowlist from its handoff and current evidence:

- `dashboard_instructions.py`
- `operations_dashboard_console.py`
- `operations_dashboard_server.py` — **shared** with C1 and C2.
- `tests/test_dashboard_console_v2.py`

Required safety checks: schema v2 single snapshot, exact task index, explicit `project_ref`/unassigned only, stage-scoped agent aggregation, pane failure isolation, append-only instruction store, actor/capability/same-origin/payload/idempotency checks, `submitted_pending_pm_review`, `parent_changed=false`, preserved old endpoints. Existing handoff reports 81 tests passed; loopback HTTP smoke was unavailable in that sandbox, so Handler transport review remains required.

Review status: backend projection/store is independently reviewable. The server integration is coupled to C1/C2 and cannot be accepted from the dirty file without a diff split.

Exact symbol locators in this snapshot: `operations_dashboard_console.py:118` (`project_console_snapshot`), `dashboard_instructions.py:107` (`submit_instruction`), `operations_dashboard_server.py:826` (`build_dashboard_console`), `operations_dashboard_server.py:1421` (`Handler.do_GET` console route), `operations_dashboard_server.py:1513` (`Handler.do_POST` instruction route).

### C4 — artifact/producer/viewer-related untracked candidate

Evidence-backed related paths:

- `artifact_contract.py`, `tests/test_artifact_contract.py`
- `hermes_local_runner.py`, `tmp_worker_runner.py` — producer manifest emission; also changed as tracked files and **not attributed to C1/C2/C3 handoffs**.
- `Agent-Hub-Dashboard-v1.1-artifact-producer-contract-ko.md`
- `Agent-Hub-Dashboard-v1.1-final-artifact-viewer-PRD-ko.md`
- `operations_dashboard_projection.py`, `operations_dashboard/app.js`, `operations_dashboard/index.html`, `operations_dashboard/styles.css`, `tests/test_dashboard_projection.py`, `tests/test_dashboard_static_contract.py` — **shared with C1/C2**; final-deliverable and top-layer viewer portions cannot be separated by filename alone.

The PRD explicitly forbids choosing a final artifact by filename, mtime, or array order and requires exact artifact binding. The current representative fixture is intentionally ambiguous (`final_write=skipped`, multiple HTML candidates, unbound review), so a safe review must preserve `artifact=null`/`ambiguous` rather than promote a candidate.

Review status: C4 requires a focused isolation/correction patch for shared projection/UI files. Do not review it as an independently mergeable untracked bundle.

Exact symbol locators in this snapshot: `artifact_contract.py:48` (`validate_artifact_manifest`), `artifact_contract.py:98` (`emit_artifact_manifest`), `operations_dashboard_projection.py:395` (`project_final_deliverable`), `operations_dashboard/app.js:35` (`syncModalCoordinator`), `operations_dashboard/app.js:1674` (`renderFinalDeliverable`).

## Ambiguous, mixed, or unattributed paths

The following are present in the snapshot but have no exact changed-file attribution in the three supplied developer handoffs, or are cross-cutting runtime/QA artifacts. They must not be silently assigned to a candidate:

- `ensure-agent-hub-services.sh` — watchdog/service supervisor behavior; likely operational recovery, not a C1/C2/C3 application patch.
- `qa_slice_a_browser.py`, `qa_slice_a_interaction.py`, `docs/qa/QA-PROGRESS-1B-slice-a-browser-acceptance-ko.md`, and the three `docs/qa/evidence/deployed-*.png` files — QA/evidence artifacts; review separately from implementation.
- `Agent-Hub-Kanban-Lifecycle-Autocontinue-Plan-ko.md`, `operations/kanban/*`, `tests/test_kanban_lifecycle.py` — Kanban lifecycle lane, not evidenced as one of the three Dashboard candidates.
- `operations/config/research-evidence-policy.v1.json`, `operations/sync/latest.json`, `operations/watchdog/*` are listed in C1 only because their contents are directly consumed by the C1 sync/watchdog changes; their generated/runtime provenance still needs reviewer confirmation.
- `Agent-Hub-Dashboard-v1.2-4quadrant-console-UX-UI-design-ko.md`, `Agent-Hub-Dashboard-v1.2-PM-operation-policy-decisions-ko.md`, and `Agent-Hub-Dashboard-v1.2-quadrant-operations-console-PRD-ko.md` are planning/design/policy inputs, not implementation allowlist files.

Tracked shared overlap that makes blind review unsafe: `operations_dashboard_server.py` (C1+C2+C3), `operations_dashboard/app.js` (C1+C2+C4), `operations_dashboard/styles.css` (C1+C2+C4), `operations_dashboard/index.html` (C1+C4), `operations_dashboard_projection.py` (C1+C4), and `tests/test_dashboard_projection.py`/`tests/test_dashboard_static_contract.py` (C1+C4).

## Test commands by candidate

- C1 focused: `python3 -m unittest tests.test_dashboard_projection tests.test_dashboard_api_contracts tests.test_dashboard_static_contract tests.test_operations_watchdog test_operations_sync`; `node --check operations_dashboard/app.js`; `git diff --check`.
- C2 focused: `python3 -m unittest -v tests.test_operations_followup_requests tests.test_dashboard_projection tests.test_dashboard_api_contracts tests.test_dashboard_static_contract tests.test_artifact_contract tests.test_operations_watchdog test_operations_sync`; `python3 -m py_compile operations_followup_requests.py operations_dashboard_server.py`; `node --check operations_dashboard/app.js`; `git diff --check`.
- C3 focused: `python3 -m unittest discover -s tests -p 'test*.py'`; `python3 -m py_compile dashboard_instructions.py operations_dashboard_console.py operations_dashboard_server.py`; `git diff --check`; direct `build_dashboard_console()` fixture check. Loopback HTTP smoke must be rerun in an environment that permits loopback.
- C4 focused: `python3 -m unittest tests.test_artifact_contract tests.test_dashboard_projection tests.test_dashboard_static_contract`; `python3 -m py_compile artifact_contract.py hermes_local_runner.py tmp_worker_runner.py`; `node --check operations_dashboard/app.js`; `git diff --check`; verify SHA-256 against producer manifest rules.
- Cross-candidate gate after isolation: `python3 -m unittest discover -s tests -p 'test*.py'` plus browser matrix at 1440/768/390 when Chromium dependencies are available. Do not treat prior handoff counts as current execution output.

## Limitations and non-reviewable items

- This manifest is a snapshot, not proof that the dirty tree can be merged.
- No commit/branch locator exists for the three candidate implementations; their handoffs identify paths and test evidence but not immutable commits.
- Shared paths contain multiple semantic changes with no patch ownership boundary. They are unsafe to cherry-pick or approve wholesale.
- Browser evidence is not reproducible in the prior C2 handoff because WSL Chromium exited with missing `libnspr4.so`; static/API evidence is not a substitute for browser acceptance.
- `operations/sync/latest.json` and watchdog state are generated observations, not source code; their freshness and provenance must be checked before treating them as acceptance evidence.
- Any file with no exact attribution above is `unassigned` until a focused isolation/correction task supplies a locator.

## Exact snapshot inventory

See `DASHBOARD-REVIEW-MANIFEST.json` for every tracked modified/untracked file, SHA-256, candidate classification, overlap flags, and review status. The JSON is the machine-readable source of truth for this document.

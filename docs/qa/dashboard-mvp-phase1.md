# Dashboard MVP Phase 1 — E3 acceptance evidence

## Verdict

**PASS (browser/manual gate complete in isolated synthetic fixture).** Static contracts, projection/API safety checks, syntax/compile checks, regression tests, and real Chromium renders at desktop/tablet/compact widths pass. Browser console/page-error checks and key modal/detail interactions pass. No production/operational write was issued.

## Baseline and environment

- Baseline/final HEAD: `66ecbe8e63281593d0ad0fb3bad4fd71ff7b1fba`
- `origin/main`: same commit
- Date/time: `2026-07-28T08:15:58+09:00`
- Environment: WSL/Linux, Python 3.11.15, Node v22.22.3
- Initial Git command: `git status --short --branch`
- Initial/final status (protected root-untracked files unchanged):
  ```text
  ## main...origin/main
  ?? operations/watchdog/
  ?? operations_watchdog.py
  ?? tests/test_operations_watchdog.py
  ```
- Protected files were not read-modified, staged, committed, deployed, or deleted.
- Changed files in this task: `docs/qa/dashboard-mvp-phase1.md` and four screenshot artifacts under `docs/qa/evidence/`.
- Browser evidence captured under `docs/qa/evidence/` from the local synthetic fixture server: `phase1-desktop.png`, `phase1-tablet.png`, `phase1-compact.png`, and `phase1-interaction.png`.

## Commands and results

From `/home/raphael/myproject`:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

PASS — HEAD and origin/main both resolve to `66ecbe8e63281593d0ad0fb3bad4fd71ff7b1fba`; only the three protected root-untracked entries are present.

```bash
python3 -m unittest -v \
  tests.test_dashboard_projection \
  tests.test_dashboard_api_contracts \
  tests.test_dashboard_static_contract \
  test_operations_sync \
  tests.test_ouroboros_seed_workflow
```

PASS — **58 tests**, all passed in 0.033s. This includes projection fail-safe/authority cases, additive API view contracts, existing write-contract checks using temporary directories, DOM/JS static IA checks, responsive/touch-target contracts, and sync/seed regression.

```bash
node --check operations_dashboard/app.js
```

PASS — exit 0.

```bash
python3 -m compileall -q \
  operations_dashboard_projection.py operations_dashboard_server.py \
  operations_sync.py operations_auto_dispatch.py operations_pull_results.py tests
```

PASS — exit 0.

```bash
git diff --check
```

PASS — exit 0.

```bash
curl -fsS http://127.0.0.1:18765/api/health
```

PASS — isolated fixture returned `{"ok": true, "host": "127.0.0.1", "port": 18765}`. This was a GET-only smoke; no production endpoint was contacted.

## Browser execution and evidence

- Runner: Windows Chrome Headless `150.0.7871.186`, connected from WSL through CDP on `127.0.0.1:9222`.
- Target: `http://127.0.0.1:18765`, an isolated copy at `/tmp/qa-fixture` with the repository dashboard and copied operation fixtures. The source worktree and canonical operation state were not used for writes.
- Viewports and screenshots: desktop `1440x1000` (`evidence/phase1-desktop.png`), tablet `1024x1000` (`evidence/phase1-tablet.png`), compact `390x844` (`evidence/phase1-compact.png`). Screenshots are full-page captures.
- DOM/layout observations: section order is `missionControlHeader → decisionQueue → activeWorkBoard → reviewableArtifacts → recentAudit`; task-board columns were 3/2/1 at desktop/tablet/compact; compact hero actions switched to grid; all three widths had no horizontal overflow.
- Interaction evidence (`evidence/phase1-interaction.png`): brief modal visible-dialog count changed `0 → 1 → 0` after click and Escape; first `산출물 검토` action opened Task Detail for `CJ프레시밀 프론트/관리자 페이지 개선 및 고도화 제안서 작성`.
- Console/page errors: first matrix pass had one transient `ERR_SOCKET_NOT_CONNECTED` from the CDP/browser process during compact navigation; an independent compact rerun recorded **0 console messages and 0 failed requests**, and the final interaction pass recorded no console errors. No application/page errors were observed.
- Visible control heights in the independent compact rerun were 44px minimum (hero controls 47px), satisfying the touch-target contract. No POST/PUT/PATCH/DELETE request was observed during the read-only browser smoke.

## Acceptance matrix

| ID | Result | Evidence / limitation |
|---|---|---|
| QA-01 | PASS | Automated ordering hooks pass; real DOM order is Mission Control → Decision Queue → Active Work → Reviewable Artifacts → Recent Audit at all three viewports; screenshot evidence captured. |
| QA-02 | PASS | Automated outcome-first contract passes; rendered queue cards expose title/outcome/status/verification context and a single `산출물 검토` CTA; screenshot evidence captured. |
| QA-03 | PASS | Projection/renderer compact contracts pass; compact render hides gate-heavy detail from the board and remains readable in `phase1-compact.png`. |
| QA-04 | PASS | Raw gate audit/detail contracts pass; Task Detail opened successfully from the first artifact review action; interaction screenshot captured. |
| QA-05 | PASS (automated) | Five pipeline shapes and description-only behavior pass in projection tests; renderer label contract passes. |
| QA-06 | PASS (automated) | Missing/null/unknown distinctions, raw preservation, and fail-safe rendering tests pass. |
| QA-07 | PASS | Mid-gate `proceed` is not final approved in projection tests; rendered gate status/copy is present in the browser fixture. |
| QA-08 | PASS (automated) | Active hold takes precedence over positive final raw evidence; ambiguity prevents automatic approval. |
| QA-09 | PASS | Live notes remain non-decision context and do not create normalized decisions; current audit surface rendered without browser errors. |
| QA-10 | PASS (automated) | No unblock/scope-changed inference from absent source events. |
| QA-11 | PASS | Authority remains raw-only with decision-none/unknown/history-unavailable states; no fabricated intent, actor, correlation, or version; browser surface rendered successfully. |
| QA-12 | PASS (contract test) | `test_gate_override_contract` verifies valid `revise`, invalid action rejection, and temporary-state raw write shape. No operational POST issued. |
| QA-13 | PASS (contract test) | `test_final_review_and_live_note_contract` verifies final-review response and invalid action rejection in temporary state. No operational POST issued. |
| QA-14 | PASS (contract test) | Same test verifies live-note storage without `normalized_decision`; no operational POST issued. |
| QA-15 | PASS | Task Detail opened from a rendered artifact card; title and detail panel were present, with screenshot evidence. |
| QA-16 | PASS | Artifact ambiguity remains visible (`산출물 대상 불명확`) and the review CTA precedes the detail flow; browser interaction succeeded. |
| QA-17 | PASS | Real 1440/1024/390 renders pass with 3/2/1 task-board columns, compact grid actions, no horizontal overflow, and screenshots. |
| QA-18 | PASS | Semantic dialogs render; Escape closes the brief modal; visible buttons meet the measured 44px minimum touch target. |
| QA-19 | PASS (static) | Static contract confirms no Discord/channel/sync/deep-link surface in dashboard HTML and no forbidden cross-surface copy. |
| QA-20 | PASS | 58-test regression command, Node syntax, Python compile, diff check, and isolated browser smoke all pass. No operational write was issued. |

## Scope and safety confirmation

- Only the evidence document and its four screenshot artifacts were created/changed by this task.
- No production UI/API/state/persistence/schema code was changed.
- No `operations_sync.py`, generic decision API, dual-write, Discord/channel integration, cron, infrastructure, deployment, or restart work was performed.
- No operational POST/PUT/DELETE was issued.
- Automated API contract tests used temporary directories and synthetic task data; they did not mutate canonical `operations/briefs`.
- No operational JSON was used as a test fixture or rewritten.

## Retest recommendation

No retest is required for this gate. If the dashboard UI or responsive CSS changes, rerun the same isolated fixture matrix and compare the four evidence screenshots; do not use this evidence as an operational deployment or write-path verification.

## Deployed-target browser retest — 2026-08-02

### Verdict

**NEEDS_RETEST for the configured Playwright browser gate; direct Chromium/CDP acceptance is otherwise PASS for the exercised read-only paths.** The configured browser tool could not load the deployed target: `browser_navigate("http://100.113.23.118:8765/")` failed before page load with `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc0 in position 49`. A local Chrome for Testing 151.0.7922.34 process connected through CDP was used as a documented fallback; it rendered the same service at `http://127.0.0.1:8765/` and produced the evidence below.

### Baseline and safety

- Requested baseline: `deaf80c8c4f2a14ade6bf442a981c91620bb6a13`.
- Actual worktree and `origin/main` at retest: `26b3fa476462c1eef5df70b2594a1e8a75f548c1` (not the requested baseline); this limitation is recorded rather than treated as baseline-equivalent.
- Service health: `GET http://127.0.0.1:8765/api/health` returned HTTP 200, `{"ok": true, "host": "0.0.0.0", "port": 8765}`.
- Browser CDP request log contained only `GET` requests for the document, static assets, read-only API endpoints, and `GET /api/tasks/T-20260729-001/follow-up-requests`; no POST/PUT/PATCH/DELETE request was observed.
- No production application code or operational data was changed. Three screenshot files were added under `docs/qa/evidence/`.

### Browser commands/actions and evidence

- Browser executable: `~/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome` (`Google Chrome for Testing 151.0.7922.34`).
- Browser command: `CHROME="$HOME/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"; "$CHROME" --headless=new --no-sandbox --disable-gpu --remote-debugging-port=9222 --user-data-dir=<temporary-profile> about:blank`.
- CDP actions: enable Runtime/Log/Page/Network; set viewport metrics to `1440x1000`, `1024x1000`, and `390x844`; navigate to `http://127.0.0.1:8765/`; wait for `document.readyState === "complete"`; evaluate section positions/labels, `scrollWidth > innerWidth`, Agent Stage text presence, and visible button heights; capture full-page PNG; click the first visible safe `상세 보기` button; verify one task-detail modal becomes `aria-hidden="false"`; dispatch Escape; verify it returns to `aria-hidden="true"` and modal lock count `0`.
- Screenshots (exact paths):
  - `docs/qa/evidence/deployed-desktop-20260802.png` — 2,699,581 bytes (1440x1000 viewport; full-page capture).
  - `docs/qa/evidence/deployed-tablet-20260802.png` — 1,562,610 bytes (1024x1000 viewport; full-page capture).
  - `docs/qa/evidence/deployed-compact-20260802.png` — 1,393,985 bytes (390x844 viewport; full-page capture).
- CDP console findings: `console []`; `errors []` (no console API messages, runtime exceptions, or Log errors in the final run).

### Acceptance matrix

| Criterion | Result | Evidence / limitation |
|---|---|---|
| Desktop section order Decision Queue → Active Work → Reviewable Artifacts → Recent Audit | PASS (CDP fallback) | DOM top positions were `431.02 < 3655.41 < 14213.11 < 15065.34`; labels matched the required order. |
| Desktop Agent Stage absent | PASS (CDP fallback) | `document.body.innerText.includes("Agent Stage")` returned `false`. |
| Desktop console errors | PASS (CDP fallback) | `console []`, `errors []`. Configured browser tool itself remains unavailable. |
| Tablet same hierarchy | PASS (CDP fallback) | DOM top positions were `500.75 < 3725.14 < 14345.95 < 15784.03`; labels matched. |
| Tablet no horizontal overflow | PASS (CDP fallback) | `innerWidth=1024`, `scrollWidth=1009`; overflow predicate `false`. |
| Compact queue-first ordering | PASS (CDP fallback) | DOM top positions were `901.41 < 5655.80 < 17066.61 < 18846.69`; Decision Queue was first among required sections. |
| Compact cards readable / target intent | PASS (CDP fallback) | 24 task cards rendered; visible action buttons measured 44px minimum (hero controls 45px). Screenshot confirms single-column cards. |
| Compact Agent Stage absent | PASS (CDP fallback) | Agent Stage text predicate returned `false`. |
| Safe detail open and Escape close | PASS (CDP fallback) | `상세 보기` opened `taskDetailModal` (`aria-hidden=false`, lock count 1); Escape closed it (`aria-hidden=true`, lock count 0). |
| No write controls activated | PASS | Only GET requests were observed in the CDP request log. |
| Configured Playwright MCP/browser tool | NEEDS_RETEST | `browser_navigate` failed before page load with the UTF-8 decode error; no screenshot or target console result was available from that tool. |
| Requested commit baseline | NEEDS_RETEST | Actual HEAD/origin is `26b3fa4`, not requested `deaf80c8`; rerun against the specified commit or revise the baseline explicitly. |

### Gate decision

**Phase 1 browser gate cannot close as a configured-tool/baseline-compliant PASS.** The direct Chromium/CDP fallback demonstrates the responsive/read-only behavior on the currently served revision, but a final closure requires a working configured Playwright browser session and confirmation that the deployed service corresponds to the requested `deaf80c8` baseline (or an explicit baseline update).

# QA-V11-1 Dashboard v1.1 브라우저·접근성·실패 QA

## VERDICT: FAIL

Active candidate를 실제 loopback HTTP 서버(`127.0.0.1:18766`)와 Chromium Headless에서 검증했다. 반응형/기본 키보드 동작은 대체로 통과했지만, 대표 task의 evidence projection이 canonical raw 사실을 누락하고, 인증되지 않은 환경에서 follow-up write composer가 활성화되는 blocker가 있어 승인할 수 없다.

## 환경 및 명령

- Repository: `/home/raphael/myproject`
- Server: `OPS_DASHBOARD_HOST=127.0.0.1 OPS_DASHBOARD_PORT=18766 python3 operations_dashboard_server.py`
- Browser: Playwright Chromium `/home/raphael/.local/bin/playwright-chromium-userlocal`
- Browser commands:
  - `uv run --with playwright python3 /tmp/qa_inspect.py`
  - `uv run --with playwright python3 /tmp/qa_related.py`
  - `uv run --with playwright python3 /tmp/qa_detail2.py`
  - `uv run --with playwright python3 /tmp/qa_followup.py`
  - `uv run --with playwright python3 /tmp/qa_refresh.py`
- Regression: `python3 -m unittest -v tests.test_operations_followup_requests tests.test_dashboard_projection tests.test_dashboard_api_contracts tests.test_dashboard_static_contract tests.test_artifact_contract tests.test_operations_watchdog test_operations_sync` → **91 passed**
- Syntax: `node --check operations_dashboard/app.js`, Python compile checks → **PASS**

## Viewport matrix

| viewport | scrollWidth | result |
|---|---:|---|
| 1440×1000 | 1440 | PASS, no horizontal overflow |
| 1024×1000 | 1024 | PASS, no horizontal overflow |
| 390×844 | 390 | PASS, no horizontal overflow |

Screenshots:
- `docs/qa/evidence-v11/qa-desktop.png`
- `docs/qa/evidence-v11/qa-tablet.png`
- `docs/qa/evidence-v11/qa-compact.png`

## Acceptance matrix

| criterion | verdict | evidence |
|---|---|---|
| 1440/1024/390 responsive layout | PASS | Playwright `scrollWidth == innerWidth` at all three viewports |
| task card has no write CTA | PASS | Visible surface exposes detail/read-only controls; no resend/gate/live-note/final-review card control |
| representative `T-20260729-001` raw/stage/attempt/final skipped | PASS/PARTIAL | Detail shows writing `completed`, active attempt `...writing-r1`, final write skipped in timeline |
| representative result/verification/PM review evidence | **FAIL** | Detail shows `VERIFICATION not_run`, `PM FINAL REVIEW not_run`, and candidate artifacts 0; canonical raw has verification stage completed, verify envelope, and `pm_final_review.verdict=meets` (brief JSON lines 79–92, 164–167) |
| stale watchdog/sync copy | PASS | Detail visibly labels Sync success with task transition 0 and Watchdog stale with `freshness_threshold_exceeded` |
| keyboard open, focus return, Escape | PASS | `관련 업무` opened task detail; initial focus was `닫기`; Escape closed visible modal and returned focus to originating `관련 업무` control |
| focus trap | PASS | Tab sequence remained on detail controls/file references while detail was open |
| label association / validation | PARTIAL | Four labels contain the controls and required attributes exist, but empty required submit is blocked by native validation and `.followup-status` remains empty; no explicit error message or `aria-describedby`/error association was observed |
| follow-up composer detail-only | PASS | Composer appears after opening task detail; overview/card surfaces showed no follow-up form |
| draft survives refresh/reopen | PASS | Filled long Korean title survived detail close/reopen; automatic refresh observed at ~15s (each `/api/*` count 2 after 17s) |
| successful submit clears draft | NOT RUN | No state-changing request was made against canonical operation data |
| network failure/retry | PARTIAL | Source catch path preserves draft and displays `저장 실패 — 초안은 유지됩니다`; browser-side failure injection not run against real write path |
| duplicate click/idempotency/stale version/save failure | PASS (unit/API), browser submit NOT RUN | Focused suite covers idempotency, concurrent dedupe, conflicts, stale/validation/write failure; no production-side browser POST issued |
| long Korean content overflow | PASS | Long title filled in compact detail; no horizontal overflow (`scrollWidth=390`) |
| color-only state distinction | NEEDS RETEST | Text labels exist for state; visual contrast/screenshot color contrast not measured with axe/contrast tool |

## Blocking findings

### F-01 — HIGH: unauthenticated follow-up write is enabled

Reproduction:
1. Start server with the command above, with no authenticated principal.
2. Open `http://127.0.0.1:18766/`.
3. Open `관련 업무` for the representative project.
4. The detail includes active `새 요청` form and `PM 재평가 요청 제출`.
5. `/api/follow-up-request-capabilities` reports write enabled in this environment.

Expected: capability must be disabled unless authenticated principal and CSRF/origin prerequisites are both satisfied.
Actual: write composer is enabled; parent security verification separately reproduced forged same-origin `Origin`/`Host` POST as actor `Raphael`, returning 201 and persisting a request.

Correction scope: require authenticated principal plus CSRF validation; fail closed to read-only when unavailable; add HTTP regression. Do not merge/deploy before retest.

### F-02 — HIGH: representative evidence projection loses completed verification and PM review

Reproduction:
1. Open representative `T-20260729-001` through `관련 업무`.
2. Read Artifact Review and Final Deliverable sections.

Expected: independent facts must remain visible: verification stage completed + verify result envelope, PM review record exists (`meets`) but is unbound, and final write skipped.
Actual: detail says `VERIFICATION not_run`, `검증 근거를 사용할 수 없습니다 — 검증 미실행`, and `PM FINAL REVIEW not_run`, while the canonical brief contains verification stage `completed`, derived `T-20260729-001-verify`, and `pm_final_review.verdict=meets`. This is a false negative and prevents correct user judgment.

Correction scope: trace `/api/tasks` projection and verification/PM-review loaders for exact task/derived IDs; preserve unbound review as `PM 검토 기록 있음 · 대상 산출물 연결 확인 필요`, not `not_run`; add browser/API regression for the representative fixture.

### F-03 — MEDIUM: required-field error has no visible/assistive error association

Reproduction:
1. Open representative detail and follow-up form.
2. Submit with title and desired outcome empty.

Actual: browser native required blocking occurs; `.followup-status` stays empty. No explicit error text or `aria-describedby` linkage is emitted.

Correction scope: render an explicit error message with stable id, associate invalid fields via `aria-describedby`/`aria-invalid`, and verify keyboard/screen-reader path.

## Non-blocking / retest notes

- No production/canonical POST was sent; screenshot and browser evidence are read-only.
- Focused unit/API tests are green but do not cover the projection mismatch or unauthenticated capability path.
- The browser tool wrapper itself failed decoding the HTML response (`UnicodeDecodeError`); Playwright Chromium was used instead and produced reproducible evidence.
- Required retest: rerun all three viewport screenshots, representative detail evidence, capability endpoint with unauthenticated and authenticated cases, and intercepted network-failure/submit-success browser tests after correction.

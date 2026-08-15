# Slice A Dashboard browser/manual release acceptance

## Verdict

**NEEDS_RETEST / FAIL for strict release acceptance.** The representative Slice A flow renders and behaves read-only as intended at all three requested viewport sizes, and the representative `T-20260729-001` copy correctly distinguishes research results from writer waiting and verification not run. However, the rendered dashboard still exposes `다시 전송` controls on other task cards, which violates the required absence of card resend controls. This is a product acceptance failure, not a browser/environment failure.

## Scope and safety

- Source: `/home/raphael/myproject`, candidate working tree (read-only inspection).
- Target: `http://127.0.0.1:18766/` served from isolated fixture `/tmp/qa-slice-a-fixture`.
- Fixture: copied `operations/` and `operations_dashboard/` from the repository; writer result sidecars for `T-20260729-001` were removed from the fixture only to reproduce the source-approved representative state (research 3/3 received, writer pending, verification not run). Canonical operational files were not modified.
- Runner command: `uv run --with playwright python3 qa_slice_a_interaction.py` and `uv run --with playwright python3 qa_slice_a_browser.py`.
- Browser executable: `/home/raphael/.local/bin/playwright-chromium-userlocal`.
- No production deployment, commit, push, or state-changing HTTP request was made.

## Browser evidence

- `docs/qa/evidence-slice-a/desktop.png` — 1440 x 1000
- `docs/qa/evidence-slice-a/tablet.png` — 1024 x 1000
- `docs/qa/evidence-slice-a/compact.png` — 390 x 844
- `docs/qa/evidence-slice-a/interaction.png` — compact task-detail interaction capture

The first matrix run captured desktop/tablet/compact dimensions and DOM state. The focused interaction run waited 15 seconds for the large task response to settle, then exercised the representative card.

## Observed results

### Responsive/layout

- 1440px: `innerWidth=1440`, `scrollWidth=1440`; no horizontal overflow.
- 1024px: `innerWidth=1024`, `scrollWidth=1024`; no horizontal overflow.
- 390px: `innerWidth=390`, `scrollWidth=390`; no horizontal overflow.
- DOM order observed at all widths: `missionControlHeader → decisionQueue → activeWorkBoard → reviewableArtifacts → recentAudit → secondaryAgentContext`.
- Card information order observed: title/objective → current stage/progress → agent progress → pipeline → artifact/verification → trust/limits → authority → next action.
- Status cues use text and symbols (e.g. `✓`, `•`, `–`, `전송 확인 · 결과 대기`, `결과 도착`, `검증 미실행`), not color alone.

### Representative card (`T-20260729-001`)

Observed rendered copy:

- `작성 진행 중 · 완료 1/4 · 생략 1`
- `리서치 완료 · 결과 도착 · writer-co · 전송 확인 · 결과 대기`
- `리서치 결과 도착 · 작성 결과 없음 · 검증 미실행`
- primary action: `작성 결과 도착 확인`
- secondary card control: `상세 보기`

Task detail opened with title `삼성펀드 홈페이지 운영 헬스체크 및 UI/UX 개선안 도출`. Detail showed writing in progress, research agents `HermesResearcher`, `researcher-co`, and `researcher_agent` as result received, `writer-co` as `전송 확인 · 결과 대기`, verification as `검증 미실행`, and an explicit read-only limitation that final artifact binding is unavailable.

### Interaction and safety

- Focused the representative primary action, then clicked it: detail title/body populated.
- Escape returned focus to the originating `작성 결과 도착 확인` action (`activeId` empty because it is a button; active text matched the originating action).
- Browser console messages: 0.
- Failed requests: 0.
- Non-GET requests observed in focused run: 0.
- Representative card itself exposed only the read-only primary action and `상세 보기`; no resend/gate/live-note/final-review write control was present on that card.
- **Global forbidden-control check: FAIL.** Other rendered cards expose `다시 전송` buttons. This is visible in the DOM button inventory and is a direct violation of the task's required absence of card resend controls, even though the representative card is clean.

## Acceptance matrix

| Criterion | Result | Evidence |
|---|---|---|
| 1440px responsive render | PASS | `desktop.png`; width/scrollWidth both 1440 |
| 1024px responsive render | PASS | `tablet.png`; width/scrollWidth both 1024 |
| 390px responsive render | PASS | `compact.png`; width/scrollWidth both 390 |
| No horizontal overflow | PASS | DOM measurements at all three widths |
| Legible information order | PASS | observed card order and representative copy above |
| Non-color status signifiers | PASS | text/icon stage and agent labels observed |
| Keyboard focus + Escape close/return focus | PASS | `interaction.png`; detail opened and focus returned to originating action |
| Exactly one read-only Next PM action | PASS (representative card) | one primary `작성 결과 도착 확인`, opens task detail only; no non-GET request |
| No card resend/gate/live-note/final-review write controls | **FAIL** | other cards expose `다시 전송`; representative card has none |
| Representative 3/3 research received | PASS | detail lists three research agents as `결과 도착` |
| Writer dispatch-confirmed/result pending | PASS | card/detail show `writer-co · 전송 확인 · 결과 대기` |
| Verification not run | PASS | card/detail show `검증 미실행` |

## Automated regression support

Command:

```bash
python3 -m unittest -v tests.test_dashboard_projection tests.test_dashboard_api_contracts tests.test_dashboard_static_contract test_operations_sync tests.test_ouroboros_seed_workflow
```

Result: **60 tests passed**.

Additional checks:

```bash
node --check operations_dashboard/app.js
python3 -m compileall -q operations_dashboard_projection.py operations_dashboard_server.py tests
git diff --check
```

All passed (exit 0).

## Retest recommendation

Remove or suppress `다시 전송` from all card surfaces (and verify no equivalent resend control appears in the card DOM), then rerun the isolated fixture matrix and focused representative interaction command. Keep write controls, if still needed by product scope, confined to the explicitly scoped task-detail surface and verify that the read-only card CTA remains the only primary action.

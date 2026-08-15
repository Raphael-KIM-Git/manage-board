# QA-PROGRESS-1D: Slice A 진행 가시화 browser/manual acceptance

## Verdict

**VERDICT: HOLD**

현재 working-tree candidate는 기존 Slice A task-card surface가 아니라 Operations Console/4사분면 surface를 기본 노출한다. 따라서 1440/1024/390px responsive·읽기 전용·focus/Escape 동작은 실행 확인했지만, 대표 fixture `T-20260729-001`의 진행 문구(리서치 3/3 도착, writer 대기, 검증 미실행)를 사용자에게 보이는 카드/상세에서 확인할 수 없어 Slice A 사용자 수용 조건을 최종 PASS할 수 없다.

## Scope and safety

- Source: `/home/raphael/myproject` (working-tree candidate; no commit/push/deploy)
- Browser target: `http://127.0.0.1:18766/`
- Data source: isolated copy `/tmp/qa-progress-current2/operations`, made from repository operations data; writer/verification files for `T-20260729-001` removed only in the temporary fixture. Canonical operational data was not changed.
- Browser: `/home/raphael/.local/bin/playwright-chromium-userlocal`, Playwright via `uv run --with playwright python3`
- Read-only safety: captured request methods contained no non-GET requests.

## Commands and real output

```bash
curl -fsS http://127.0.0.1:18766/api/health
# {"ok": true, "host": "127.0.0.1", "port": 18766}

uv run --with playwright python3 /tmp/qa_current_console.py \
  > docs/qa/evidence-slice-a/current-console-matrix.json
# exit 0

python3 -m pytest -q
# 108 passed, 3 subtests passed in 1.30s

node --check operations_dashboard/app.js
# exit 0
python3 -m compileall -q operations_dashboard_projection.py operations_dashboard_server.py tests
# exit 0
git diff --check
# exit 0
```

The repository scripts `qa_slice_a_browser.py` and `qa_slice_a_interaction.py` were also attempted against the candidate. They are not compatible with the current visible console surface: `.task-card` is rendered only inside the `aria-hidden="true"` legacy container, so the matrix timed out waiting for a visible representative card. The interaction script recorded `cards=0` and could not locate `삼성펀드`.

## Browser matrix

| Viewport | URL/data | innerWidth | scrollWidth | Visible task cards | Console/page errors | Non-GET |
|---|---|---:|---:|---:|---|---|
| 1440×1000 | `http://127.0.0.1:18766/`, isolated fixture | 1440 | 1440 | 0 | none observed | 0 |
| 1024×1000 | same | 1024 | 1024 | 0 | none observed | 0 |
| 390×844 | same | 390 | 390 | 0 | none observed | 0 |

Visible surface text included `OPERATIONS CONSOLE`, `PM CONVERSATION`, `AGENTS`, `PROJECTS`, `MISSION CONTROL`, `전송 확인`, `결과 7`, `검토 21`, `원시 근거와 귀속을 확인할 수 없습니다`, and `업무 상세`. It did **not** include `삼성펀드` or the required representative progress strings.

## Interaction result

The first enabled visible `업무 상세` button was focused and activated at compact viewport:

- Focus before activation: `업무 상세`
- Detail/dialog surface opened; no network write occurred.
- Escape returned focus to `업무 상세`.
- Request methods: `non_get=[]`.
- Limitation: the first enabled action was an agent/console detail action, not the representative `T-20260729-001` task detail, because that task is not exposed as a visible task-card in the current console surface.

## Acceptance matrix

| Criterion | Result | Evidence / limitation |
|---|---|---|
| 1440px render | PASS | `current-console-desktop.png`; 1440/1440 |
| 1024px render | PASS | `current-console-tablet.png`; 1024/1024 |
| 390px render | PASS | `current-console-compact.png`; 390/390 |
| No horizontal overflow | PASS | `scrollWidth == innerWidth` at all three widths |
| State signifiers beyond color | PASS (current console) | Text labels `전송 확인`, `준비됨`, `알 수 없음`, `DECISION`, `UNKNOWN` visible |
| Keyboard focus + Escape return-focus | PASS (generic detail) | Focus returned to originating `업무 상세`; no write |
| Task-detail-only read-only Next PM action | HOLD | Representative task card/action absent from visible surface; generic console detail verified only |
| No resend/gate/live-note/final-review write controls | PASS for visible surface | Visible action inventory contained `업무 상세`, `결과 보기`, `상세 근거`, layout controls; no forbidden write control; non-GET=0 |
| Representative `T-20260729-001` progress copy | **HOLD** | Visible DOM did not contain `삼성펀드`, `리서치 3/3`, writer waiting, or verification-not-run copy |
| Representative 3/3 research received | HOLD | Not visible in current console surface |
| Writer dispatch-confirmed/result pending | HOLD | Not visible in current console surface |
| Verification not run | HOLD | Not visible for representative task |

## Evidence artifacts

- `docs/qa/evidence-slice-a/current-console-matrix.json`
- `docs/qa/evidence-slice-a/console-desktop.png`
- `docs/qa/evidence-slice-a/console-tablet.png`
- `docs/qa/evidence-slice-a/console-compact.png`
- `docs/qa/evidence-slice-a/current-browser-matrix.json` (empty because legacy script timed out before JSON emission)
- `docs/qa/evidence-slice-a/current-interaction.json` (legacy script: visible card not found; console/page errors from incompatible surface)

## Correction / retest scope

1. Decide whether Slice A acceptance targets the legacy progress task-card surface or the new Operations Console surface.
2. If Slice A remains in scope, expose `T-20260729-001` as a visible read-only task detail/card in the candidate and preserve the required progress copy.
3. Update the browser runner to target the active surface rather than hidden `#legacyConsoleData`, then rerun all three viewports and representative task detail/Escape checks.

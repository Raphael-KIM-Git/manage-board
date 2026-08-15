VERDICT: FAIL

범위
- 대상: /home/raphael/myproject shared dirty-tree candidate, HEAD 26b3fa4, PRD section 10 QA-01~QA-24.
- 실행일: 2026-08-10.
- 브라우저 도구: Chromium/Firefox/WebKit 모두 실행 시도했으나 브라우저 도구 자체가 `utf-8 codec can't decode byte 0xc0 in position 49`로 example.com에서도 실패. 따라서 브라우저 acceptance를 통과로 추정하지 않음.

핵심 release blocker
1. P0 (upstream independent verification, current candidate): schema-v2 skipped-final fallback이 exact-bound verification status `failed` 또는 `inconclusive`를 positive evidence로 취급하고, 첫 verification record만 선택해 이후 negative record를 가린다. 재현 결과: failed/inconclusive exact-bound fixture가 `confirmed`; positive-first/negative-second도 `confirmed`. 위치: `operations_dashboard_projection.py:498-525`. 최소 수정: 명시적 positive verdict allowlist, 관련 exact-bound records aggregate, failed/inconclusive/negative evidence fail-closed.
2. P1 (upstream verification): legacy non-v2 skipped-final fallback이 arbitrary id/version으로 confirm할 수 있다. Rule B에 v2 primary+digest 증명을 요구하고 legacy implicit primary는 Rule A로 제한해야 한다.
3. 현재 실행한 static regression도 실패: `test_decision_first_section_order`가 `recentAudit` 안의 `<p class="section-kicker">Recent Audit</p>` 누락을 검출했다. 현재 DOM은 `<section id="recentAudit"><div id="recentFlow"></div></section>`이다.
4. candidate isolation 문제: shared dirty tree는 manifest와 완전히 재현되지 않아 merge/release 승인 경계가 불명확하다.

QA matrix
- QA-01: NOT RUN — Chromium browser blocker. Static projection/unit 관련 경로는 실행했으나 browser 증거 없음.
- QA-02: FAIL — P0 skipped fallback false-positive가 upstream에서 재현됨.
- QA-03: NOT RUN — Chromium browser blocker; T-20260729-001 screenshot/DOM text 없음.
- QA-04: NOT RUN — Firefox browser blocker.
- QA-05: NOT RUN — WebKit browser blocker.
- QA-06: NOT RUN — computed z-index/hit-test screenshot 불가. Static named modal coordinator hook은 존재.
- QA-07: NOT RUN — keyboard interaction trace 불가. Static open/close hooks 존재.
- QA-08: NOT RUN — activeElement trace 불가. Static return-focus implementation 존재.
- QA-09: NOT RUN — Chromium keyboard trace 불가. Static `trapTopModal` 존재.
- QA-10: NOT RUN — backdrop interaction trace 불가.
- QA-11: NOT RUN — runtime body lock trace 불가. Static modal lock counter/class 존재.
- QA-12: NOT RUN — 390x844 screenshot 불가.
- QA-13: NOT RUN — 768x1024 screenshot 불가.
- QA-14: NOT RUN — 200% zoom screenshot 불가.
- QA-15: NOT RUN — NVDA/Chromium 실행 불가; 동등 reviewer verification 없음.
- QA-16: NOT RUN — prefers-reduced-motion browser 기록 불가; stylesheet에 해당 rule은 현재 없음.
- QA-17: PARTIAL — static inspection confirms iframe is created with `sandbox="allow-downloads"`, no script/form allowance; runtime console/network proof는 없음.
- QA-18: NOT RUN — deleted fixture browser error UI 확인 불가. Server missing-file smoke는 HTTP 404.
- QA-19: FAIL — 95 tests 실행, 1 failure (`test_decision_first_section_order`). 상세: `docs/qa/evidence-v11-2/full-unittest.txt`.
- QA-20: PARTIAL — viewer flow 전후 mutation을 수행하지 않았고 canonical operation directories read-only hash snapshot을 남김. Full before/after diff는 browser blocker 및 no executable flow로 미완료.
- QA-21: NOT RUN — refresh tick/focus runtime trace 불가.
- QA-22: PASS (static subset) — index.html id 59개 검사에서 duplicate id 0개. Runtime/axe는 미실행.
- QA-23: NOT RUN — overview artifact tile deep entry browser instrumentation 불가.
- QA-24: NOT RUN — verification entry browser screenshot 불가.

실행 증거
- `/home/raphael/myproject/docs/qa/evidence-v11-2/full-unittest.txt` — 95 tests, 1 failure.
- `/home/raphael/myproject/docs/qa/evidence-v11-2/focused-unittest.txt` — focused 65 tests, 1 failure.
- `/home/raphael/myproject/docs/qa/evidence-v11-2/compile.txt` — Python compile PASS.
- `/home/raphael/myproject/docs/qa/evidence-v11-2/node-check.txt` — app.js syntax PASS.
- `/home/raphael/myproject/docs/qa/evidence-v11-2/diff-check.txt` — git diff check PASS.
- `/home/raphael/myproject/docs/qa/evidence-v11-2/api-smoke.txt` — overview/tasks/results/verifications/digests/capabilities/dashboard-console HTTP 200; missing file HTTP 404.
- `/home/raphael/myproject/DASHBOARD-REVIEW-MANIFEST.json` 및 `.md` — candidate hash/provenance boundary.

정적 추가 관찰
- duplicate DOM id: 0.
- iframe sandbox: allow-downloads만 존재; allow-scripts/allow-forms 없음.
- `trapTopModal`, modal stack/coordinator, focus-return 함수는 존재.
- CSS에서 `prefers-reduced-motion` rule은 발견되지 않음.
- 현 `index.html`의 legacy hidden surface는 PRD가 요구하는 visible section label을 포함하지 않아 static contract failure가 발생함.

권고
- P0 correction 단일 slice를 먼저 적용하고, failed/inconclusive/negative verification을 절대 confirmed로 승격하지 않는 adversarial tests를 추가한다.
- `recentAudit` section kicker 누락을 수정한 뒤 full unittest를 재실행한다.
- immutable isolated candidate/worktree를 만든다.
- 브라우저 의존성/도구를 복구한 환경에서 Chromium QA-01~14,17~24, Firefox QA-04/08, WebKit QA-05/mobile, NVDA QA-15를 재실행하고 screenshots/DOM/focus/console evidence를 첨부한다.

# HANDOFF 2026-07-13 — PM 파이프라인 선택(프로세스 카탈로그) + 로드맵

작성: 맥북 Claude (Fable). 대상 독자: Hermes(PC Claude) + 다음 세션의 맥북 Claude.
목적: 오늘 배포된 "PM이 업무 주제에 따라 프로세스를 선택"하는 기능의 구조·검증 결과와, 앞으로 진행할 로드맵 공유.

## 0. 제품 방향 (Raphael 확정)

> 하나의 업무가 주어졌을 때 PM이 해당 주제에 따라 **적절한 업무 프로세스를 선택**해 진행하고 그에 맞는 결과를 가져온다.
> PM은 전체 업무 조율과 결과물 판단을 담당하고, 실제 업무는 각 에이전트가 수행한다. (참고 모델: paperclip.ing — 현재는 일부만 반영)

이 원칙이 모든 후속 작업의 판단 기준이다. **파이프라인을 새로 고정하는 방향의 수정은 지양**하고, PM 판단 지점(게이트)을 늘리거나 카탈로그를 확장하는 방향으로 갈 것.

## 1. 오늘 배포된 것 (2026-07-13)

### 1-1. PIPELINE_CATALOG — PM이 프로세스 형태를 선택
`operations_sync.py` 상단의 선언형 카탈로그가 단일 소스다. 진입 게이트(GATE0) 프롬프트의 선택지 설명도 여기서 자동 생성된다. **새 프로세스 형태를 추가할 때는 이 dict에만 항목을 추가하면 된다** (skip 단계 + 한국어 desc).

| pipeline | 흐름 | 용도 |
|---|---|---|
| `full` | 조사→작성→검증→최종본 | 제안서/보고서 등 격식 문서 |
| `write_verify` | (조사 생략 가능)→작성→검증 | 초안+검증으로 충분한 일반 문서 |
| `research_verify` | 조사→검증 | 조사 리포트 자체가 산출물 (현황 조사·요약·팩트 확인) |
| `research_only` | 조사만 | 저위험 빠른 내부 참고용 |

- 진입 게이트 응답 스키마에 `pipeline` 필드 추가. `decision`(proceed/skip_research/hold)과 직교 — skip_research일 때는 full/write_verify만 유효(코드에서 강제).
- `apply_pipeline_shape()`가 생략 단계를 `status='skipped', skipped=True`로 마킹하고 `task['pipeline_shape']` 기록.
- **GATE1.5** (sync_task_statuses): writing이 skipped면 research→verification 직결. `maybe_dispatch_verification`은 writing skipped 시 research 결과를 검증 대상으로 컨텍스트 구성("조사 리포트 자체를 검증할 것" 헤더).
- 완료 판정 일반화: **모든 단계가 completed|skipped → task completed** (4단계 all-completed 하드코딩 제거).

### 1-2. 대시보드
- 단계칩: skipped = "PM 판단 생략" + `–` 마커 + `.stage-skipped`(반투명).
- 카드 헤더: full이 아니면 프로세스 배지 표시 ("조사→검증", "작성→검증" 등, `.badge-pipe`).
- `build_task_view`(server)에 `pipeline_shape` 필드 추가 — **API 화이트리스트 방식이므로 브리프에 새 필드를 추가하면 여기도 함께 추가해야 UI에 보인다** (오늘 실제로 밟은 함정).
- favicon 404 콘솔 에러 수정 (index.html/detail.html 인라인 SVG).

### 1-3. 검증 증거 (전부 라이브 실측)
- T-20260713-001 (릴리스 요점 조사): GATE0 → `research_verify` 판정, writer/final 생략 → HermesResearcher 조사 → research 게이트 proceed(검증 보완 지시 동반) → verify-co 검증 → completed. finals/ 산출물 없음 확인.
- T-20260713-002 (소개 문단 정돈): GATE0 → `skip_research + write_verify` → writer-co 작성 → GATE2 proceed → verify-co 검증 → completed. 역시 finals/ 없음.
- 시뮬레이션: 제안서형 → full+워커3, 조사형 → research_verify+워커2 (판단 사유 타당).
- UI: 배지·생략칩 렌더 확인, 콘솔 에러 0.

### 1-4. 백업·기준선
- 백업: `*.bak.pre-shape`(형태 1차), `*.bak.pre-catalog`(카탈로그+배지).
- 맥북 Claude가 md5 기준선을 메모리로 관리 중. **Hermes가 이 파일들을 수정하는 것은 문제없으나**, `hermes_entry_gate / apply_pipeline_shape / PIPELINE_CATALOG / GATE1.5 블록 / 완료판정 일반화 / build_task_view의 pipeline_shape` 심볼은 보존할 것.

## 2. 로드맵 (Raphael 승인, 우선순위 순)

### R1. 프로세스 카탈로그 확장 — ✅ 분석 유형까지 완료 (2026-07-13 오후)
**분석 업무 유형(문서 분석 + 데이터 분석)이 배포됐다:**
- **파일 첨부 → 분석 흐름**: 브리프 모달에 입력 파일 첨부(#taskFiles, 최대 10개·30MB) → `POST /api/upload-input?name=`(바이너리 본문) → `operations/inputs/`에 저장 → 브리프에 `input_files`(PC 경로)+`input_files_remote`(맥 경로) 기록 → dispatch 시 scp로 맥 `~/agent-hub/inputs/<base_task_id>/`에 전송(파생 task_id는 base id 디렉터리 공유, `base_task_id_str`).
- **analyst-co 워커** (맥 `~/.claude/agents/analyst-co.md`): 문서 분석(RFP·계약서 → 요구사항·리스크·견적 근거) + 데이터 분석(CSV/XLSX → python3 검증 수치만 보고). workers.json ssh 등록, worker_runner WORKER_SPECS 등록, build_prompt에 "입력 파일" 섹션 추가.
- **`analyze_verify` 카탈로그 항목**: 분석→검증 (writing/final 생략). 이 형태일 때 research 단계 라벨이 'Analysis'로 바뀜. 진입 게이트에 첨부 파일 목록 섹션 + "입력 파일 있는 분석 업무는 analyze_verify+analyst-co 기본" 기준 + 워커별 한 줄 설명 추가.
- **E2E 검증 (T-20260713-003, 실데이터)**: 매출 CSV 업로드 → GATE0 `analyze_verify+analyst-co` 판정 → 파일 scp → analyst-co 분석(수치 전부 python3 집계) → PM 게이트가 검산 후 proceed → verify-co가 독립 재검산("수치 오류 0건") → completed. UI 배지 "분석→검증"·Analysis 칩·파일 입력 확인.
- **함정 (중요)**: 헤드리스 `claude -p --output-format json`은 **마지막 메시지만** 결과로 수거한다. 에이전트가 리포트를 중간에 쓰고 "작성 완료했습니다"로 끝내면 산출물이 유실된다(실제 발생). 새 에이전트 정의에는 "마지막 응답=산출물 전문" 규칙을 반드시 넣을 것. 또 worker_runner는 결과 파일이 있으면 skip하고 브리프를 processed로 옮기므로, 재실행하려면 results의 md+json 삭제 + 브리프를 inbox로 복귀.
- 남은 것: 콘텐츠 기획 등 추가 유형(수요 생기면), PC 로컬 워커(HermesResearcher)용 입력 파일 프롬프트 지원(현재 미구현 — 분석은 맥 analyst-co 전담이라 당장 불필요), xlsx 분석용 openpyxl/pandas 맥 설치 여부 확인(현재 csv는 표준 라이브러리로 동작).

### R2. PM 중간 개입 (run 중 개입) — ✅ 완료 (2026-07-13 저녁, 맥북 Claude)
**`pm_live_notes` 채널로 구현·라이브 검증 완료:**
- **UI**: 진행 중(미완료) 카드마다 지시 입력줄("PM 지시 추가 — 다음 심사·단계부터 반영") + [지시 전달] 버튼. 대기 중 지시는 보라 칩으로 표시. 폴링 재렌더에도 입력값 유지(`liveNoteDrafts`).
- **API**: `POST /api/live-note {task_id, note}` → 브리프 `pm_live_notes`에 `{note, at, consumed}` 추가 (노트당 1000자, 최근 20개 캡, 완료/취소 태스크 거부).
- **반영 경로 3곳** (operations_sync.py):
  1. 게이트 프롬프트(진입+단계 모두)에 "PM 실시간 지시" 섹션 — 심사·feedback에 반영됨
  2. 다음 단계 디스패치 컨텍스트 최상단에 `[PM 실시간 지시 — 최우선 반영]` 주입, **주입 성공 시 consumed 처리** (헬퍼: pending_live_notes/live_notes_block/consume_live_notes)
  3. **hold 해제**: `gate_hold`/`entry_hold` 상태에서 게이트 판정 시각(`gate.at`)보다 새 지시가 오면 캐시를 지우고 재심사(`_fresh_note_after`) — 텍스트로 보류를 풀 수 있다
- **검증 증거**: ① 시뮬레이션 — entry_hold(LLM WIKI 용도불명) + "회사 노션 위키 신입사원용" 지시 → 재심사 → proceed+write_verify, 사유에 지시 방향 반영. ② 라이브(T-20260713-004) — research 진행 중 "출처 URL 접근성 표 + 국내 동향 한계 명시 확인" 지시 투입 → research 게이트가 국내 동향 미명시를 지적, verification 지시서 최상단에 지시 주입·consumed 처리, **verify-co 리포트에 실제 '출처 URL 접근성 표' 생성** → completed. ③ UI 경로 — 카드 입력→전달 버튼→브리프 저장 확인, 콘솔 에러 0.
- 한계(설계 의도): 이미 실행 중인 워커(1회성 headless)에게는 전달 불가 — 다음 심사/단계부터 반영. 백업 `*.bak.pre-livenote`.

### R3. 완료 후 PM 총평 (마감 게이트) — ✅ 완료 (2026-07-13, 맥북 Claude가 진행)
> Raphael이 처음엔 Hermes에게 배정했으나 이후 맥북 Claude가 직접 진행하도록 지시 변경. **Hermes는 이 항목 중복 구현하지 말 것.**

**`pm_final_review` 마감 게이트 구현·검증 완료:**
- 파이프라인의 모든 단계가 completed|skipped가 되는 순간(예전엔 곧장 completed), `_apply_final_review`가 HermesPM에게 **사용자 원 발화(pm_conversation) 대비 최종 산출물**을 심사시킨다. 결과 `task['pm_final_review']={verdict, comment, gaps, at}`.
  - verdict **meets/partial → completed** (총평·보완점을 기록한 채 완료)
  - verdict **not_meets → needs_pm_review** (완료 막고 사용자에게 승인/재작업 요청)
- **산출물 자동 선택**: `deliverable_stage_id`가 검증 제외, 완료·비생략 우선순위 final_write>writing>research로 최종 산출물 단계를 고름 → 모든 파이프라인 형태에서 올바른 결과물 심사.
- **override**: `POST /api/final-review {task_id, action}` — `accept`(강제 완료) / `rework`(`_reopen_deliverable`: 산출물 단계 queued·이후 완료단계 planned로 재개 + pm_final_review 삭제 + 총평 gaps를 pm_live_notes 재작업 지시로 주입 → 상태머신이 재디스패치, 재완료 시 총평 재실행).
- **UI**: 카드에 `PM 총평: 충족/대체로 충족/미충족` 배지+코멘트+보완점(.final-review 색상별). not_meets면 [이대로 승인]/[재작업] 버튼(finalReviewOverride).
- **패턴 준수**: 멱등(pm_final_review 존재 시 LLM 재호출 안 함, `_apply_final_review`가 (action, mutated) 반환해 held 태스크 재저장도 방지), pending fail-safe, 네이티브 claude, build_task_view 화이트리스트에 pm_final_review 추가.
- **검증**: ① 단위 — 정상 산출물→partial, 엉뚱한 산출물(개념설명 vs 매출요청)→not_meets 정확 판별, 멱등(complete/False·hold/False), accept→complete, rework→research 재개+gaps 주입 PASS. ② 통합 — 완료 실태스크(T-20260713-002) 실산출물로 sync→partial 총평 후 completed, API 노출 확인. ③ UI — not_meets 박스+버튼 렌더, [이대로 승인] 클릭→/api/final-review→sync→completed 전 루프, 콘솔 에러 0.
- 백업 `*.bak.pre-finalreview`(sync/server/app.js/styles.css).

### R4. 소소한 개선 (아무나, 짬 날 때)
- 진행 중 카드에 진행바/경과시간.
- 수동 "다시 전송"(/api/dispatch) 경로에도 dispatched_workers 기록 (스팟라이트 정확도).
- stale rate_limited 배지 시간필터 (sync_remote_worker_status 로그 250줄 재감지 문제).

## 3. 협업 규칙 리마인드
- 같은 파일 동시 수정 가능성 있음 → 수정 전 `.bak.pre-<주제>` 백업, 수정 후 py_compile.
- 게이트/카탈로그 심볼 보존 (1-4 참조). 크론이 실행하는 것은 `myproject/operations_sync.py` 풀버전이며 `.hermes/scripts/operations_sync.py`는 runpy 래퍼(수정 금지).
- claude 호출은 반드시 네이티브 `/home/raphael/.local/bin/claude`.
- 서버(server.py) 수정 시에만 재시작 필요. 프론트 3파일은 매 요청 read.

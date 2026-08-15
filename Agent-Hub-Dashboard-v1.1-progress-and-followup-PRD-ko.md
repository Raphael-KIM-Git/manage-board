# Agent Hub Dashboard v1.1 — 진행 가시화 및 추가 작업 요청 PRD

- 문서 상태: 개발·검증 handoff용
- 제품 범위: Agent Hub Dashboard-only v1.1
- 기준 저장소: `/home/raphael/myproject`
- 대표 사례: `T-20260729-001`
- 선행 기준: `Agent-Hub-Dashboard-progress-visibility-PRD-ko.md`, 승인 Slice A commit `26b3fa4`
- 핵심 원칙: **결과 도착, stage 전이, 검증 완료, PM 최종 검토, 추가 작업 요청을 서로 독립된 사실로 표시한다.**

## 기획 요약

v1.1은 사용자가 첫 화면에서 실제 진행 위치와 근거의 신선도를 빠르게 판단하고, task detail에서만 후속 작업 의도를 안전하게 제출하도록 한다. raw task·stage·dispatch·result envelope·verification·PM review·sync/watchdog snapshot을 canonical evidence로 유지하며, Dashboard projection은 이를 보수적으로 읽어 설명한다.

추가 작업 요청은 실행 명령이나 승인이 아니다. 제출 시 immutable한 사용자 의도 레코드가 만들어지고 `PM 재평가 대기`가 된다. PM이 별도 판단한 뒤에만 기존 task의 live note 또는 새 derived task에 연결할 수 있으며, 기존 stage·승인·완료·dispatch 상태는 요청 제출만으로 절대 바뀌지 않는다.

권고 구현 순서는 다음과 같다.

1. **Slice 0 — 배포 기준선 고정:** 승인된 `26b3fa4`와 현재 미검증 sync/research-policy/watchdog 변경을 분리한다.
2. **Slice 1 — 상태·근거·동기화 가시화:** overview/card/detail에 raw task, stage, 결과, 검증, PM review, sync/watchdog evidence를 서로 다른 축으로 표시한다.
3. **Slice 2 — 추가 작업 요청 intake:** task detail에만 요청 composer와 감사 가능한 요청 이력을 추가한다. 제출은 `pending_pm_review`까지만 수행한다.
4. **Slice 3 — PM 연결:** 명시적 PM 판단으로만 요청을 live note 또는 derived task에 연결한다. 자동 실행·자동 승인·기존 task 상태 변경은 금지한다.

---

## 1. 문제 / 목표 / 비목표

### 1.1 문제

현재 Dashboard는 승인된 Slice A를 통해 stage·agent·artifact 진행을 더 잘 보여주지만, 다음 오판 가능성이 남아 있다.

- raw task가 `completed`여도 결과 파일 도착, 각 stage 완료, verification 완료, PM final review가 각각 언제 어떤 근거로 성립했는지 한눈에 분리되지 않는다.
- result envelope가 먼저 도착했지만 sync가 parent stage를 아직 전이하지 않은 순간에는 “결과 도착”과 “stage 진행 중”이 동시에 참이다. 이를 하나의 상태로 합치면 결과를 숨기거나 stage 완료를 과장한다.
- sync/watchdog snapshot은 관찰 시각과 source 범위가 다르다. 오래된 watchdog snapshot을 현재 task 상태처럼 보여주면 이미 완료된 task를 active로 오표시할 수 있다.
- sync 성공은 모든 task가 최신 상태라는 뜻이 아니다. 마지막 sync가 성공했어도 특정 task에 대한 accepted/rejected transition evidence가 없을 수 있다.
- 사용자는 진행 중인 업무를 보며 보완 요청을 남기고 싶지만, 카드에 write control을 넣으면 승인된 read-only Slice A 원칙을 깨고 우발적 실행 위험을 높인다.
- 기존 live note는 비결정 맥락이지만, 일반 사용자는 이를 실행 지시나 승인으로 오해할 수 있다. 추가 작업 요청에는 별도의 version·request id·상태·연결 결과가 필요하다.
- 요청 제출과 derived task 생성 사이의 PM 판단을 생략하면 범위 확장, 담당자 오배정, 검증 누락, 기존 완료 상태의 무단 변경이 발생할 수 있다.

### 1.2 목표

1. 첫 화면에서 10초 안에 raw task 상태, 현재/직전 stage, agent별 결과 상태, 산출물·검증 상태, 근거 신선도, 다음 조치를 식별하게 한다.
2. 결과 파일 도착, stage 완료, verification 완료, PM final review를 독립 축으로 표시한다.
3. sync/watchdog의 마지막 성공·오류·관찰 시각·상태 전이 근거·source limitation을 raw evidence로 보여준다.
4. task detail에서만 사용자가 추가 작업 또는 보완 요청을 제출하게 한다.
5. 요청을 versioned·traceable 사용자 의도로 기록하고 기존 task/stage/approval/completion을 변경하지 않는다.
6. PM 재평가 후에만 요청을 live note 또는 derived task에 연결하며, 권한·범위·담당자·검증 요구를 명시한다.
7. 승인 Slice A와 미검증 runtime/sync/policy 변경을 분리 배포하고 독립 rollback할 수 있게 한다.

### 1.3 성공 지표

- 대표 상태 fixture에서 결과 도착과 stage 전이를 서로 잘못 대체하는 오탐 0건.
- verification envelope 도착과 verification stage 완료, PM final review를 혼동하는 오탐 0건.
- 오래된 watchdog/sync snapshot을 현재 상태로 표시하는 오탐 0건.
- 카드에 write control이 노출되는 회귀 0건.
- 요청 제출 100%가 `request_id`, `version`, actor, submitted_at, parent task, requested scope를 가진다.
- 요청 제출로 기존 task/stage/gate/final-review/dispatch 필드가 바뀌는 경우 0건.
- 중복 submit/idempotency retry로 동일 요청이 둘 이상 생성되는 경우 0건.
- accepted 요청 100%가 live note 또는 derived task의 식별자와 연결되고 PM decision evidence를 가진다.
- 키보드·모바일 viewport에서 요청 작성·검토·오류 복구가 가능하다.

### 1.4 비목표

- Dashboard 카드의 재전송·승인·gate override·live-note·추가 작업 버튼
- Discord를 공식 운영 제어 또는 승인 채널로 사용
- 요청 제출 즉시 agent 실행, dispatch, 승인, 완료, gate 전이
- 요청 free text 또는 버튼 클릭만으로 완료·승인·agent 성공을 추론
- 외부 사이트 변경, 실제 콘텐츠/UI 제작, production write
- 기존 raw task·dispatch·result persistence 대개편
- 과거 result의 attempt/stage correlation 자동 복구
- result 본문을 LLM으로 읽어 검증 상태 또는 요청 scope를 자동 확정
- 승인 Slice A와 현재 미검증 sync/research-policy/watchdog 변경을 한 번에 배포
- 완료 task의 원본 이력 재개방 또는 완료 상태 취소. 완료 후 요청은 새 derived task 후보로만 평가한다.

---

## 2. 실제 관찰과 상태 불일치 원인

### 2.1 대표 사례의 현재 canonical raw 사실

`operations/briefs/T-20260729-001-삼성펀드-홈페이지-운영-헬스체크-및-ui-ux-개선안-도출.json` 기준:

- task raw status: `completed`
- task `updated_at`: `2026-07-29T17:07:23`
- research: `completed`
- writing: `completed`, active derived task `T-20260729-001-writing-r1`
- verification: `completed`, derived task `T-20260729-001-verify`
- final_write: `skipped`
- writer 초안 envelope: `T-20260729-001-writing__writer-co.json`, `status=completed`
- writer 재제출 envelope: `T-20260729-001-writing-r1__writer-co.json`, `status=completed`
- verify-co envelope: `T-20260729-001-verify__verify-co.json`, `status=completed`
- verification 전용 디렉터리 `operations/verifications`에는 이 task 파일이 없다. 검증 근거는 result envelope에 있다.
- PM final review: `verdict=meets`, `at=2026-07-29T17:07:23`
- PM final review에는 현재 `artifact_id`/`artifact_version` binding이 없다. 따라서 “PM 검토 기록 도착”은 표시할 수 있으나 projection의 강한 `effective_final_approved`와 동일시해서는 안 된다.

현재 사용자용 안전한 요약은 다음과 같다.

> **업무 raw 완료 · 리서치/작성/검증 stage 완료 · 최종 작성 생략 · writer 및 verify-co 결과 envelope 도착 · PM 최종 검토 기록 있음(산출물 binding 확인 필요)**

### 2.2 이전 불일치 사례

이전 관찰 시점에는 writer completed envelope가 존재했지만 parent writing stage가 `in_progress`로 유지됐다. 두 사실은 충돌처럼 보이지만 서로 다른 처리 단계였다.

1. worker가 report와 result envelope를 결과 inbox에 기록
2. sync가 결과를 pull
3. sync가 envelope의 derived task id·worker·status·report 존재를 검증
4. sync가 parent stage를 `completed`로 전이
5. 다음 stage를 dispatch하거나 hold

3~4가 수행되기 전에는 다음 두 문구가 동시에 참이다.

- `writer-co 결과 도착`
- `writing stage raw 진행 중 · sync 전이 대기/확인 필요`

Dashboard는 결과를 숨기거나 stage를 임의 완료시키지 않고 두 축을 함께 보여줘야 한다.

### 2.3 불일치의 구조적 원인

| 원인 | 실제 의미 | 잘못된 표시 | 요구 표시 |
|---|---|---|---|
| 비동기 결과 수집 | envelope가 parent 전이보다 먼저 도착 | 결과가 없다고 숨김 또는 stage 자동 완료 | 결과 도착 + stage raw 상태 병기 |
| derived task id | `...-writing-r1` 결과가 parent task에 귀속됨 | prefix만으로 다른 attempt와 혼합 | active `derived_task_id`와 exact match |
| report/envelope 분리 | `.md`, `.json`, `.html`이 한 실행 묶음 | 결과 3개 완료 | result bundle 1개, 파일 3개 |
| verification 저장 위치 차이 | 검증 envelope가 results에 존재할 수 있음 | verifications 폴더가 비어 검증 미실행 | stage/derived id/worker envelope 우선, 전용 폴더는 보조 |
| PM review binding 부재 | review 기록은 있으나 정본 artifact 연결이 약함 | 최종 승인 확정 | PM 검토 기록 있음 + binding 확인 필요 |
| snapshot 관찰 주기 차이 | watchdog와 sync의 observed_at이 다름 | 오래된 snapshot을 현재 상태로 표시 | 관찰 시각·age·source limitation 표시 |
| sync run 전역 성공 | pull 성공이 특정 task 전이 증거는 아님 | 모든 상태 최신 | global run outcome과 task transition evidence 분리 |

### 2.4 현재 sync/watchdog raw evidence의 제한

`operations/sync/latest.json`:

- `observed_at=2026-07-29T20:03:06`
- `pull_exit=0`, `last_result=success`
- `status_updates`는 다른 task `T-20260710-910`의 rejected evidence만 포함
- `T-20260729-001`의 마지막 accepted transition은 현재 snapshot만으로 복구할 수 없음

`operations/watchdog/latest.json`:

- `observed_at=2026-07-29T06:56:33.784357+00:00`
- `T-20260729-001`을 `dispatched / writing` active task로 기록
- canonical raw task의 `updated_at=2026-07-29T17:07:23`, status `completed`보다 오래된 관찰

따라서 Dashboard는 watchdog을 현재 task 상태의 authority로 쓰지 않는다. 다음처럼 표시한다.

> `Watchdog 마지막 관찰: 2026-07-29T06:56:33Z · 당시 writing/dispatched · 현재 raw task보다 오래된 snapshot`

### 2.5 사실과 가정 구분

**확인된 사실**

- 승인 Slice A commit은 `26b3fa4`이며 main/origin main에 있다.
- 현재 working tree에는 `operations_sync.py`, `operations_dashboard_server.py`, `test_operations_sync.py` 수정과 policy/sync/watchdog 관련 untracked 파일이 있다.
- 현재 task raw는 completed이며 writer/verify result envelope와 PM review가 있다.
- 기존 카드 CTA는 task detail만 열도록 구현됐고 mutation 지향 label을 차단한다.

**가정**

- 현재 미검증 working-tree 변경은 별도 개발/review 흐름에서 검증될 예정이며 이 PRD 구현과 직접 합치지 않는다.
- 후속 요청 identity는 기존 task id와 충돌하지 않는 opaque id를 생성할 수 있다.
- Dashboard 인증 actor를 즉시 강하게 식별할 수 없다면 v1.1은 configured local user `Raphael`과 request origin을 함께 기록하되, 공유 배포 전 인증을 선행한다.

---

## 3. 상태·근거·동기화 모델

### 3.1 독립 상태 축

Dashboard는 하나의 “진행 상태”로 축약하지 않고 최소 7개 축을 유지한다.

1. **Task raw:** queued/in_progress/completed 등 원본 상태
2. **Stage raw:** 각 stage의 planned/in_progress/completed/skipped/blocked/unknown
3. **Agent delivery/result:** not_dispatched/dispatch_confirmed/result_received/failed_or_blocked/unknown
4. **Artifact:** none/partial_received/reviewable/ambiguous
5. **Verification:** not_run/evidence_received_unbound/verified/failed/unknown
6. **PM review:** not_run/review_recorded_unbound/review_recorded_bound/hold/unknown
7. **Sync health:** never_observed/success/error/stale/unknown + task transition evidence

강한 상태는 약한 상태를 덮어쓰지 않는다. 예를 들어 PM review가 있어도 verification failed를 숨기지 않는다.

### 3.2 상태 근거 우선순위

1. task/stage raw JSON
2. exact derived task id + expected worker + completed status + existing report로 검증된 result envelope
3. artifact-bound verification envelope/verdict
4. artifact-bound PM final review/override
5. dispatch raw record
6. sync task transition evidence
7. sync/watchdog global snapshot
8. 파일명 추정 또는 자유 텍스트는 긍정 상태의 근거로 사용하지 않음

동일 축에서 근거가 충돌하면 `unknown/ambiguous`로 내리고 raw evidence를 함께 표시한다.

### 3.3 결과와 stage 전이 규칙

- result envelope 도착은 `agent.result_received`만 증명한다.
- stage raw `completed`만 stage 완료를 증명한다.
- envelope가 있고 stage가 active면 `결과 도착 · stage 전이 대기/불일치 확인`을 표시한다.
- stage completed이나 expected result 일부가 없으면 `stage raw 완료 · 결과 근거 일부 확인 불가`를 표시한다.
- derived `-r1` 결과는 active `derived_task_id`와 일치할 때 최신 active attempt로 본다. 이전 attempt는 history로 남긴다.
- `completion_policy=any`는 stage 완료 정책일 뿐 모든 agent가 결과를 냈다는 뜻이 아니다.

### 3.4 검증과 PM review 규칙

- verify worker의 completed envelope + report는 `검증 결과 도착`을 증명한다.
- verification stage raw completed는 `검증 stage 완료`를 증명한다.
- 대상 artifact/version binding과 verdict가 있어야 `verified`를 표시한다.
- PM final review가 존재하면 `PM 검토 기록 있음`을 표시한다.
- PM review에 artifact binding이 없으면 `최종 승인 확정` 대신 `대상 산출물 연결 확인 필요`를 표시한다.
- `final_write=skipped`는 PM review 또는 verification을 의미하지 않는다.

### 3.5 sync/watchdog 상태 모델

| 상태 | 판정 | 사용자 문구 |
|---|---|---|
| `never_observed` | snapshot 없음 | 동기화 관찰 기록 없음 |
| `success` | `last_result=success`, 허용 시간 내 | 마지막 sync 성공 |
| `error` | pull/runner error | 마지막 sync 오류 |
| `stale` | snapshot이 canonical task updated_at보다 오래됐거나 freshness threshold 초과 | 오래된 관찰 · 현재 상태 근거로 사용 불가 |
| `unknown` | malformed/missing key | 동기화 상태 확인 불가 |

freshness threshold는 UI에서 임의 확정하지 않는다. 서버 설정값 `sync_freshness_seconds`와 `watchdog_freshness_seconds`를 projection에 함께 제공한다. task별 `transition_evidence`가 없으면 global success를 task 전이 성공으로 확장하지 않는다.

### 3.6 요청 상태 모델

| 요청 상태 | 의미 | 누가 만들 수 있는가 | 기존 task 영향 |
|---|---|---|---|
| `draft` | 브라우저 내 미제출 초안 | 사용자 | 없음, 서버 미기록 |
| `pending_pm_review` | 제출된 사용자 의도 | 권한 있는 Dashboard 사용자 | 없음 |
| `needs_clarification` | PM이 범위 보완 요청 | PM | 없음 |
| `accepted_as_live_note` | 현재 active stage의 다음 심사 맥락으로 연결 | PM | live note 추가만; stage 자동 전이 없음 |
| `accepted_as_derived_task` | 별도 후속 task 생성·연결 | PM | parent 원본 상태 불변 |
| `rejected` | 범위/안전/중복 사유로 미수행 | PM | 없음 |
| `superseded` | 새 version이 이전 요청을 대체 | 시스템/PM | 없음 |
| `cancelled_by_user` | PM 판단 전 사용자 취소 | 최초 actor | 없음 |

금지 전이는 다음과 같다.

- `pending_pm_review → stage completed`
- `pending_pm_review → approved`
- `pending_pm_review → dispatched`
- `accepted_as_live_note → agent success`
- 요청 존재만으로 parent task를 reopen 또는 in_progress로 변경

### 3.7 근거 시각 표시

모든 상태 블록은 가능할 때 다음 시각을 분리한다.

- source event time: raw `finished_at`, `gate.at`, `pm_final_review.at`
- file observed/modified time
- sync observed time
- Dashboard rendered time은 근거 시각으로 사용하지 않음

시간대 정보가 없는 raw timestamp는 원문을 보존하고 `timezone 확인 필요`를 표시한다.

---

## 4. 화면 요구사항

### 4.1 Overview / Mission Control

추가 summary 항목:

- 진행 중 task 수
- 결과 도착 후 stage 전이 대기/불일치 수
- 검증 근거 도착·binding 미확인 수
- PM 검토 대기 수
- 추가 작업 요청 `pending_pm_review` 수
- sync 오류/stale 여부
- watchdog 오류/stale 여부

상단 운영 상태는 다음 형식으로 표시한다.

> `Sync: 성공 · 마지막 관찰 20:03:06 · task 전이 근거 0건`  
> `Watchdog: 오래된 관찰 · 06:56:33Z · 현재 raw보다 이전`

전역 sync 성공 배지는 개별 task 완료 배지와 색·위치를 분리한다.

### 4.2 Task card

카드 고정 정보 순서:

1. Outcome — 제목·목표
2. Task raw — 예: `raw task: completed`
3. 현재 위치 — `필수 stage 3개 완료 · 최종 작성 생략`
4. 직전 전이 — `검증 stage 완료`
5. Agent 결과 — `writer-co 결과 도착 · verify-co 검증 결과 도착`
6. Artifact / Verification / PM review — 세 줄로 분리
7. 근거 시각 — 가장 최근 canonical event와 source label
8. 다음 조치 — detail을 여는 읽기 전용 단일 CTA

카드 금지 요소:

- 추가 작업 요청 입력/버튼
- 다시 전송
- 승인/재작업/override
- gate controls
- live note 입력
- 요청 승인 또는 derived task 생성

카드는 click 자체가 mutation을 만들지 않는다.

### 4.3 카드 대표 문구 — 현재 `T-20260729-001`

권장 copy:

- Task raw: `업무 완료`
- 단계: `리서치·작성·검증 완료 · 최종 작성 생략`
- Agent: `writer-co 재제출 결과 도착 · verify-co 검증 결과 도착`
- 산출물: `writer 초안/HTML 결과 묶음 있음`
- 검증: `검증 결과 도착 · 대상 산출물 binding 확인 필요`
- PM review: `meets 기록 있음 · 최종 산출물 binding 확인 필요`
- 근거 시각: `PM review 2026-07-29T17:07:23`
- 동기화 한계: `watchdog snapshot은 현재 raw보다 오래됨`
- CTA: `업무 상세 보기`

금지 copy:

- `최종 승인 완료` — binding 없는 review만 근거일 때
- `검증 완전 통과` — verify envelope summary가 `major_revision`인데 구조화 verdict/binding이 없을 때
- `결과 15개 완료` — sidecar/HTML/attempt를 독립 실행으로 셀 때
- `현재 writing 진행 중` — 오래된 watchdog snapshot만 근거일 때
- `추가 작업 실행` — request 제출 단계에서

### 4.4 Task detail 정보 구조

고정 순서:

1. Outcome / raw task
2. Progress overview
3. Stage timeline
4. Agent execution / attempts
5. Artifact bundles
6. Verification
7. PM review
8. Sync / Watchdog evidence
9. Authority / Audit
10. Additional work requests
11. Live note context — 기존 정책에 따라 active task에서만

#### Stage timeline

각 stage 행에 다음을 표시한다.

- normalized/raw state
- depends_on
- active derived task id
- expected/dispatched/result-received agent 수
- stage event time
- result-to-stage mismatch warning
- skipped reason이 없으면 `생략 사유 확인 불가`

#### Agent execution / attempts

- worker
- stage
- derived task / attempt id
- dispatch state/time
- envelope status/finished_at
- report file
- active attempt 여부
- 이전 attempt는 접힌 history
- correlation limitation

#### Verification

세 사실을 나란히 표시한다.

- verification stage: completed/...
- verification result: envelope/report 도착 여부
- verification binding/verdict: verified/unbound/failed/unknown

#### PM review

- raw verdict/comment/gaps/time
- artifact binding 존재 여부
- effective approval projection
- verification과 별개라는 안내

#### Sync / Watchdog evidence

- source name
- observed_at
- last_result / pull_exit
- task-specific accepted/rejected transitions
- snapshot age/freshness
- canonical task updated_at과 비교
- source limitation
- raw JSON detail disclosure

### 4.5 빈값·충돌·오류 UX

- sync snapshot 없음: `동기화 관찰 기록 없음`
- malformed snapshot: `동기화 근거를 읽을 수 없음`
- snapshot이 task보다 오래됨: `오래된 관찰 · 현재 상태 근거로 사용 안 함`
- envelope completed + report 없음: `결과 envelope 거부 · report 없음`
- verify result 있음 + stage in_progress: 두 상태 병기
- PM review 있음 + binding 없음: `검토 기록 있음 · 대상 연결 확인 필요`
- duplicate follow-up submit: 기존 request id를 반환하고 `이미 제출됨`
- request 저장 실패: draft 유지, 기존 task 무변경, 재시도 안내

---

## 5. 추가 작업 요청 UX와 권한 / 감사 모델

### 5.1 진입점

- task detail의 `Additional work requests` 섹션에서만 `추가 작업 요청` 버튼을 제공한다.
- active task와 completed task 모두 요청할 수 있으나 권장 연결 방식이 다르다.
  - active: PM이 현재 stage의 live note 또는 별도 derived task로 평가
  - completed: 원본을 reopen하지 않고 derived task만 허용
- 카드·overview·Mission Control에서는 pending 건수만 읽기 전용으로 표시한다.

### 5.2 작성 흐름

1. 사용자가 `추가 작업 요청` 선택
2. 안내문 확인: `요청은 즉시 실행·승인되지 않으며 PM 재평가 후 연결됩니다.`
3. 필수 입력
   - 요청 제목
   - 원하는 결과 / 완료 조건
   - 요청 범위: 현재 결과 보완 / 추가 조사 / 수정 / 검증 / 새 산출물 / 기타
   - 대상: task 전체 / stage / artifact bundle
   - 우선순위: low/medium/high. emergency는 v1.1 미지원
4. 선택 입력
   - 배경/이유
   - 제약
   - 선호 담당 역할
   - 필요한 검증
5. 미리보기에서 다음을 확인
   - 기존 task 상태는 변하지 않음
   - PM 재평가 대기
   - 요청된 scope/owner/verification은 확정 전 제안값
6. submit
7. 성공 시 `요청 접수 · PM 재평가 대기`와 request id/version 표시

### 5.3 입력 제한

- title 120자, desired outcome 2,000자, context/constraints 각 2,000자
- HTML/스크립트는 text로 escape
- secret/token/개인정보 입력 금지 안내
- 빈 요청, whitespace-only, parent task 없음, 허용 밖 enum은 4xx
- 자유 텍스트에서 승인·완료·담당자·검증 성공을 추론하지 않음
- 파일 첨부는 v1.1 비목표. 기존 artifact를 id로 선택만 허용한다.

### 5.4 제출 후 화면

요청 timeline 행:

- request id / version
- submitted by / submitted at
- requested scope / desired outcome
- state
- PM decision 및 이유
- 연결 방식
- linked live note id 또는 derived task id
- required reviewer/verification
- supersedes/superseded_by

사용자 copy:

- `PM 재평가 대기`
- `현재 단계 메모로 연결됨 · 실행/승인 보장 아님`
- `후속 업무로 연결됨 · 원본 업무 상태 불변`
- `보완 필요`
- `수행하지 않음 · 사유 보기`

### 5.5 PM 재평가 규칙

PM은 다음 순서로 판단한다.

1. 요청 의도가 원 업무 목표와 관련 있는가?
2. 현재 active stage에서 안전하게 반영 가능한 맥락인가?
3. 기존 완료/승인/검증을 무효화해야 하는가? 그렇다면 원본 변경 대신 새 task가 필요한가?
4. 외부 write, production, 계정/개인정보, 비용, 법무 등 고위험 범위인가?
5. 담당 역할과 필요한 검증을 지정할 수 있는가?
6. 중복 요청인가?

연결 기준:

- **live note:** active task, 현재/다음 stage의 비결정 맥락, 원래 scope 안, 기존 완료 stage를 되돌릴 필요 없음
- **derived task:** completed task, scope 확장, 새 산출물, 별도 owner, 독립 검증 필요, 기존 완료/승인을 보존해야 함
- **needs clarification:** desired outcome/target/AC가 불명확
- **reject:** 위험, 중복, 권한 없음, 범위 외

### 5.6 권한 모델

| 행위 | 사용자 | PM | 시스템/sync | agent |
|---|---:|---:|---:|---:|
| 요청 draft/submit | 허용 | 허용 | 금지 | 금지 |
| 본인 pending 요청 취소 | 허용 | 허용 | 금지 | 금지 |
| clarification 요청 | 금지 | 허용 | 금지 | 금지 |
| live note 연결 | 금지 | 허용 | 기록만 | 금지 |
| derived task 생성/연결 | 금지 | 허용 | 식별자 생성·저장 | 금지 |
| 기존 stage/gate/final review 변경 | 요청 기능에서는 모두 금지 | 기존 별도 control에서만 | 기존 정책만 | 금지 |
| dispatch | 요청 기능에서는 금지 | 별도 기존 flow | 기존 flow | 금지 |

인증 actor를 신뢰할 수 없는 배포에서는 request submit 자체를 disable하고 `권한 확인 필요`를 표시한다.

### 5.7 감사 불변조건

- request record는 append-only event history를 가진다.
- 수정은 기존 레코드 overwrite가 아니라 `version+1`, `supersedes`로 기록한다.
- PM decision에는 actor, at, decision, reason, target kind/id, requested owner, required verification을 기록한다.
- derived task에는 `parent_task_id`와 `source_request_id/version`을 기록한다.
- live note에는 `source_request_id/version`을 기록한다.
- request 제출 전후 parent task JSON의 task/stage/gate/final review/dispatch hash-equivalent payload가 동일해야 한다.
- projection은 요청 raw를 읽기만 하며 상태를 추론·write하지 않는다.

---

## 6. API / projection / 원시 데이터 계약

### 6.1 설계 결정

요청은 기존 `/api/live-note`에 free text로 바로 저장하지 않는다. 그 방식은 version·PM decision·target link를 보장하지 못하고, 제출과 반영을 혼동시킨다.

권고는 제한된 **intent intake API**와 additive raw sidecar다. 이는 agent 실행·승인·stage 전이를 수행하는 운영 API 확장이 아니라, 사용자 의도를 안전하게 접수하는 단일 목적의 계약이다.

raw 위치 후보:

`operations/follow-up-requests/<parent-task-id>/<request-id>.json`

기존 task JSON을 요청 제출 때 수정하지 않는다. 새 persistence 대개편이 아니라 독립 additive sidecar이며 rollback 시 무시할 수 있다.

### 6.2 요청 raw schema v1

```json
{
  "schema_version": 1,
  "request_id": "FR-opaque-id",
  "version": 1,
  "parent_task_id": "T-20260729-001",
  "target": {
    "kind": "task|stage|artifact",
    "id": "T-20260729-001"
  },
  "request_type": "supplement|research|revision|verification|new_artifact|other",
  "title": "모바일 실기기 검증 추가",
  "desired_outcome": "390px 실기기/브라우저 검증 결과와 이슈 목록",
  "context": "기존 보고서의 미검증 항목 보완",
  "constraints": "GET-only, production 변경 금지",
  "priority_requested": "medium",
  "owner_role_requested": "reviewer",
  "verification_requested": ["browser_390px", "evidence_urls"],
  "state": "pending_pm_review",
  "submitted_by": {
    "actor_id": "Raphael",
    "auth_source": "dashboard-local"
  },
  "submitted_at": "ISO-8601",
  "idempotency_key": "opaque-client-key",
  "supersedes": null,
  "decision": null,
  "links": [],
  "events": [
    {
      "event": "submitted",
      "at": "ISO-8601",
      "actor_id": "Raphael",
      "from": null,
      "to": "pending_pm_review"
    }
  ]
}
```

서버가 생성하는 필드와 client 입력 필드를 분리한다. client는 request_id, version, state, actor, timestamps, decision, links를 지정할 수 없다.

### 6.3 요청 API

#### `POST /api/tasks/{task_id}/follow-up-requests`

요청 header:

- `Content-Type: application/json`
- `Idempotency-Key: <opaque>` 필수

성공: `201 Created`

```json
{
  "ok": true,
  "request": {
    "request_id": "FR-opaque-id",
    "version": 1,
    "state": "pending_pm_review"
  },
  "parent_task_changed": false
}
```

재시도 중복: 동일 payload/key면 `200`과 기존 request 반환. 동일 key·다른 payload면 `409`.

#### `GET /api/tasks/{task_id}/follow-up-requests`

해당 task의 요청 version과 상태 이력을 읽기 전용 반환한다.

#### PM decision API

Slice 3에서 별도 권한의 `POST /api/follow-up-requests/{request_id}/decisions`를 도입할 수 있다. 이 endpoint는 allowlisted decision만 받고, live note 또는 derived task 연결을 기존 canonical writer 함수에 위임한다. request submit endpoint와 route/권한/테스트를 분리한다.

### 6.4 PM decision payload

```json
{
  "request_version": 1,
  "decision": "accept_as_live_note|accept_as_derived_task|needs_clarification|reject",
  "reason": "원본 완료 상태를 보존하고 독립 QA가 필요함",
  "owner_role": "reviewer",
  "required_verification": ["browser_390px", "artifact_binding"],
  "derived_task_spec": {
    "title": "삼성펀드 모바일 실기기 검증",
    "objective": "기존 미검증 항목을 독립 검증"
  }
}
```

낙관적 동시성: 최신 `request_version`이 다르면 `409 stale version`.

### 6.5 progress/sync projection additive 계약

기존 `dashboard_projection.schema_version=1`을 유지한다. additive 필드 후보:

```json
{
  "dashboard_projection": {
    "schema_version": 1,
    "progress": {
      "schema_version": 2,
      "task_raw": {"state": "completed", "updated_at": "2026-07-29T17:07:23"},
      "current_stage": null,
      "last_completed_stage": "verification",
      "stages": [],
      "agents": [],
      "artifact_state": "reviewable",
      "verification": {
        "stage_state": "completed",
        "result_state": "evidence_received",
        "binding_state": "unbound"
      },
      "pm_review": {
        "state": "review_recorded_unbound",
        "verdict_raw": "meets",
        "at": "2026-07-29T17:07:23"
      },
      "latest_canonical_event_at": "2026-07-29T17:07:23",
      "data_quality": ["pm_review_artifact_binding_missing"]
    },
    "follow_up_summary": {
      "schema_version": 1,
      "pending_count": 0,
      "latest_request_at": null
    }
  }
}
```

overview additive 필드:

```json
{
  "operations_evidence": {
    "sync": {
      "state": "success",
      "observed_at": "2026-07-29T20:03:06",
      "freshness_seconds": 0,
      "task_transition_evidence": []
    },
    "watchdog": {
      "state": "stale",
      "observed_at": "2026-07-29T06:56:33.784357+00:00",
      "source_limitation": "snapshot_older_than_task_raw"
    }
  }
}
```

기존 working-tree의 top-level `sync_evidence`, `watchdog_evidence`는 미검증 후보이므로 즉시 contract로 확정하지 않는다. Slice 1 developer가 reviewer와 함께 raw passthrough와 normalized `operations_evidence` 중 하나를 선택하되, UI는 raw snapshot을 task authority로 사용하지 않는다.

### 6.6 canonical source 매핑

| 사용자 표시 | canonical source | fallback | 금지 추론 |
|---|---|---|---|
| task raw | brief JSON `status` | unknown | watchdog snapshot |
| current/last stage | `stages[].status` | unknown | result 도착 |
| agent result | exact result envelope + report | ambiguous | dispatch success |
| artifact bundle | result metadata/report binding | ambiguous | 파일 개수 |
| verification result | verify derived envelope | unavailable | verifications 폴더 존재만 |
| verified | bound verdict | unbound | worker completed |
| PM review | `pm_final_review` | not_run | verification 완료 |
| sync health | sync latest raw | never/unknown | task 완료 |
| watchdog health | watchdog latest raw | never/unknown | canonical task 상태 |
| follow-up request | request sidecar | none | live note text |
| derived task link | PM decision + new task raw | unlinked | request accepted 문구 |

### 6.7 보안·데이터 보호

- path traversal 차단: task/request id를 allowlist하고 server-side path 생성
- payload size 제한
- HTML escape, JSON schema validation
- CSRF/Origin 보호가 없는 shared deployment에서는 write UI disable
- request raw에 secret/token/민감정보를 넣지 않도록 안내 및 운영 로그 redaction
- actor/auth source를 기록하되 검증 불가능한 client-supplied actor를 신뢰하지 않음
- error response에 filesystem 절대경로나 raw payload 전체를 노출하지 않음

---

## 7. 구현 slice·순서·Acceptance Criteria

### Slice 0 — 승인 기준선과 미검증 변경 분리

**목적:** `26b3fa4` 배포와 현재 sync/research-policy/watchdog 변경을 섞지 않는다.

**파일/작업:**

- clean main/origin main의 `26b3fa4`를 release baseline으로 태깅/기록
- 현재 modified/untracked 파일은 별도 branch/worktree에서만 검증
- runtime 재기동 전 diff·테스트·운영 승인

**AC**

- [ ] 승인 Slice A 배포물에 현재 working-tree 미검증 파일이 포함되지 않는다.
- [ ] `git status`와 release artifact manifest가 기록된다.
- [ ] rollback은 코드와 runtime state를 구분한다.
- [ ] 현재 production/runtime를 계획 작업 때문에 재기동하지 않는다.

### Slice 1A — 상태 축 및 대표 completed 사례

**후보 파일:**

- `operations_dashboard_projection.py`
- `operations_dashboard_server.py`
- `operations_dashboard/app.js`
- `operations_dashboard/styles.css`
- `tests/test_dashboard_projection.py`
- `tests/test_dashboard_api_contracts.py`
- `tests/test_dashboard_static_contract.py`

**AC**

- [ ] raw task completed와 stage 3 completed/final skipped를 분리 표시한다.
- [ ] current stage가 없고 last completed stage가 verification으로 표시된다.
- [ ] writer original/revision attempt가 history와 active attempt로 구분된다.
- [ ] `.md/.json/.html`을 독립 실행 개수로 세지 않는다.
- [ ] verify result envelope와 verification stage 완료를 별도 표시한다.
- [ ] PM review `meets`와 artifact binding missing을 함께 표시한다.
- [ ] binding 없는 PM review를 final approved로 승격하지 않는다.
- [ ] 기존 Slice A 카드 CTA는 detail-opening read-only 동작만 유지한다.

### Slice 1B — sync/watchdog evidence

**후보 파일:**

- `operations_dashboard_server.py`
- `operations_dashboard_projection.py`
- `operations_dashboard/app.js`
- `operations_dashboard/styles.css`
- `operations_sync.py` 및 `operations_watchdog.py`는 별도 미검증 lane에서 raw producer 계약이 승인된 경우에만
- `tests/test_dashboard_api_contracts.py`
- `tests/test_dashboard_projection.py`
- `tests/test_operations_watchdog.py`
- `test_operations_sync.py`

**AC**

- [ ] sync success/error/never/unknown을 표시한다.
- [ ] observed_at과 source limitation을 표시한다.
- [ ] global sync success가 task transition success로 표시되지 않는다.
- [ ] task-specific accepted/rejected transition evidence를 구분한다.
- [ ] watchdog snapshot이 task raw보다 오래되면 stale로 표시한다.
- [ ] stale watchdog의 active task가 current task status를 덮어쓰지 않는다.
- [ ] malformed/missing snapshot에서 API/UI가 fail-safe로 동작한다.

### Slice 2 — Follow-up request intake

**후보 파일:**

- 신규 `operations_followup_requests.py` — schema validation, append/version, idempotency
- `operations_dashboard_server.py` — 좁은 GET/POST route
- `operations_dashboard/app.js`
- `operations_dashboard/styles.css`
- 필요 시 `operations_dashboard/index.html` — detail modal hook만
- 신규 `tests/test_operations_followup_requests.py`
- `tests/test_dashboard_api_contracts.py`
- `tests/test_dashboard_static_contract.py`

**AC**

- [ ] composer는 task detail에만 존재한다.
- [ ] 카드에 요청/write control이 없다.
- [ ] submit 전 즉시 실행/승인되지 않는다는 안내가 보인다.
- [ ] 성공 시 request id/version/state=`pending_pm_review`를 반환한다.
- [ ] raw request sidecar가 versioned/auditable하게 기록된다.
- [ ] 동일 idempotency key/payload 재시도는 중복 생성하지 않는다.
- [ ] 동일 key/다른 payload는 409다.
- [ ] parent task의 status/stages/gates/final review/dispatch가 변경되지 않는다.
- [ ] completed task의 요청도 parent를 reopen하지 않는다.
- [ ] 저장 실패 시 client draft가 유지되고 parent raw는 무변경이다.
- [ ] auth/CSRF prerequisite가 충족되지 않으면 write UI가 fail-closed다.

### Slice 3 — PM decision 및 연결

**후보 파일:**

- `operations_followup_requests.py`
- `operations_dashboard_server.py`
- `operations_dashboard/app.js`
- `operations_sync.py`는 derived task dispatch가 아니라 link evidence를 읽는 최소 범위만 검토
- 관련 API/projection/static tests

**AC**

- [ ] 사용자와 PM 권한이 분리된다.
- [ ] stale request version decision은 409다.
- [ ] live note 연결은 active task에만 허용되고 source request id/version을 기록한다.
- [ ] completed task는 live note 연결을 거부하고 derived task만 허용한다.
- [ ] derived task에 parent task와 source request가 기록된다.
- [ ] decision만으로 dispatch되지 않는다.
- [ ] owner role과 required verification이 명시된다.
- [ ] reject/clarification 사유가 audit history에 남는다.
- [ ] 기존 gate/final review endpoint 계약은 변경하지 않는다.

### 공통 출시 차단 조건

- 카드 write control 재노출
- result 도착을 stage/task 완료로 자동 승격
- verification binding 없이 verified/final approved 표시
- stale watchdog/sync snapshot이 canonical task를 덮어씀
- request submit이 task/stage/gate/final review/dispatch를 변경
- request submit 즉시 derived task dispatch
- request actor/auth를 client 값만으로 신뢰
- 승인 Slice A와 미검증 working-tree 변경 혼합 배포

---

## 8. Migration / Deploy Separation / Rollback

### 8.1 배포 lane

**Lane A — 승인 Slice A**

- 기준 commit: `26b3fa4`
- 목적: 승인된 progress UI만 배포
- 현재 working tree의 sync/policy/watchdog 변경 포함 금지

**Lane B — sync/research-policy/watchdog 후보**

- 현재 modified/untracked 상태를 별도 branch/worktree로 옮긴다.
- unit/contract/watchdog deterministic test와 reviewer 승인을 통과한 뒤 별도 배포한다.
- runtime 재기동은 배포 승인 후에만 수행한다.

**Lane C — v1.1 Slice 1**

- Lane A baseline 위에 projection/UI additive 변경
- Lane B raw producer에 의존하지 않도록 missing-safe
- Lane B가 승인되면 normalized evidence adapter를 별도 활성화

**Lane D — v1.1 request intake/decision**

- read UI와 write endpoint를 feature flag로 분리
- request read projection → submit intake → PM decision 순으로 활성화

### 8.2 데이터 migration

- 기존 task/result/dispatch/verification 파일 migration 없음
- request sidecar 디렉터리는 비어 있는 상태로 시작
- old task는 `follow_up_summary.pending_count=0`으로 동작
- progress schema v1 소비자는 유지하고 schema v2는 additive/fallback-safe
- 과거 live note를 follow-up request로 역변환하지 않는다.

### 8.3 Feature flags

- `OPS_PROGRESS_EVIDENCE_V11`
- `OPS_FOLLOWUP_REQUEST_READ`
- `OPS_FOLLOWUP_REQUEST_WRITE`
- `OPS_FOLLOWUP_PM_DECISION`

기본 순서: evidence read → request read → request write → PM decision.

### 8.4 Rollback

- UI/projection rollback: flag off, 기존 Slice A fallback
- request write rollback: endpoint 503/feature disabled, 기존 sidecar 보존·read 가능
- PM decision rollback: decision UI/endpoint off, pending 요청 보존
- data rollback: request 파일 삭제 금지. 잘못된 요청은 `cancelled/rejected/superseded` event로 정정
- runtime rollback: 승인된 release artifact로 재배포하되 raw operations 파일은 덮어쓰지 않음
- Lane B rollback은 Lane A/C와 독립적으로 수행

---

## 9. 테스트 / QA 매트릭스

### 9.1 상태 projection unit matrix

| ID | Fixture | 기대 결과 |
|---|---|---|
| P1 | result 없음, dispatch만 성공 | dispatch confirmed, result 대기 |
| P2 | result envelope 도착, stage in_progress | result 도착 + stage 전이 대기 |
| P3 | report 없음 completed envelope | rejected evidence, 완료 아님 |
| P4 | active derived id `-r1`, 이전 attempt 존재 | r1 active, 이전 history |
| P5 | writing/verification completed, final skipped | last completed verification, final skipped |
| P6 | verify envelope 있음, binding 없음 | verification evidence received unbound |
| P7 | PM review meets, artifact binding 없음 | review recorded unbound, final approved 아님 |
| P8 | stage completed, expected result 일부 누락 | raw 완료 + data-quality warning |
| P9 | unknown/future/null 상태 | raw 보존, positive 승격 없음 |
| P10 | md/json/html sidecars | bundle 1개, files N개 |

### 9.2 sync/watchdog matrix

| ID | Fixture | 기대 결과 |
|---|---|---|
| S1 | sync latest 없음 | never observed |
| S2 | pull_exit 0 | global success만 표시 |
| S3 | pull error | error + observed_at |
| S4 | accepted transition 있음 | 해당 task evidence 표시 |
| S5 | rejected report_missing | rejected reason 표시, stage 불변 |
| S6 | watchdog task snapshot < task updated_at | stale, task 상태 덮어쓰기 금지 |
| S7 | malformed JSON | unknown, API 500 방지 |
| S8 | timezone 없는 timestamp | 원문 보존 + timezone limitation |

### 9.3 request domain unit matrix

| ID | Fixture | 기대 결과 |
|---|---|---|
| R1 | valid submit | v1 pending_pm_review |
| R2 | empty title/outcome | 400, 파일 없음 |
| R3 | unknown target task | 404 |
| R4 | same idempotency key/payload | 기존 request 반환 |
| R5 | same key/different payload | 409 |
| R6 | version update | 새 version + supersedes |
| R7 | completed parent | submit 허용, parent 완료 유지 |
| R8 | write failure | partial file 없음/atomic write, parent 불변 |
| R9 | forged actor client field | 무시/거부, server actor 사용 |
| R10 | script/HTML payload | 저장은 text, UI escaped |

### 9.4 PM decision matrix

| ID | Fixture | 기대 결과 |
|---|---|---|
| D1 | active task + in-scope context | live note 연결 가능 |
| D2 | completed task + live note decision | 거부 |
| D3 | completed task + derived decision | child link 생성, parent 불변 |
| D4 | stale request version | 409 |
| D5 | owner/verification 없음 | validation error 또는 explicit PM defaults |
| D6 | accept decision retry | duplicate child/live note 없음 |
| D7 | reject | reason 필수, no link |
| D8 | decision 후 request 수정 | version conflict/supersede 정책 적용 |

### 9.5 API / security contract

- path traversal task/request id
- payload size limit
- invalid content type
- origin/CSRF/auth missing
- filesystem permission failure
- concurrent submit atomicity
- error payload의 경로/secret 비노출
- existing `/api/live-note`, `/api/gate-override`, `/api/final-review`, `/api/tasks` 계약 회귀 없음

### 9.6 Static UI contract

- 카드에 mutation control 없음
- detail에만 follow-up composer hook 존재
- 안내문에 `즉시 실행/승인되지 않음` 포함
- request state를 색 외 텍스트/아이콘으로 표시
- unknown/stale/failed copy 존재
- raw evidence disclosure 접근 가능
- 기존 detail focus trap/return focus 회귀 없음

### 9.7 수동 브라우저 QA

viewport: 1440px, 1024px, 390px.

- 대표 completed task를 10초 안에 판단
- sync/watchdog stale 경고를 current task 상태와 구분
- 긴 한국어 요청 title/outcome overflow
- 키보드만으로 composer open/close/submit/error recovery
- 중복 클릭과 네트워크 retry
- 저장 실패 시 draft 유지
- modal focus, Escape, return focus
- screen reader label/validation association
- 15초 refresh 중 작성 draft 유실 방지
- request submitted 후 상태 polling과 중복 row 방지

### 9.8 회귀 명령 후보

```bash
python3 -m unittest \
  tests.test_dashboard_projection \
  tests.test_dashboard_api_contracts \
  tests.test_dashboard_static_contract \
  test_operations_sync \
  tests.test_operations_watchdog \
  tests.test_operations_followup_requests
```

새 테스트 모듈은 구현 전 존재하지 않을 수 있으므로 developer가 추가한 뒤 위 명령을 실행한다. 실제 통과 수와 명령은 handoff에 기록한다.

### 9.9 대표 사례 browser acceptance

`T-20260729-001`에서 다음을 확인한다.

- raw completed
- research/writing/verification completed, final_write skipped
- writer original/revision result attempts 구분
- verify-co result 도착
- verification result와 PM review 각각 unbound limitation 표시
- stale watchdog가 writing/current로 오표시하지 않음
- completed task에 follow-up request 제출 가능
- 제출 후 parent는 completed 유지
- 요청은 pending PM review이며 즉시 실행/승인 문구 없음

---

## 10. 리스크 / 가정 / 미결 질문 / 후속 카드

### 10.1 주요 의사결정과 근거

1. **요청은 live note가 아니라 별도 intent record로 먼저 저장한다.**  
   live note는 비결정 맥락이며 version·decision·link가 부족하다. 별도 request가 제출과 반영을 분리한다.
2. **completed task를 reopen하지 않는다.**  
   원본 감사 이력을 보존하고 후속 scope를 derived task로 분리한다.
3. **카드는 계속 read-only다.**  
   Slice A acceptance와 빠른 overview의 안전성을 유지한다.
4. **sync/watchdog는 authority가 아니라 관찰 evidence다.**  
   canonical task보다 오래될 수 있으므로 observed_at/source limitation이 필수다.
5. **verification과 PM review는 binding이 있을 때만 강한 완료/승인으로 승격한다.**  
   대표 사례의 envelope summary와 PM review가 서로 다른 메시지를 가질 수 있어 과장 방지가 필요하다.
6. **배포 lane을 분리한다.**  
   승인 commit과 미검증 working-tree 변경을 섞으면 rollback과 원인 추적이 불가능해진다.

### 10.2 가정

- **A1:** Dashboard v1.1은 local 또는 인증된 사용자만 접근한다.
- **A2:** request sidecar를 생성할 수 있는 filesystem 권한이 있다.
- **A3:** active `derived_task_id`가 stage result 귀속의 1차 key다.
- **A4:** PM decision은 기존 PM 권한 체계로 인증할 수 있다.
- **A5:** live note writer에 source request optional metadata를 additive하게 넣을 수 있다.
- **A6:** derived task 생성 함수는 parent/source link를 additive field로 받을 수 있다.
- **A7:** 기존 projection v1 소비자는 unknown additive field를 무시한다.

### 10.3 리스크와 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| 요청 submit endpoint가 운영 실행 API로 확장 | 우발 실행 | intake/decision/dispatch route와 권한 분리, submit 불변조건 테스트 |
| 인증 없는 local server가 네트워크에 노출 | 무단 요청 | bind/auth/origin prerequisite, 미충족 시 write flag off |
| request sidecar 동시 write | 중복/손상 | atomic temp+rename, idempotency index, lock |
| active attempt 판정 오류 | 잘못된 결과 표시 | exact derived id, 모호하면 history/unknown |
| verify summary와 PM verdict 상충 | 잘못된 승인 | 독립 축, binding, conflict warning |
| stale snapshot 오판 | 잘못된 현재 상태 | raw updated_at 비교, stale 표시, authority 금지 |
| detail 정보 과밀 | 판단 지연 | summary→evidence disclosure 계층화 |
| 15초 refresh 중 draft 유실 | 사용자 손실 | task/request별 local draft, submit 성공 후만 clear |
| 미검증 working tree 혼합 | 운영 회귀 | Lane A/B 분리, release manifest, 재기동 금지 |

### 10.4 미결 질문과 권고

1. **request raw를 별도 sidecar로 둘 것인가, task JSON 배열로 둘 것인가?**  
   권고: sidecar. 제출 시 parent 불변과 atomic rollback이 쉽다.
2. **PM decision UI를 같은 Slice에 넣을 것인가?**  
   권고: intake와 분리된 Slice 3. 권한과 side effect가 다르다.
3. **completed task 요청을 항상 derived task로 만들 것인가?**  
   권고: 그렇다. 원본 완료 이력을 보존한다.
4. **live note에 연결된 요청을 실행 완료로 언제 표시하는가?**  
   권고: 표시하지 않는다. live note consumed도 실행 성공이 아니다.
5. **PM review의 artifact binding을 과거 데이터에 보강할 것인가?**  
   권고: 자동 migration 금지. 새 review부터 binding을 강제하고 과거는 unbound로 표시한다.
6. **sync/watchdog freshness threshold는 얼마인가?**  
   권고: 운영 주기에서 설정하고 projection에 threshold/source를 노출한다. UI hard-code 금지.
7. **`verify-co` envelope의 summary verdict를 구조화할 것인가?**  
   권고: 후속 producer contract에서 verdict/artifact binding을 추가하되 본문 parsing은 금지한다.

### 10.5 후속 Developer 카드 명세

**제목:** `DEV-V11-1: Dashboard 상태·sync/watchdog evidence Slice 1`

- 담당: `developer`
- 입력: 본 PRD 2~4, 6.5~6.6, 7 Slice 0~1, 9.1~9.2
- 필수: 승인 baseline과 미검증 working tree 분리, projection/UI/tests 구현
- 완료 증거: changed files, test command/count, representative JSON/render capture, stale snapshot 재현, raw non-mutation

**제목:** `DEV-V11-2: Follow-up request intake Slice 2`

- 담당: `developer`
- 의존: DEV-V11-1 acceptance
- 입력: 본 PRD 5, 6.1~6.4/6.7, 7 Slice 2, 9.3/9.5
- 필수: detail-only UX, sidecar schema, idempotency, atomic write, parent invariance
- 완료 증거: API fixtures, concurrency/idempotency tests, parent before/after comparison, browser capture

### 10.6 후속 Reviewer 카드 명세

**제목:** `VERIFY-V11-1: 상태·동기화·요청 안전성 acceptance review`

- 담당: `reviewer`
- 의존: 각 developer slice
- 검증: 오표시, stale evidence, binding, card read-only, request state transition, authority boundary, regression
- 출시 차단: 7장의 공통 출시 차단 조건 하나라도 위반
- 결과: PASS / NEEDS_CHANGES, finding severity, file/line/evidence, 재현 명령

### 10.7 후속 QA 카드 명세

**제목:** `QA-V11-1: Dashboard v1.1 browser·accessibility·failure QA`

- 담당: `reviewer` 또는 실제 `qa` profile이 있으면 `qa`
- 의존: developer + reviewer contract acceptance
- 범위: 1440/1024/390px, keyboard, focus, screen reader labels, refresh draft retention, network retry, duplicate submit, stale snapshot copy
- 산출물: viewport별 screenshot/evidence, pass/fail matrix, blocker 목록

### 10.8 PM 후속

- Lane A/B 배포 분리 승인
- request intake write enable 전 인증/Origin 정책 승인
- PM decision Slice 3 진입 여부 결정
- owner role 및 required verification taxonomy 확정
- 후속 카드 결과를 바탕으로 request 기능의 운영 활성화 결정

---

## Acceptance Criteria 최종 체크리스트

- [x] 문제·목표·비목표를 정의했다.
- [x] 실제 `T-20260729-001` raw completed 상태와 writer/verify 결과를 확인해 반영했다.
- [x] 이전 result 도착/parent stage in_progress 불일치 원인을 설명했다.
- [x] task/stage/agent/artifact/verification/PM review/sync를 독립 축으로 정의했다.
- [x] sync/watchdog observed_at·success/error·transition evidence·source limitation 최소 설계를 포함했다.
- [x] overview/card/detail 화면 요구사항을 정의했다.
- [x] 카드 write control 금지와 detail-only 추가 작업 요청을 명시했다.
- [x] 추가 요청이 자동 실행·자동 승인·기존 상태 변경으로 이어지지 않는 상태 전이를 정의했다.
- [x] versioned/traceable request raw schema, idempotency, audit, 권한 모델을 정의했다.
- [x] live note와 derived task 연결 기준을 분리했다.
- [x] API/projection/canonical source 계약과 fail-safe 규칙을 정의했다.
- [x] 승인 Slice A와 미검증 sync/policy/watchdog 변경의 분리 배포·rollback 순서를 정의했다.
- [x] 구현 파일 후보, slice별 AC, non-goal, 출시 차단 조건을 제시했다.
- [x] unit/API/security/static/browser QA 매트릭스를 제시했다.
- [x] 리스크·가정·미결 질문을 라벨링했다.
- [x] developer/reviewer/QA/PM 후속 카드 명세를 포함했다.

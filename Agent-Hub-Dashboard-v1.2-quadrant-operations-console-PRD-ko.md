# Agent Hub Dashboard v1.2 — 4사분면 운영 콘솔 PRD

- 문서 상태: 개발·디자인·검증 handoff용
- 제품 범위: Agent Hub Dashboard-only v1.2
- 기준 저장소: `/home/raphael/myproject`
- 기준 작업: `PLAN-V12-1`
- 선행 문서:
  - `Agent-Hub-Dashboard-v1.1-progress-and-followup-PRD-ko.md`
  - `Agent-Hub-Dashboard-v1.1-final-artifact-viewer-PRD-ko.md`
- 핵심 원칙: **4개 pane은 서로 다른 질문에 답하고, raw canonical 상태를 바꾸거나 추론하지 않는 projection을 기본으로 한다. 명시적 작성 surface도 실행·승인·완료와 분리한다.**

## 기획 요약

v1.2는 길게 이어진 Dashboard 섹션을 데스크톱 2×2 운영 콘솔로 재구성한다. 1영역은 PM과의 현재 대화 및 명시적 업무 지시, 2영역은 agent 가용성과 실행 근거, 3영역은 최소 밀도의 프로젝트 탐색, 4영역은 지금 판단할 blocker·decision·reviewable·unknown을 맡는다.

이 개편은 시각적 재배치만이 아니다. 각 pane의 목적, 데이터 source, 허용 action, 권한 경계를 분리한다. 특히 다음 의미를 합치지 않는다.

- configured/available과 실제 dispatch 성공
- dispatch 성공과 result 도착
- result 도착과 stage 완료
- 자유 텍스트 제출과 PM 승인·실행
- project 집계와 개별 task raw status
- reviewable artifact와 final deliverable
- 관찰 snapshot과 canonical task 상태

권고 구현은 additive `dashboard_console` projection과 단일 read snapshot을 먼저 만들고, 그 위에 4-pane shell을 얹는 순서다. 기존 task detail의 Final Deliverable 최상단, artifact viewer top-layer/focus, detail-only follow-up request, raw state fail-safe 원칙은 유지한다.

---

## 1. 문제, 배경, 목표

### 1.1 현재 문제

현재 첫 화면은 Mission Control, Decision Queue, Active Work Board, Reviewable Artifacts, Recent Audit, 보조 agent context가 세로로 이어진다. 정보는 풍부하지만 운영자가 다음 네 질문을 한 화면에서 병렬로 보기 어렵다.

1. PM과 어떤 맥락을 주고받고 있으며 다음 지시는 무엇인가?
2. 어떤 agent가 실제로 구성됐고, 어떤 작업을 받아 결과를 냈는가?
3. 어떤 프로젝트가 진행 중이고 어떤 프로젝트가 끝났는가?
4. 지금 Raphael님 또는 PM이 판단할 한정된 항목은 무엇인가?

현재 구현에는 다음 구조적 한계도 있다.

- `index.html`의 주요 섹션은 세로 DOM 순서이며 2×2 pane contract가 없다.
- `/api/overview`에는 `agents`가 있지만 `loadDashboard()`는 별도 Agents pane을 렌더링하지 않는다.
- 현재 static contract는 agent surface가 없어야 한다고 고정한다. v1.2에서는 의도적으로 교체해야 한다.
- `build_agent_summary()`는 task에 언급된 agent를 task 전체 status로 집계한다. stage별 dispatch/result 근거와 무관한 agent까지 active/completed로 셀 수 있다.
- raw task에는 안정적인 `project_id`가 없다. 제목·task id·디렉터리명으로 프로젝트를 추론하면 canonical 원칙을 깨뜨린다.
- 현재 `POST /api/tasks`, `/api/auto-dispatch`, `/api/live-note`, `/api/final-review`, `/api/gate-override`가 함께 존재한다. 새 콘솔에서 action을 잘못 배치하면 read-only 카드 원칙과 권한 경계가 흐려진다.
- `/api/overview`, `/api/tasks`, `/api/results` 등을 병렬 fetch하므로 한 렌더 사이클에서도 서로 다른 관찰 시점의 데이터가 섞일 수 있다.

### 1.2 왜 지금인가

v1.1에서 다음 기반이 이미 생겼다.

- raw-preserving `dashboard_projection`
- 결과 도착과 stage 완료를 분리한 `progress.agent_states`
- decision queue와 data quality
- sync/watchdog freshness 표시
- detail-only follow-up request
- task detail 최상단 Final Deliverable
- top-layer artifact viewer와 modal coordinator

따라서 v1.2는 새 workflow engine을 만드는 대신, 이 projection을 운영 질문별 pane으로 재구성할 수 있다.

### 1.3 목표

1. 데스크톱 첫 화면에서 10초 안에 네 운영 질문의 상태를 각각 식별하게 한다.
2. 4영역 Mission Control에서 blocker·decision·reviewable·unknown을 가장 빠르게 판단하게 한다.
3. 1영역 자유 텍스트가 task/stage/approval/completion/agent success를 자동 변경하거나 암시하지 않게 한다.
4. 2영역에서 agent의 가용성, dispatch, result, failure/blocked, unknown을 분리한다.
5. 3영역에서 프로젝트를 최소 밀도로 탐색하되 project identity나 상태를 임의 추론하지 않는다.
6. 네 pane 어디서 task를 열어도 동일 task detail과 top-layer artifact viewer를 사용한다.
7. 390px, 768px, 1440px 대표 viewport에서 Mission Control과 instruction input이 묻히지 않게 한다.
8. 기존 v1.1 projection·final artifact·viewer·follow-up contract의 의미 회귀를 0건으로 유지한다.

### 1.4 성공 지표

- 4-pane 대표 fixture에서 pane 목적 위반 또는 같은 action의 중복 노출 0건
- dispatch-only fixture가 `result_received` 또는 완료로 표시되는 오탐 0건
- unbound/free-text instruction이 승인·실행·완료로 표시되는 오탐 0건
- project identity가 없는 task를 임의 프로젝트로 묶는 오탐 0건
- Mission Control의 blocker/decision/reviewable/unknown 분류 fixture 정확도 100%
- 1440px에서 4영역 모두 첫 viewport에 식별 가능한 heading과 핵심 row 노출
- 390/768px에서 Mission Control과 instruction composer에 2회 이하의 주요 탐색 동작으로 접근
- keyboard-only로 pane 이동, row 열기, task detail, viewer open/close/return focus 완료
- 기존 projection/server/static test와 v1.1 browser acceptance 회귀 0건

### 1.5 비목표

- raw task/stage schema를 Dashboard projection이 자동 교정하는 기능
- 카드 또는 Agents/Projects/Mission Control row에서 dispatch, approval, gate override, final review override 실행
- 대화 텍스트에서 task 완료, stage 승인, agent 성공을 자연어 추론하는 기능
- Dashboard를 Kanban, chat, IDE, remote runner의 canonical control plane으로 승격
- project portfolio planning, budget, roadmap, Gantt, dependency editing
- agent performance ranking 또는 생산성 점수
- 기존 follow-up request를 1영역 instruction으로 자동 변환
- artifact viewer, final artifact 판정 알고리즘의 재설계
- 자유 배치형 window manager 또는 pane detach

---

## 2. 사용자와 핵심 Job

### 2.1 사용자

| 사용자 | 핵심 필요 |
|---|---|
| Raphael님 | 현재 대화·업무·agent·판단 항목을 한 화면에서 확인하고 안전하게 지시한다. |
| HermesPM | 자유 텍스트 의도와 canonical workflow 결정을 분리해 검토한다. |
| 운영 Developer | 동일 snapshot과 projection contract로 pane을 구현한다. |
| Verifier/QA | 상태 축·권한·반응형·viewer 회귀를 fixture와 browser에서 검증한다. |

### 2.2 Job stories

- 운영 상황을 확인할 때, 네 운영 질문을 같은 화면에서 비교하고 싶다. 그래야 여러 섹션을 스크롤하며 관계를 재구성하지 않아도 된다.
- PM에게 추가 지시를 남길 때, 지시가 언제·무엇을 대상으로 기록됐는지 알고 싶다. 그래야 실행 또는 승인으로 오해하지 않는다.
- agent 상태를 볼 때, 구성 가능성과 실제 수행 근거를 분리하고 싶다. 그래야 dispatch 성공을 작업 완료로 오판하지 않는다.
- 프로젝트를 훑을 때, 진행/완료 정도만 보고 task detail로 들어가고 싶다. 그래야 첫 화면이 다시 task board가 되지 않는다.
- 판단할 일이 있을 때, blocker와 unknown을 reviewable artifact보다 먼저 보고 싶다. 그래야 위험과 데이터 공백을 먼저 처리한다.

---

## 3. 제품 원칙과 불변조건

### 3.1 Canonical과 projection

1. raw task/stage/dispatch/result envelope/verification/PM review/follow-up request가 canonical evidence다.
2. `dashboard_console`은 additive read projection이다.
3. projection은 raw 값을 overwrite하지 않는다.
4. missing, null, unknown, conflict를 서로 구분한다.
5. 파일명, mtime, 제목 유사도, 자유 텍스트는 긍정 상태의 근거로 쓰지 않는다.
6. stale sync/watchdog snapshot은 현재 상태 authority가 아니다.
7. 화면 집계와 raw 상태가 충돌하면 raw를 유지하고 projection에 limitation을 표시한다.

### 3.2 Action 경계

- **Pane row/card:** 읽기 전용. 허용 action은 선택, 필터, 접기/펼치기, task detail 열기, 안전한 viewer 열기뿐이다.
- **1영역 composer:** 명시적 command surface다. 새 brief 저장 또는 append-only instruction 제출만 허용한다.
- **Task detail:** 기존 detail-only follow-up intake와 이미 허용된 scoped control contract를 유지한다. pane에 복제하지 않는다.
- **Pane resize:** 로컬 표현 설정이며 workflow mutation이 아니다. 서버 canonical에 쓰지 않는다.
- **Refresh:** read action이다.

### 3.3 상태 의미 불변조건

- `configured/available ≠ dispatch_confirmed`
- `dispatch_confirmed ≠ result_received`
- `result_received ≠ raw stage completed`
- `verification result received ≠ verification stage completed`
- `PM review recorded ≠ artifact-bound final approved`
- `instruction submitted ≠ accepted ≠ dispatched ≠ completed`
- `project progress summary ≠ task status rewrite`
- `reviewable artifact ≠ final deliverable`
- `sync success ≠ every task synchronized`

---

## 4. Information Architecture

### 4.1 데스크톱 고정 배치

```text
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ 1 · PM CONVERSATION / INSTRUCTION   │ 2 · AGENTS                          │
│ 현재 맥락 · 새 업무 · 추가 지시     │ 가용성 · 수행 근거 · 검토 대기       │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ 3 · PROJECTS                        │ 4 · MISSION CONTROL                 │
│ 진행/완료 최소 목록 · detail 진입   │ blocker · decision · reviewable · ? │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

- label number와 이름은 고정한다.
- 기본 위치는 1=좌상단, 2=우상단, 3=좌하단, 4=우하단이다.
- pane 내부만 스크롤한다. 전체 page scroll이 4영역 접근성을 결정하지 않게 한다.
- desktop 기본 비율은 열 `50:50`, 행 `46:54`를 권고한다. 4영역은 3영역보다 같거나 큰 기본 높이를 갖는다.
- resize handle은 열 divider 1개, 행 divider 1개다. 최소 폭/높이를 넘지 않는다.
- resize 값은 localStorage에만 저장한다. Reset layout을 제공한다.
- 4영역 최소 크기는 다른 pane보다 작아질 수 없게 한다. Mission Control을 0에 가깝게 접는 기능은 제공하지 않는다.

### 4.2 전역 chrome

허용:

- 제품명
- snapshot 생성 시각과 freshness
- 새로고침
- layout reset
- 전체 data-quality 경고

첫 화면 전역 chrome에서 제외:

- auto dispatch
- gate/final review override
- 승인 버튼
- raw task status 변경

기존 API를 제거할 필요는 없지만 v1.2 전역 chrome에 노출하지 않는다.

### 4.3 공통 pane 구성

각 pane은 다음 순서를 따른다.

1. 고정 header: 번호, 이름, 한 줄 목적
2. summary: 최대 3개 수치 또는 상태
3. primary content: row/list/thread
4. empty/error/stale state
5. 필요 시 읽기 전용 secondary disclosure

각 row는 가능한 경우 다음을 가진다.

- 대상 label/id
- raw 또는 projection 상태
- evidence timestamp
- limitation 또는 provenance
- navigation-only action

### 4.4 Task detail과 viewer 진입

- 2·3·4영역 task 관련 row는 모두 동일 `openTaskDetail(task, trigger)`를 사용한다.
- 1영역의 instruction target task link도 동일 task detail을 연다.
- task detail body의 첫 section은 계속 Final Deliverable이다.
- artifact는 진입 pane과 무관하게 동일 top-layer viewer coordinator를 사용한다.
- viewer는 pane shell과 task detail보다 높은 layer다.
- Escape 1회는 topmost layer 1개만 닫는다.
- 닫은 뒤 최초 trigger로 focus를 복원한다.

---

## 5. 1영역 — PM Conversation / Instruction

### 5.1 목적

현재 PM 대화 맥락, 새 업무 brief 작성, 기존 업무에 대한 추가 PM 지시를 한 곳에서 보여주되, 자유 텍스트와 workflow 결정을 분리한다.

### 5.2 표시 데이터

고정 순서:

1. **Current context**
   - 대화 session/context id 또는 `연결 확인 불가`
   - 현재 선택 target: `task`, `project`, `none`
   - target id/title와 raw status
   - 마지막 context 기록 시각
2. **Conversation thread**
   - Raphael/PM role
   - message id
   - recorded_at
   - engine/fallback limitation이 있으면 표시
3. **Instruction composer**
   - mode: `new_task_brief` 또는 `additional_instruction`
   - target type/id
   - 자유 텍스트
   - PM interpretation preview
   - 명시적 submit
4. **Recent instruction records**
   - instruction id/version
   - target type/id
   - submitted_at/submitted_by
   - state
   - `pending PM review` 여부
   - accepted/rejected라면 decision evidence id

### 5.3 Instruction 상태 모델

| 상태 | 의미 | workflow 영향 |
|---|---|---|
| `draft_local` | 브라우저 로컬 초안 | 없음 |
| `submitted_pending_pm_review` | append-only instruction 기록 생성 | 없음 |
| `needs_clarification` | PM이 target/outcome 확인 요청 | 없음 |
| `accepted_as_new_brief` | PM 판단 후 새 brief/task identity 연결 | 새 task만 생성; 기존 task 불변 |
| `accepted_as_context` | 현재 대화 또는 non-decision context로 연결 | stage/approval/completion 불변 |
| `rejected` | 범위·위험·중복·권한 사유로 미수행 | 없음 |
| `superseded` | 새 version이 이전 instruction 대체 | 없음 |
| `unknown` | record 또는 state를 해석할 수 없음 | 없음; raw 확인 필요 |

금지되는 전이:

- `submitted_pending_pm_review → dispatched` 자동 전이
- 텍스트에 “승인”, “완료”, “실행”이 포함됐다는 이유로 canonical 상태 변경
- additional instruction 제출로 parent task reopen
- PM reply text만으로 stage gate/final review 생성

### 5.4 새 업무와 추가 지시 구분

**새 업무 brief**

- existing `POST /api/tasks` contract를 명시적 최종 submit 뒤 사용한다.
- title과 objective가 확인돼야 한다.
- 저장 성공은 `brief_created`이며 dispatch 성공이 아니다.
- 화면 copy는 `브리프 저장됨 · 진입 판단 대기`처럼 표현한다.

**추가 PM 지시**

- append-only instruction endpoint를 사용한다.
- target task/project/raw status와 submitted_at을 함께 기록한다.
- 제출 성공 copy는 `지시 기록됨 · PM 검토 대기`다.
- direct live note, gate override, dispatch를 호출하지 않는다.

### 5.5 기존 follow-up request와 경계

- 1영역 instruction: 현재 PM 대화와 운영 지시를 기록하는 command context다.
- task detail follow-up request: 특정 task 산출물의 추가·보완 결과를 요청하는 versioned intake다.
- follow-up request는 계속 detail-only다.
- 같은 의도가 양쪽에 중복 제출돼도 자동 병합하지 않는다.
- PM은 중복을 판단해 한쪽을 `rejected:duplicate` 또는 `superseded`로 남긴다.
- 1영역에는 `산출물 보완 요청은 업무 상세에서 작성` link를 제공할 수 있다.

### 5.6 허용 action과 권한

| Action | Raphael | PM | 시스템 | Pane 결과 |
|---|---:|---:|---:|---|
| 대화 읽기 | O | O | 제공 | read-only |
| 로컬 draft 작성 | O | O | - | canonical 영향 없음 |
| 새 brief 명시적 저장 | O | O | 기록 | 새 queued brief 생성 가능 |
| additional instruction 제출 | O | O | append-only 저장 | pending PM review |
| instruction accept/reject | X | O | 기록 | 별도 PM decision evidence 필요 |
| dispatch/approval/gate override | X | X | X | 1영역에서 금지 |

인증 actor를 신뢰할 수 없으면 write controls를 disabled 처리하고 `권한 확인 필요`를 표시한다.

### 5.7 빈값·오류 UX

- 대화 context 없음: `현재 연결된 PM 대화 맥락이 없습니다.`
- target 없음: `대상 없음 · 새 업무 맥락`
- target raw status 없음: `대상 상태 확인 불가`
- instruction 이력 fetch 실패: composer는 무조건 활성화하지 않고 capability를 확인한다.
- submit timeout: idempotency key를 유지하고 draft를 보존한다.
- PM LLM fallback: `규칙 기반 임시 처리`를 숨기지 않는다.

---

## 6. 2영역 — Agents

### 6.1 목적

Agent List와 상태를 운영 관점에서 보여준다. 구성 가능성과 수행 결과를 분리하고, dispatch 성공을 작업 완료처럼 보이지 않게 한다.

### 6.2 Agent 상태 축

단일 status badge를 만들지 않고 최소 네 축을 유지한다.

1. **Availability**
   - `configured_available`
   - `configured_unavailable`
   - `needs_config`
   - `unknown`
2. **Dispatch evidence**
   - `not_dispatched`
   - `dispatch_confirmed`
   - `dispatch_failed_or_blocked`
   - `unknown`
3. **Result evidence**
   - `none`
   - `partial_received`
   - `result_received`
   - `failed_or_blocked`
   - `unknown`
4. **Workload summary**
   - active task count
   - review waiting count
   - blocked count
   - recent result count 또는 last result state

Availability와 execution을 하나의 초록/빨강 상태로 합치지 않는다.

### 6.3 Agent row 표시

- agent display name / profile slug 또는 worker key
- role label
- availability badge와 근거 source
- 현재 작업 수
- 검토 대기 수
- blocked/failed 수
- 최근 상태 변화: from/to 또는 event kind
- evidence_at
- source limitation
- 최대 1개 navigation CTA: `관련 업무 보기`

### 6.4 집계 규칙

1. agent identity는 profile registry, workers config, exact stage agent, exact result envelope worker key에서만 가져온다.
2. task title에 agent 이름이 나온다는 이유로 연결하지 않는다.
3. active count는 해당 agent가 현재 stage에 할당됐거나 exact dispatch/result evidence가 있을 때만 센다.
4. completed parent task는 agent result가 없으면 그 agent의 completed count로 세지 않는다.
5. `dispatch_confirmed`는 active/waiting일 수 있으나 completed/result count에 넣지 않는다.
6. exact result envelope + existing report가 있을 때만 `result_received`다.
7. failed metadata 또는 failed dispatch가 positive state보다 우선한다.
8. worker key alias가 명시적으로 매핑되지 않으면 별도 unknown identity로 남긴다.
9. evidence timestamp가 없으면 `시간 확인 불가`를 표시한다.

### 6.5 현재 구현과의 교정

현재 `build_agent_summary()`는 task 전체 status를 관련 agent 모두에게 집계한다. v1.2에서는 `dashboard_projection.progress.agent_states[stage][agent]`와 dispatch/result evidence를 사용해 집계를 다시 만든다.

예:

- task completed, research agent result 있음, writer result 없음
  - research agent: result received/completed evidence 가능
  - writer: task에 계획돼 있었다는 이유만으로 completed count 증가 금지
- worker configured, dispatch 없음
  - availability configured
  - execution not dispatched
- dispatch record만 있음
  - dispatch confirmed
  - result none
  - copy: `전송 확인 · 결과 대기`

### 6.6 정렬

1. failed/blocked
2. review waiting
3. active with dispatch/result evidence
4. configured idle
5. needs config
6. unknown

같은 그룹에서는 latest evidence_at 내림차순, 시각이 없으면 이름순이다.

### 6.7 허용 action

- agent row 선택
- 관련 task 목록 filter 또는 task detail 열기
- source/limitation disclosure

금지:

- dispatch
- retry
- cancel
- assign
- approve
- availability toggle

---

## 7. 3영역 — Projects

### 7.1 목적

프로젝트 목록을 최소 밀도로 제공하고, 선택 시 관련 task detail/context로 연결한다. 이 pane은 task board나 portfolio editor가 아니다.

### 7.2 Project identity

강한 project identity 우선순위:

1. raw task의 explicit `project_ref.project_id`
2. canonical project registry의 exact task binding
3. 없으면 `unassigned` bucket

금지:

- task 제목 유사도로 프로젝트 추론
- task id prefix를 project id로 사용
- 폴더명 또는 최근 선택으로 project 자동 귀속
- `unassigned`를 실제 프로젝트처럼 이름 붙이기

`unassigned`는 UI에서 `프로젝트 미지정`으로 표시하며 project count와 별도로 셀 수 있다.

### 7.3 Project 상태 표시

Project row는 다음만 기본 표시한다.

- project name/id
- raw project status가 있으면 raw 값
- active task count
- done task count
- unknown task count가 있으면 경고
- latest task evidence_at
- navigation-only CTA

기본 label은 다음 정도로 제한한다.

- `진행 중`: active task가 1개 이상이며 blocker/unknown이 projection을 무효화하지 않음
- `완료`: 명시적으로 bound된 task가 모두 raw completed/cancelled이고 unknown이 없음
- `확인 필요`: project/task binding 또는 status에 unknown/conflict가 있음
- `프로젝트 미지정`: explicit identity 없음

Project projection은 raw task status를 바꾸지 않는다.

### 7.4 최소 밀도 원칙

첫 row에 넣지 않는 정보:

- 전체 stage timeline
- agent별 상세
- artifact 파일 목록
- acceptance criteria
- gate/final review control
- follow-up composer
- dispatch control

선택 시 다음 중 하나로 이동한다.

- task 1개: 해당 task detail
- task 여러 개: pane 내부 read-only task selector 후 task detail
- explicit project context URL이 있으면 read-only context view

### 7.5 Project 상태 집계

- `active`: raw task status가 done/cancelled가 아니고 known
- `done`: raw completed/cancelled
- `unknown`: missing/null/unsupported status
- blocker는 active와 별도 count로 표시할 수 있으나 project status를 자동 `failed`로 바꾸지 않는다.
- project completion은 task count의 비율일 뿐 artifact approval을 의미하지 않는다.
- unassigned task가 여러 개여도 하나의 실제 프로젝트로 간주하지 않는다.

### 7.6 허용 action

- project row 선택
- project 내 task 필터
- task detail 열기
- project context 읽기

금지:

- project 생성/삭제/상태 변경
- task project 재배정
- bulk approval/dispatch
- stage 또는 follow-up write

---

## 8. 4영역 — Mission Control

### 8.1 목적

기존 Mission Control의 “지금 판단할 일” 의미와 우선순위를 유지하면서, 4-pane 안에서 가장 빠르게 scan 가능한 판단 pane으로 만든다.

### 8.2 분류

| kind | 의미 | 대표 source |
|---|---|---|
| `blocker` | 진행을 막는 active hold, dispatch failure, failed result | raw stage/gate/dispatch/result |
| `decision` | PM/Raphael 판단이 필요한 명시적 final review, clarification, instruction review | decision evidence/pending record |
| `reviewable` | 검토 가능한 artifact/verification/result가 도착 | exact result/verification binding |
| `unknown` | missing/null/conflict/stale/unlinked로 안전한 판단 불가 | data_quality/operations evidence |

기존 `active_hold`는 `blocker`, `final_review`는 `decision`, `reviewable`은 그대로 매핑한다. `progress.next_pm_action.kind=blocked|unknown`도 각각 blocker/unknown 후보가 된다.

### 8.3 우선순위

기본 정렬:

1. blocker
2. decision
3. unknown
4. reviewable

각 그룹 내 tie-break:

1. raw priority가 명시돼 있으면 high > medium > low
2. deadline/aging 정책이 명시돼 있으면 breach 우선
3. evidence_at 오래된 순서가 아니라, 위험이 동일하면 latest actionable evidence 우선
4. timestamp unknown은 숨기지 않고 그룹 하단

Reviewable이 unknown보다 위험하지 않다는 기본 원칙을 사용한다. 단, explicit deadline policy가 있으면 projection reason과 함께 위로 올릴 수 있다.

### 8.4 Mission row 구성

- kind badge
- 한 문장 판단 질문
- task/project/instruction target
- raw status와 scope
- evidence 요약 최대 2개
- evidence_at
- source/limitation
- recommended next action
- navigation-only CTA `상세 확인`

`recommended next action`은 설명이다. 버튼 label이 mutation처럼 보이면 안 된다.

좋은 예:

- `작성 stage gate hold 근거를 확인하세요 · task detail 열기`
- `지시가 PM 검토 대기입니다 · instruction record 보기`
- `검증 결과가 도착했습니다 · artifact binding 확인`
- `agent result 귀속을 확인할 수 없습니다 · raw evidence 보기`

금지 copy:

- `승인하기`
- `재전송`
- `게이트 해제`
- `완료 처리`
- `검증 완료` — verification stage/result 축이 충분하지 않을 때

### 8.5 중복 제거

같은 사건이 여러 projection에 나타날 수 있다. Mission Control은 다음 key로 display duplicate만 줄인다.

`target_type + target_id + scope + evidence_id + kind`

- raw evidence를 삭제하거나 합치지 않는다.
- 같은 task라도 blocker와 reviewable이 동시에 있으면 두 kind를 유지할 수 있다.
- 같은 evidence가 Decision Queue와 Recent Audit에 동시에 있던 현재 UI는 Mission row 1개와 task detail audit으로 정리한다.

### 8.6 중요도 보존

- 4영역 header와 top 3 rows는 pane resize 후에도 최소 높이 안에서 보인다.
- 새 blocker가 생기면 색뿐 아니라 icon/text/count를 갱신한다.
- 전체 pane을 success empty state로 과도하게 강조하지 않는다.
- `지금 판단할 일 없음`은 data load 성공과 unknown count 0이 모두 확인될 때만 표시한다.
- load 실패 시 `판단 항목 없음` 대신 `Mission Control 확인 불가`를 표시한다.

### 8.7 허용 action

- task/instruction/project detail 열기
- raw evidence disclosure
- kind filter
- sort 설명 보기

금지:

- row에서 approval/override/dispatch/retry
- 추천 문구 클릭만으로 mutation
- unknown 자동 dismiss

---

## 9. 데이터 매핑

### 9.1 공통 snapshot contract

권고 신규 read endpoint:

`GET /api/dashboard-console`

```json
{
  "schema_version": 2,
  "snapshot_id": "opaque-id",
  "generated_at": "ISO-8601",
  "source_freshness": {
    "tasks": "ISO-8601|null",
    "agents": "ISO-8601|null",
    "sync": "ISO-8601|null",
    "watchdog": "ISO-8601|null"
  },
  "panes": {
    "pm_instruction": {},
    "agents": [],
    "projects": [],
    "mission_control": []
  },
  "tasks_by_id": {},
  "limitations": []
}
```

요구:

- server는 한 번의 `load_tasks()` 결과로 agents/projects/mission/task index를 만든다.
- 같은 response 안의 pane은 같은 task snapshot을 참조한다.
- 기존 `/api/overview`, `/api/tasks`, `/api/agents`, file/detail endpoint는 호환을 위해 유지한다.
- projection failure가 전체 response를 500으로 만들지 않도록 pane별 `state=unknown`과 limitation을 반환한다.
- raw secret, credential, full path가 새 endpoint로 추가 노출되지 않게 한다.

### 9.2 Task 매핑

| UI/Projection | Source | 규칙 |
|---|---|---|
| task id/title/objective | raw task | 그대로 표시 |
| raw status | raw task.status | missing/null/unknown 분리 |
| stage status | raw task.stages[].status | result로 자동 전이 금지 |
| dispatch | dispatch record | latest exact worker record |
| result | exact sidecar + report | worker/stage/task/active attempt match 필요 |
| verification | verification/result evidence | stage 완료와 별도 |
| final deliverable | v1.1 `final_deliverable` | 알고리즘 재사용 |
| audit | gate/final review/live note raw | 결정/non-decision scope 유지 |
| follow-up | follow-up request store | detail-only |
| project | explicit project_ref/registry | 추론 금지 |

### 9.3 Agent 매핑

| UI field | Source | Fail-safe |
|---|---|---|
| identity | profile registry/workers config/exact worker key | alias 불명확 시 unknown agent |
| availability | workers config + runtime worker status | timestamp 없으면 configured만 표시 |
| dispatch state | task dispatch records | result/complete로 승격 금지 |
| result state | `progress.agent_states` | unlinked sidecar는 unknown |
| active count | current stage exact assignment/evidence | task 전체 status 단순 복제 금지 |
| review count | reviewer/current verification assignment | parent task status만으로 추론 금지 |
| latest change | explicit event/evidence timestamp | mtime만으로 실행 성공 추론 금지 |

### 9.4 Project 매핑

| UI field | Source | Fail-safe |
|---|---|---|
| project id/name | raw project_ref 또는 canonical registry | 없으면 unassigned |
| active/done counts | bound raw task statuses | unknown 별도 |
| latest evidence | bound task updated_at/evidence_at | 정렬용, 상태 증명 아님 |
| context link | explicit registry URL/id | 제목 기반 link 생성 금지 |

### 9.5 Mission Control 매핑

| Source | Mission kind | 조건 |
|---|---|---|
| active hold/gate hold | blocker | raw active hold 존재 |
| dispatch/result failed | blocker | exact failure evidence |
| final review not_meets/pending decision | decision | scope와 evidence 존재 |
| pending instruction | decision | `submitted_pending_pm_review` |
| artifact/verification reviewable | reviewable | exact safe item 존재 |
| projection data quality | unknown | missing/null/conflict/unlinked |
| stale sync/watchdog | unknown 또는 보조 limitation | canonical task를 대체하지 않음 |

### 9.6 PM instruction 매핑

권고 신규 append-only endpoint:

`POST /api/dashboard/instructions`

필수 요청:

- `instruction_type`
- `target_type`
- `target_id` 또는 null
- `target_raw_status` snapshot 또는 null
- `text`
- `conversation_context_id` 또는 null
- `client_created_at`
- `Idempotency-Key`

필수 응답:

- `instruction_id`
- `version`
- `state=submitted_pending_pm_review`
- `submitted_at`
- `submitted_by`
- `target`
- `parent_changed=false`

보안/권한:

- same-origin 확인
- JSON content type
- payload limit
- text escape
- actor/capability 확인
- idempotent retry
- append-only event history
- 기존 task/stage/gate/final review/dispatch mutation 금지

---

## 10. 반응형·리사이즈·접근성

### 10.1 Desktop — 1200px 이상

- 2×2 grid
- pane별 독립 scroll
- row/column divider keyboard 조절 지원
- 최소 pane 폭 360px 권고
- 최소 pane 높이: 1영역 280px, 2영역 240px, 3영역 220px, 4영역 280px
- Mission Control top rows와 instruction composer가 최소 크기에서 보여야 한다.

### 10.2 Tablet — 768~1199px

권고 stack:

1. 4 · Mission Control
2. 1 · PM Conversation / Instruction
3. 2 · Agents
4. 3 · Projects

- label number는 desktop 위치 의미를 유지한다.
- 2열을 사용할 경우 첫 행에 4와 1을 둔다.
- pane resize는 끄고 각 pane height auto/max-height를 사용한다.

### 10.3 Mobile — 767px 이하

- 1열 stack
- 기본 순서: 4 → 1 → 2 → 3
- 상단 compact jump nav: `판단`, `지시`, `Agents`, `Projects`
- Mission Control top 3 rows는 heading 아래 즉시 표시
- instruction composer는 thread 전체 아래 묻히지 않도록 `지시 작성` sticky affordance 또는 thread collapse 제공
- touch target 최소 44×44px
- pane 내부와 page의 이중 scroll을 피한다.

### 10.4 Resize 동작

- pointer와 keyboard 모두 지원
- divider는 `role=separator`, orientation, value now/min/max 제공
- Arrow key로 조절, Shift+Arrow로 큰 단위 조절
- Reset layout 제공
- 값은 viewport tier별 localStorage key로 저장
- 저장값이 새 minimum과 충돌하면 clamp
- localStorage 실패가 console load를 막지 않음

### 10.5 Focus와 layer

- pane 간 landmark/heading navigation 지원
- row open 후 task detail heading으로 focus 이동
- viewer open 시 top-layer focus trap
- Escape topmost-only
- viewer close → artifact trigger
- task detail close → pane row trigger
- layout rerender 중 trigger가 사라지면 해당 pane heading으로 안전하게 복귀

### 10.6 상태 전달

- 색만으로 상태를 구분하지 않는다.
- icon + text + badge 조합을 사용한다.
- live refresh는 전체 pane에 불필요한 `aria-live` 폭주를 만들지 않는다.
- 새 blocker/submit result 등 중요 변화만 polite announcement를 사용한다.
- timestamp는 ISO raw disclosure와 현지화 display를 함께 제공할 수 있다.

---

## 11. v1.1과의 충돌·중복·보존 결정

### 11.1 현행 화면과의 매핑

| v1.1 surface | v1.2 처리 | 결정 이유 |
|---|---|---|
| Mission Control counts | 4영역 header summary로 이동 | 판단 pane에 집중 |
| Decision Queue | 4영역 primary list로 통합 | 같은 질문의 중복 제거 |
| Active Work Board | 3영역 최소 프로젝트 목록 + detail 진입으로 축소 | 첫 화면 과밀 해소 |
| Reviewable Artifacts | 4영역 reviewable rows와 task detail로 이동 | 판단 맥락에 통합 |
| Recent Audit | pane row에서는 요약, full audit은 task detail 유지 | raw 근거 보존, 중복 축소 |
| secondary agent context | 2영역 Agents로 승격 | 고정 운영 질문 충족 |
| brief modal | 1영역 command surface로 이동 | 현재 맥락과 지시 통합 |
| header auto dispatch | v1.2 첫 화면에서 제거 | command/inspect 경계 보호 |

### 11.2 Final Deliverable

- task detail 첫 section 유지
- 3·4영역에 final file을 직접 복제하지 않는다.
- Mission row는 `최종 결과물 확인 필요/가능` 정도만 요약하고 task detail로 연결한다.
- `confirmed`, `candidate_unconfirmed`, `ambiguous`, `conflict`, `unavailable`, `unknown` 의미를 바꾸지 않는다.
- mtime/filename으로 final을 선택하지 않는다.

### 11.3 Artifact viewer

- 기존 `modalStack`, top-layer, sandbox, referrer policy, scroll lock을 보존한다.
- 4-pane shell이 새 stacking context를 만들더라도 viewer는 shell 밖 top layer에 둔다.
- pane overflow가 viewer를 clip하지 않게 한다.
- 390px fullscreen viewer contract를 유지한다.

### 11.4 Follow-up work

- task detail의 Additional work requests는 그대로 유지한다.
- 1영역 instruction과 동일 form/component로 합치지 않는다.
- pane에는 pending follow-up count를 읽기 전용으로 표시할 수 있으나 작성은 detail로 이동한다.
- follow-up submit으로 parent task/stage/gate/final review/dispatch를 바꾸지 않는다.

### 11.5 Existing scoped controls

- task card/Agents/Projects/Mission pane에 gate/final review/live note/dispatch control을 복제하지 않는다.
- 기존 task detail scoped controls는 별도 정책 변경 전까지 유지한다.
- v1.2 static test는 pane row가 navigation-only인지 별도로 검사한다.

### 11.6 Static contract 교체

현재 test의 `agent surface is absent` contract는 v1.2 의도와 충돌한다. 이를 삭제만 하지 말고 다음 contract로 교체한다.

- 4개 pane hook과 고정 label 존재
- desktop 2×2 order/position
- responsive priority order 4→1→2→3
- Agents row renderer 존재
- pane row mutation API 호출 없음
- task detail/viewer/follow-up hooks 보존

---

## 12. API 요구사항

### 12.1 Read API

`GET /api/dashboard-console`

- status 200에서 네 pane key를 항상 반환한다.
- pane 데이터가 없으면 빈 배열과 explicit empty state를 제공한다.
- malformed source는 raw secret 없이 limitation을 제공한다.
- `schema_version=2`를 고정한다.
- `snapshot_id`와 `generated_at`을 제공한다.
- task ref는 `tasks_by_id` exact key를 사용한다.
- agent/project/mission row가 존재하지 않는 task id를 참조하지 않는다.

기존 API:

- `/api/tasks`: task detail/fallback 호환 유지
- `/api/agents`: 호환 유지하되 새 execution semantics를 반영하거나 deprecated 표시
- `/api/overview`: 기존 consumer 호환
- `/files/*`: viewer 보안 header 유지

### 12.2 Instruction write API

- capability endpoint를 제공한다: `GET /api/dashboard/instruction-capabilities`
- same-origin, actor, enabled 여부를 확인한다.
- request limit과 idempotency를 적용한다.
- 성공 response는 `parent_changed=false`를 포함한다.
- instruction text를 canonical decision으로 파싱하지 않는다.
- PM accept/reject는 별도 PM-only 처리이며 Dashboard pane CTA로 제공하지 않는다.

### 12.3 Error contract

공통 error shape:

```json
{
  "ok": false,
  "error": {
    "code": "stable_enum",
    "message": "safe user message",
    "retryable": false
  }
}
```

- network/500: 마지막 성공 snapshot이 있으면 `stale` 표시와 함께 유지
- 403: write disabled, draft 유지
- 409: idempotency/target version conflict, record 조회 유도
- 413/415: 안전한 validation copy
- unknown enum: raw value를 숨기지 않고 UI는 `확인 불가`

### 12.4 성능

- 한 console snapshot에서 task source를 중복 scan하지 않는다.
- 첫 payload는 full artifact preview/body를 포함하지 않는다.
- 기본 목표: 로컬 기준 100 tasks, 30 agents에서 projection p95 500ms 이하를 검증한다.
- pane render는 큰 list에서 initial cap/virtualization 또는 incremental render를 고려한다.
- detail/viewer content는 필요할 때 가져온다.

---

## 13. Acceptance Criteria

### 13.1 IA / Layout

- [ ] 1440px에서 1 좌상, 2 우상, 3 좌하, 4 우하가 2×2로 표시된다.
- [ ] 각 pane은 번호·이름·목적을 명확히 표시한다.
- [ ] 4영역의 기본 면적과 최소 높이가 3영역보다 작지 않다.
- [ ] pointer와 keyboard로 divider를 조절할 수 있다.
- [ ] layout reset이 동작하며 workflow API를 호출하지 않는다.
- [ ] 768px tier에서 4와 1이 2·3보다 먼저 접근된다.
- [ ] 390px에서 stack 순서가 4→1→2→3이며 jump nav가 있다.
- [ ] pane overflow가 task detail 또는 viewer를 clip하지 않는다.

### 13.2 1영역 UI

- [ ] current context, target type/id/raw status, recorded_at이 표시된다.
- [ ] 새 업무와 additional instruction mode가 구분된다.
- [ ] additional instruction submit 전 `즉시 실행·승인이 아님`을 표시한다.
- [ ] submit 성공 시 instruction id/version/state/time/pending PM review를 표시한다.
- [ ] timeout/error에서 draft와 idempotency key가 유지된다.
- [ ] 자유 텍스트로 task/stage/approval/completion/agent result 표시가 바뀌지 않는다.
- [ ] follow-up request 작성은 task detail로 안내하고 pane에 form을 복제하지 않는다.

### 13.3 2영역 UI

- [ ] availability와 dispatch/result evidence가 별도 badge/field다.
- [ ] agent별 active/review/blocked count와 latest evidence_at을 표시한다.
- [ ] dispatch-only agent copy가 `전송 확인 · 결과 대기`이며 완료 표현이 없다.
- [ ] unlinked sidecar/alias는 unknown과 limitation으로 표시된다.
- [ ] row action은 관련 task/detail navigation만 제공한다.
- [ ] agent row에서 dispatch/retry/cancel/assign control이 없다.

### 13.4 3영역 UI

- [ ] explicit project identity만 실제 project row로 표시한다.
- [ ] identity 없는 task는 `프로젝트 미지정`으로 분리한다.
- [ ] 기본 row는 project name/id, active/done/unknown, latest evidence만 표시한다.
- [ ] task 여러 개면 read-only selector를 거쳐 detail로 간다.
- [ ] title 유사도/id prefix/폴더명으로 project를 추론하지 않는다.
- [ ] project row에 write control이 없다.

### 13.5 4영역 UI

- [ ] blocker, decision, unknown, reviewable 순으로 기본 정렬된다.
- [ ] 각 row에 question, target, scope, evidence, time, limitation, recommended action이 있다.
- [ ] active hold가 blocker로 표시된다.
- [ ] pending instruction이 decision으로 표시된다.
- [ ] exact artifact/verification evidence가 reviewable로 표시된다.
- [ ] malformed/unlinked/conflict가 unknown으로 표시된다.
- [ ] load 실패를 empty success로 표시하지 않는다.
- [ ] row CTA는 detail/evidence navigation만 수행한다.

### 13.6 API / Projection

- [ ] `/api/dashboard-console`이 schema v2, snapshot id, generated_at, 네 pane key를 반환한다.
- [ ] 모든 pane은 같은 `load_tasks()` snapshot에서 생성된다.
- [ ] projection은 input raw task를 mutate하지 않는다.
- [ ] missing/null/unknown/conflict가 test fixture에서 구분된다.
- [ ] agent 집계가 task 전체 status를 모든 관련 agent에 복제하지 않는다.
- [ ] project identity가 없는 task를 임의 project에 귀속하지 않는다.
- [ ] Mission dedupe가 raw evidence를 삭제하지 않는다.
- [ ] pane별 projection failure가 다른 pane read를 막지 않는다.

### 13.7 Instruction API

- [ ] same-origin, JSON, payload size, capability, actor를 검증한다.
- [ ] Idempotency-Key retry가 instruction record를 중복 생성하지 않는다.
- [ ] 생성 record가 instruction id/version/target/submitted_at/submitted_by/state를 가진다.
- [ ] 성공 response가 `parent_changed=false`를 반환한다.
- [ ] submit 전후 parent task/stage/gate/final review/dispatch raw가 동일하다.
- [ ] HTML/script text가 실행되지 않고 text로 escape된다.

### 13.8 v1.1 회귀

- [ ] task detail 첫 section이 Final Deliverable이다.
- [ ] unbound/ambiguous final artifact를 자동 선택하지 않는다.
- [ ] viewer가 pane/task detail보다 높은 top layer다.
- [ ] Escape 1회당 topmost layer 1개만 닫힌다.
- [ ] viewer/task detail close 후 focus가 올바른 trigger로 돌아간다.
- [ ] iframe sandbox/referrer policy/file CSP가 유지된다.
- [ ] follow-up request는 detail-only이며 parent raw를 바꾸지 않는다.
- [ ] 기존 card/detail write boundary tests가 통과한다.

### 13.9 QA matrix

필수 fixture:

1. configured agent, dispatch 없음
2. dispatch confirmed, result 없음
3. partial results
4. result received, stage in progress
5. failed dispatch/result
6. unknown worker alias/unlinked envelope
7. project_ref 있음, mixed active/done
8. project_ref 없음
9. active hold + reviewable artifact 동시 존재
10. pending instruction
11. malformed instruction state
12. stale sync/watchdog + newer raw task
13. confirmed final deliverable
14. ambiguous/unbound final deliverable
15. pane API 일부 projection failure
16. instruction idempotent retry
17. instruction 403/413/415/500
18. 390/768/1440 responsive
19. keyboard resize/focus/Escape
20. 100-task/30-agent performance fixture

Browser 목표:

- Chromium
- Firefox
- WebKit
- keyboard-only
- 200% zoom
- reduced motion

---

## 14. 개발 Slice

### Slice 0 — Contract와 fixture 고정

범위:

- 현재 v1.1 projection/final/viewer/follow-up test baseline 기록
- 4-pane schema v2 fixture 작성
- 현재 static `agent surface absent` contract를 교체할 테스트를 먼저 추가
- instruction non-mutation fixture

완료 조건:

- 새 test가 현행 UI/API에서 의도대로 실패한다.
- 기존 변경 사항과 v1.2 변경 범위를 분리할 수 있다.

### Slice 1 — Additive console projection/API

범위:

- `project_console_snapshot()` 또는 동등한 pure projection
- agent execution 집계 교정
- project explicit binding/unassigned projection
- Mission classification/dedupe
- `/api/dashboard-console`

완료 조건:

- pure projection non-mutation test
- 같은 snapshot 참조 test
- 20개 핵심 상태 fixture 통과
- 기존 endpoint 회귀 없음

### Slice 2 — 4-pane shell과 responsive foundation

범위:

- semantic pane landmarks
- desktop 2×2
- tablet/mobile priority stack
- pane scroll/minimum/resize/reset
- global snapshot/freshness chrome

완료 조건:

- 390/768/1440 layout contract
- keyboard separator
- Mission과 instruction 접근성
- no workflow mutation on resize

### Slice 3 — Agents / Projects pane

범위:

- agent row/status axes/filter/detail link
- minimal project rows/unassigned/task selector
- empty/error/unknown states

완료 조건:

- dispatch-only false completion 0건
- project inference 0건
- pane row write control 0개

### Slice 4 — Mission Control migration

범위:

- counts + queue + reviewable/unknown 통합
- priority/dedupe/recommended next action
- 기존 Active Work Board/Recent Audit 첫 화면 중복 제거
- task detail audit 보존

완료 조건:

- blocker/decision/unknown/reviewable fixture 100%
- load failure가 empty success로 보이지 않음
- navigation-only CTA

### Slice 5 — PM instruction surface

범위:

- current context/thread/target
- new brief flow 이전
- append-only instruction store/API/capability/idempotency
- pending PM review timeline
- follow-up detail link

완료 조건:

- parent non-mutation 100%
- retry duplicate 0건
- unsafe text execution 0건
- permission disabled UX

### Slice 6 — Integration, browser QA, rollout

범위:

- task detail/viewer/follow-up 회귀
- focus/layer/scroll lock
- performance
- feature flag와 rollback
- operator documentation

완료 조건:

- full automated suite 통과
- Chromium/Firefox/WebKit 핵심 flow 통과
- 기존 v1.1 화면으로 독립 rollback 가능

### 권고 배포 방식

- `dashboard_console_v2` feature flag
- projection/API를 먼저 배포하고 기존 UI에서 미사용 상태로 검증
- shell은 flag 아래에서 전환
- instruction write는 read console과 별도 capability flag
- rollback 시 v1.1 UI로 돌아가되 신규 instruction records는 보존

---

## 15. 리스크, 완화, 가정, 의존성

### 15.1 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| 4-pane 정보 과밀 | scan 속도 저하 | pane별 질문 1개, row 필드 cap, detail 이동 |
| 작은 pane에서 Mission 매몰 | 핵심 판단 누락 | minimum size, responsive 4→1 우선 |
| instruction을 실행 명령으로 오해 | 무단 상태 변경 | pending PM review, append-only, non-mutation test |
| agent 집계 오탐 | 완료/가용성 오판 | stage exact evidence 기반 재집계 |
| project identity 부재 | 잘못된 grouping | explicit binding only, unassigned bucket |
| 여러 endpoint 시점 불일치 | pane 간 모순 | 단일 console snapshot endpoint |
| 새 grid stacking context | viewer 가림 | viewer shell 밖 top-layer, browser test |
| current working tree의 미검증 변경과 혼합 | rollback 어려움 | feature flag, slice/commit 분리, baseline test |
| localStorage layout 손상 | pane 접근 불가 | clamp, schema key, reset |
| 100+ tasks 성능 | 초기 렌더 지연 | compact payload, cap/virtualize, lazy detail |

### 15.2 가정

- **가정 A:** v1.2는 현재 Python server + vanilla HTML/CSS/JS 구조를 유지한다.
- **가정 B:** Dashboard는 인증된 단일 사용자 로컬 환경이 기본이지만, write capability를 서버에서 검증한다.
- **가정 C:** 안정적인 project registry는 아직 없으므로 첫 slice에서 `unassigned`가 다수일 수 있다.
- **가정 D:** PM conversation context가 항상 복구되지는 않으므로 missing 상태를 지원한다.
- **가정 E:** 기존 task detail scoped controls의 정책 자체는 이번 범위에서 바꾸지 않는다.
- **가정 F:** 현재 uncommitted v1.1 코드와 PRD는 별도 review 대상이며 v1.2 개발은 baseline 확정 후 시작한다.

### 15.3 의존성

- Designer: Monitor + Command/Inspect 정보 계층, pane visual system, wireframe, interaction state, responsive guidance
- Developer: projection/API/store/layout/focus 구현
- Verifier: PRD 대비 intended-vs-implemented gap, authority/write boundary review
- QA: state fixture, browser, accessibility, performance, v1.1 regression
- PM: instruction accept/reject 운영 규칙과 project identity source 결정

### 15.4 열린 질문

1. canonical project registry를 새 파일로 둘지 raw task `project_ref`를 확장할지 PM/Developer가 결정해야 한다.
2. additional instruction accept/reject를 어떤 PM 운영 surface에서 처리할지 정해야 한다. v1.2 pane에는 넣지 않는다.
3. pane resize persistence를 browser localStorage로 한정할지 사용자 profile preference로 승격할지 결정해야 한다. 기본은 localStorage다.
4. `new_task_brief`는 현행처럼 queued task를 즉시 생성할지, instruction처럼 PM review 후 생성할지 별도 정책 결정이 필요하다. 이번 PRD는 기존 explicit submit contract를 보존한다.
5. Mission Control deadline/SLA source가 없다. 추론하지 않고 향후 explicit policy가 생길 때만 정렬에 반영한다.

---

## 16. 권고 후속 카드

### DESIGN-V12-1 — 4사분면 Monitor + Command/Inspect 콘솔 디자인

- Assignee: `designer`
- 산출물:
  - 1440px 2×2 wireframe
  - 768px/390px priority stack
  - pane header/row/status visual system
  - divider resize와 keyboard interaction
  - Mission priority/empty/error/stale states
  - instruction composer/pending review states
  - task detail/viewer layer integration guidance
- Acceptance:
  - 4와 1이 작은 화면에서 묻히지 않음
  - availability/execution 상태를 색 하나로 합치지 않음
  - pane row write control 없음

### DEV-V12-1 — Console projection/API와 instruction store

- Assignee: `developer`
- Dependency: PLAN-V12-1, DESIGN-V12-1의 data density guidance
- 산출물:
  - console schema v2
  - agent/project/mission projection
  - append-only instruction API/capability/idempotency
  - fixture/unit/server tests
- Acceptance:
  - raw non-mutation
  - same snapshot
  - agent/project false inference 0건
  - instruction parent_changed=false

### DEV-V12-2 — 4-pane shell과 integration

- Assignee: `developer`
- Dependency: DEV-V12-1, DESIGN-V12-1
- 산출물:
  - responsive 4-pane UI
  - resize/reset/focus
  - pane renderers
  - task detail/viewer/follow-up integration
- Acceptance:
  - UI AC 전체
  - mutation control boundary
  - v1.1 static contract 교체

### VERIFY-V12-1 — Intended vs Implemented / 권한 경계 검토

- Assignee: `verifier`
- Dependency: DEV-V12-1, DEV-V12-2
- 검토:
  - PRD 상태 의미 대 코드
  - instruction non-mutation
  - pane row read-only
  - project/agent false inference
  - final/viewer/follow-up 회귀

### QA-V12-1 — 4사분면 콘솔 browser acceptance

- Assignee: `qa`
- Dependency: VERIFY-V12-1 또는 수정 반영 build
- 검증:
  - 20개 fixture
  - Chromium/Firefox/WebKit
  - 390/768/1440, 200% zoom
  - keyboard resize/focus/Escape
  - 100-task/30-agent performance
  - feature flag rollback

### PM-V12-1 — Project identity와 instruction triage 운영 결정

- Assignee: `pm`
- 결정:
  - project registry vs raw `project_ref`
  - instruction accept/reject 처리 surface
  - new brief 생성 시점 정책
  - SLA/deadline source 도입 여부

---

## 17. 구현 근거 메모

이 PRD는 다음 현행 구현을 기준으로 작성했다.

- `operations_dashboard/index.html:25-78` — Mission/Queue/Board/Artifacts/Audit의 현재 세로 IA
- `operations_dashboard/index.html:82-223` — brief, artifact viewer, task detail layer
- `operations_dashboard/app.js:390-415` — Mission counts와 Decision Queue
- `operations_dashboard/app.js:417-438` — Reviewable Artifacts
- `operations_dashboard/app.js:633-766` — task card/board와 navigation action
- `operations_dashboard/app.js:1118-1139` — 여러 endpoint의 병렬 snapshot load
- `operations_dashboard/app.js:1517-1533` — follow-up idempotency와 detail history
- `operations_dashboard_server.py:422-445` — worker availability source
- `operations_dashboard_server.py:753-808` — task view와 additive dashboard projection
- `operations_dashboard_server.py:811-965` — 현재 agent summary의 task-level 집계
- `operations_dashboard_server.py:968-1000` — overview/agents/operations evidence
- `operations_dashboard_server.py:1392-1424` — read endpoints
- `operations_dashboard_server.py:1493-1511` — follow-up same-origin/idempotent write
- `operations_dashboard_server.py:1549-1570` — 기존 live-note/final/gate write endpoints
- `operations_dashboard_projection.py:520-554` — progress와 agent execution evidence
- `operations_dashboard_projection.py:557-636` — decision queue와 task projection
- `operations_dashboard_projection.py:639-651` — Dashboard counts
- `tests/test_dashboard_static_contract.py:48-51` — v1.2에서 교체가 필요한 agent surface absent contract
- `tests/test_dashboard_static_contract.py:215-234` — viewer top-layer/security contract
- `tests/test_dashboard_projection.py:75-130` — dispatch/result/stage/verification 분리 fixture

---

## 18. Acceptance Criteria 충족 체크

Task 요구 대비:

- [x] 네 영역을 목적·표시 데이터·허용 action·권한 경계로 구분
- [x] 1=좌상, 2=우상, 3=좌하, 4=우하 desktop IA 정의
- [x] Mission Control 중요도와 responsive 우선순위 정의
- [x] raw canonical/projection/non-mutation 원칙 유지
- [x] task/agent/project/mission/instruction 데이터 매핑 정의
- [x] v1.1 state/projection/final artifact/viewer/follow-up 충돌·중복 명시
- [x] UI/API/test acceptance criteria 제공
- [x] 개발 slice와 독립 rollout/rollback 정의
- [x] 리스크·가정·의존성·열린 질문 명시
- [x] Designer/Developer/Reviewer/QA/PM 후속 카드 명세 제공

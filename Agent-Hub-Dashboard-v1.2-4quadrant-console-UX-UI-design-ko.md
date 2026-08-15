# Agent Hub Dashboard v1.2 — 4사분면 운영 콘솔 UX/UI 디자인 명세

- 문서 성격: Designer handoff · Monitor + Command/Inspect 콘솔 기준
- 제품 범위: Raphael Agent Hub Dashboard-only
- 기준 구현: `operations_dashboard/index.html`, `styles.css`, `app.js`, `operations_dashboard_projection.py`
- 선행 보존 원칙: v1.1 raw canonical 상태, Final Deliverable 우선 영역, artifact viewer 최상위 레이어, detail-only follow-up intake

## 크리에이티브 요약

추천 방향은 **Warm Evidence Console**이다. 기존 Warm Brief Command의 크림 배경·부드러운 라운드·차분한 블루/웜 포인트는 유지하되, 긴 세로 보드를 네 개의 명확한 작업 창으로 재구성한다. 화면의 첫 인상은 ‘무엇을 클릭할까’가 아니라 **‘지금 어디에 판단과 주의가 필요한가’**여야 한다.

핵심 태도는 다음 한 줄로 정리한다.

> 부드럽게 보이되, 증거는 단단하게 읽힌다.

---

## 1. 설계 목적과 정보 계층

### 1.1 사용자가 10초 안에 얻어야 하는 답

1. 지금 PM이 확인하거나 결정할 일은 무엇인가? (4영역 Mission Control)
2. 현재 대화/지시는 어떤 task·프로젝트에 연결되며, PM 검토 전인가? (1영역)
3. 어느 agent가 실제로 결과를 냈고, 어느 agent는 단지 dispatch만 확인됐는가? (2영역)
4. 프로젝트 전체는 진행 중인지/완료인지, 더 깊은 task 맥락은 어디서 보는가? (3영역)

### 1.2 시선 우선순위

1. **Mission Control의 판단 항목** — blocker, decision, reviewable, unknown
2. **PM Conversation / Instruction의 최근 지시와 PM review 상태**
3. **Agent evidence** — result received와 dispatch confirmed의 분리
4. **Projects의 맥락 연결**
5. 보조 메타데이터·시간·raw detail disclosure

Mission Control은 기본 위치가 우하단이어도, 위험 상태가 있을 때는 배지·좌측 상단 priority rail·키보드 진입 순서로 가장 먼저 도달 가능해야 한다. 중요도를 물리적인 카드 면적만으로 해결하지 않는다.

---

## 2. 추천 콘셉트와 비주얼 시스템

### 2.1 추천: Warm Evidence Console

- **무드:** warm, calm, accountable, technical without being cold
- **레이아웃 인상:** 네 개의 독립된 관찰 창이 하나의 운영 테이블 위에 놓인 느낌
- **기존 UI 계승:** `--bg`, `--panel`, `--border`, `--accent`, `--warm`, `--success`, `--warn`, `--danger`, `--violet` 토큰과 22–30px 라운드, 가벼운 그림자를 유지한다.
- **신규 시각 원칙:** 색은 성과의 축약이 아니라 상태 종류를 구분하는 보조 수단이다. 모든 badge는 상태 텍스트·근거 시각 또는 근거 출처를 동반한다.

### 2.2 토큰 적용

| 용도 | 기존 토큰 / 처리 | 의미 |
|---|---|---|
| Canvas | `--bg`, `--bg-cream` | 긴 운영 화면에서도 눈부심을 줄이는 따뜻한 바탕 |
| Pane | `--panel`, 1px `--border`, `--radius-xl` | 네 영역을 독립된 책임 단위로 분리 |
| PM / instruction | `--accent-soft`, `--accent` | 입력 가능한 명령 경로. 실제 상태 변경 성공을 의미하지 않음 |
| Result received | `--success-soft`, `--success` + `결과 도착` 텍스트 | result envelope/report 수신 사실 |
| Dispatch confirmed | `--warn-soft`, `--warn` + `전송 확인` 텍스트 | 실행 완료가 아닌 dispatch 사실 |
| Blocked / failed | `--danger-soft`, `--danger` + reason | 조치가 필요한 실패·보류 |
| Reviewable | `--violet-soft`, `--violet` | 검토 가능하나 최종 승인/완료가 아님 |
| Unknown / stale | neutral/warn surface + `알 수 없음` 또는 `오래된 관찰` | 빈칸을 성공처럼 보이지 않게 처리 |

### 2.3 타이포그래피와 밀도

- Pane kicker: 11–12px uppercase, letter-spacing 0.10em. 예: `01 · PM CONVERSATION`.
- Pane title: 20–24px, 800 weight. 현재 `.section-head h2`보다 더 큰 hero는 불필요하다.
- Key decision/question: 15–16px, 800 weight, 2줄 clamp.
- Evidence/meta: 11–12px, `--muted`; ID와 timestamp는 tabular-nums 사용 권장.
- 기본 pane 내부 gap 12px, section gap 18px, 라인 높이 1.45–1.6. 한 pane에서 동시에 3종 이상의 강조색을 쓰지 않는다.

### 2.4 지양할 표현

- dispatch 성공을 녹색 완료 체크로 표기
- 자유 텍스트에서 추론한 `승인됨`, `완료됨`, `성공` badge
- 상시 노출되는 approve/retry/dispatch/gate override 버튼
- Projects pane에 task timeline 전체를 다시 렌더링
- Mission Control의 urgency를 단순한 빨간 수치만으로 표현

---

## 3. 데스크톱 2×2 레이아웃

### 3.1 전체 구조

Viewport 1280px 이상에서 `console-grid`는 12-column CSS Grid이며 두 행의 최소 높이를 유지한다. 첫 행은 command/inspect 맥락, 둘째 행은 operating decision 맥락이다.

```text
┌───────────────────────────────────────┬───────────────────────────────────────┐
│ 01 PM CONVERSATION / INSTRUCTION      │ 02 AGENTS                             │
│ 현재 대화 · 최근 지시 · PM review      │ 구성/실행/결과의 근거 분리             │
│ [최근 instruction] [PM review 대기]    │ [agent row] [agent row] [agent row]   │
│ [instruction thread]                  │ [상태 범례]                            │
│ [지시 작성] → detail-only intake      │ [선택 시 읽기 전용 작업 상세]          │
├───────────────────────────────────────┼───────────────────────────────────────┤
│ 03 PROJECTS                            │ 04 MISSION CONTROL                    │
│ 진행 중 / 완료 프로젝트의 낮은 밀도     │ 지금 판단할 일 · 근거 · 다음 조치       │
│ [project] 진행 중  3 tasks             │ [BLOCKER / DECISION]                  │
│ [project] 완료    8 tasks              │ [REVIEWABLE] [UNKNOWN]                │
│ [선택 → task detail/context]           │ [상세에서 검토] (읽기 전용 CTA)         │
└───────────────────────────────────────┴───────────────────────────────────────┘
```

### 3.2 권장 크기

- Shell: 기존 max-width 1480px 유지, desktop padding 22–28px.
- **1440px 기준 기본 split:** 열 `50:50`, 행 `46:54`. CSS 변수는 `--console-left: 50%`, `--console-top: 46%`로 시작하며 4영역은 3영역보다 작아지지 않는다.
- Grid: `grid-template-columns: minmax(360px, var(--console-left)) minmax(360px, 1fr)` 및 동일 원리의 두 행. 1440px에서 실제 권장 pane 폭은 약 684–706px, 상단 약 410px, 하단 약 480px다.
- Desktop pane min-height: 1영역 280px, 2영역 240px, 3영역 220px, **4영역 280px**. 하단 행 최소값은 4영역의 280px을 보장한다.
- 콘텐츠가 길면 pane body만 `overflow:auto`로 스크롤한다. pane header와 Mission Control top 3 rows, 1영역 composer 진입점은 해당 pane의 첫 화면에 남긴다. 전체 page scroll이 pane 접근 순서를 결정하지 않는다.
- Resize는 v1.2의 필수 interaction이다. 네이티브 `resize:both`는 사용하지 않고, 열 divider 1개와 행 divider 1개만 제공한다. 값은 localStorage preference일 뿐 workflow write가 아니다.
- Pane header는 기본 sticky가 아니다. 목록이 pane body 높이를 넘는 Agents/Mission에 한해 header/summary strip을 pane 내부에서 sticky로 유지할 수 있다.

### 3.3 Divider resize / reset contract

| 대상 | Pointer | Keyboard | 범위와 보호 규칙 |
|---|---|---|---|
| 세로 divider | 12px hit area를 drag | `←`/`→` 16px, `Shift+←/→` 48px | 각 열 최소 360px. 4영역 열 폭이 360px 아래가 되면 clamp. |
| 가로 divider | 12px hit area를 drag | `↑`/`↓` 16px, `Shift+↑/↓` 48px | 1영역/4영역 최소 280px, 2영역 240px, 3영역 220px. 4영역은 3영역보다 낮아지지 않게 clamp. |
| Reset layout | global ghost action | divider focus 중 `Home` 또는 Reset 버튼 `Enter/Space` | 50:50 / 46:54로 복귀, `console-layout-v2:{tier}` 값 삭제 후 성공 toast. |

- 각 divider는 실제 `<button>`이 아니라 `role="separator"`, 적절한 `aria-orientation`, `aria-valuemin/max/now`, `aria-label`을 갖는 focusable control이다. 드래그 중에는 `aria-valuetext="왼쪽 영역 50%"`처럼 현재 값을 갱신한다.
- pointer capture를 사용해 pane 밖에서도 drag가 끊기지 않게 하고, pointerup/cancel 시에만 localStorage에 저장한다. 저장 실패·손상값·viewport 변경은 기본값 또는 clamp로 안전 복귀한다.
- resize 중 text selection을 막고 cursor를 `col-resize`/`row-resize`로 바꾸되, `prefers-reduced-motion`에서는 transition을 두지 않는다. keyboard focus는 resize 후 divider에 남는다.
- 1199px 이하에서는 divider를 렌더하지 않고 saved desktop 값도 적용하지 않는다. `Reset layout`은 숨기지 않되 `현재 화면에서는 기본 레이아웃 사용 중`으로 비활성/설명 처리할 수 있다.

### 3.4 전역 header 축소

현재 hero는 한 줄로 압축한다.

- 좌측: `Raphael Agent Hub` + `Operations Console` kicker
- 중앙 또는 하단: `raw evidence를 읽기 전용으로 표시합니다.`
- 우측: `업무 지시 작성`만 primary. `대기 중인 일 보내기`는 dashboard-wide mutation이므로 이 v1.2 기본 화면에서는 숨기거나 detail/intake 흐름 밖의 별도 확인 단계를 거친다.
- 새로고침은 icon + tooltip 또는 ghost action.

이는 4개 pane의 작업 맥락을 header보다 먼저 읽게 한다.

---

## 4. 영역별 wireframe, 데이터, 권한 경계

## 4.1 1영역 — PM Conversation / Instruction

### 목적

Raphael님과 PM의 **현재 맥락, 이미 작성된 지시, PM 재검토 상태**를 묶되, 대화 문장이 task/stage/승인/agent 성공을 바꾸거나 암시하지 않도록 한다.

### Pane 구성

```text
01 · PM CONVERSATION
현재 지시와 PM 맥락
[ PM review 대기 2 ] [ 마지막 기록 14:22 · source: instruction ]
────────────────────────────────────────
최근 지시
“4사분면 운영 콘솔의 …”
대상: T-20260730-003 · Agent Hub Dashboard
상태: PM 재검토 대기 · 기록 14:22
[업무 상세 보기]
────────────────────────────────────────
대화 맥락 (최근 3개, 접기 가능)
Raphael  …
PM       …
────────────────────────────────────────
[ + 지시 작성 ]  ← 허용된 PM 작성 flow 진입점
```

### 표시 데이터

- 최근 instruction: `task_id`, 제목/outcome, 연결 project, 기록 시각, source label, `pending_pm_review` 여부.
- conversation은 display-only transcript이며 role과 기록 순서를 명시한다.
- 요청이 task에 연결되지 않았다면 `대상 task 확인 불가`로 보이고 일반 task 상태와 시각적으로 결합하지 않는다.
- `follow_up_summary.pending_count`는 존재할 때만 작은 neutral count로 표시한다. count가 approval이나 실행을 뜻하지 않음을 부연한다.

### 허용 액션

- `업무 상세 보기` → 기존 `openTaskDetail()`.
- `지시 작성` → 기존 PM brief modal/허용된 detail-only intake. 새 지시의 저장 성공도 task 완료/승인 표시는 금지.
- transcript expand/collapse.

### 금지 액션

- task stage 변경, dispatch, PM approval, final review override, gate override.
- free text parsing으로 agent/result/status badge 생성.

### 상태 표현

- **pending PM review:** violet/neutral badge + `PM 재검토 대기`.
- **unlinked:** muted badge + `대상 연결 확인 필요`.
- **no instruction:** empty state `표시할 지시 기록 없음` + 지시 작성 CTA. ‘모든 일이 완료’ 같은 빈 상태 문구 금지.

### Composer state contract

| UI state | 보이는 요소 | Primary action / 결과 | 절대 암시하지 않을 것 |
|---|---|---|---|
| local draft | mode toggle, target summary, textarea, `로컬 초안` | 명시적 `지시 기록` | 저장·승인·실행 |
| target 미연결 | `대상 없음 · 새 업무 맥락` 및 target picker | 새 brief 또는 unlinked instruction으로 기록 | 임의 task 연결 |
| capability loading/denied | disabled submit, 이유/재시도 | draft는 유지 | permission 오류를 제출 성공으로 보이기 |
| submitting | submit은 disabled, idempotency 유지, `기록 중` | duplicate submit 방지 | dispatch 진행 |
| submitted pending review | instruction id/version/time + `PM 재검토 대기` | `기록 보기` 또는 local dismiss | 승인·task 생성·agent 배정 |
| failed/timeout | error copy + 보존된 draft + retry | 같은 idempotency key로 재시도 | 이력 유실 또는 parent 상태 변경 |

- composer submit 직전/직후 microcopy는 고정한다: `이 지시는 즉시 실행·승인·완료 처리가 아닙니다.`
- additional instruction과 new brief를 segmented mode로 구분하되, follow-up는 mode로 넣지 않는다. `산출물 보완 요청은 업무 상세에서 작성`은 task detail로 가는 보조 link다.
- pending record는 새 메시지처럼 대화 맨 아래에 놓되, 수신/읽음/실행 완료처럼 보이는 체크 아이콘을 쓰지 않는다.

## 4.2 2영역 — Agents

### 목적

Agent List를 단순 online roster가 아닌, **설정·전송·결과·실패의 관찰 근거를 분리한 실행 관제 목록**으로 보인다.

### Pane 구성

```text
02 · AGENTS                                      [상태 범례]
현재 작업과 근거
────────────────────────────────────────────────────────────
● writer-co       결과 도착       현재 1 · 검토 대기 1
  writing · result envelope 14:20 · report 연결됨
────────────────────────────────────────────────────────────
◐ verify-co       전송 확인       현재 1 · 검토 대기 0
  verification · dispatch 14:18 · 결과 수신 확인 불가
────────────────────────────────────────────────────────────
! claude-code     실패/보류        현재 0
  dispatch_blocked · reason: host 미설정 · 13:40
────────────────────────────────────────────────────────────
? agent-x         알 수 없음      구성/최근 상태 근거 없음
```

### 상태 taxonomy 및 표현 규칙

| 표현 | raw/evidence 기준 | 시각 처리 | 절대 해석 금지 |
|---|---|---|---|
| `준비됨` | configured/available | neutral-blue | 작업이 배정/실행됨 |
| `전송 확인` | dispatch confirmed/dispatched | amber | 결과 수신/작업 완료 |
| `결과 도착` | exact active envelope + report가 안전하게 연결됨 | green | stage/전체 task 완료 |
| `실패/보류` | failed/blocked/error 근거 | coral + reason | 영구 실패/복구 불가 |
| `알 수 없음` | missing, malformed, unlinked, stale | neutral/warn | 비활성/성공 |

### 표시 데이터

- API 후보: 기존 `/api/agents`, `/api/workers`, `/api/tasks`의 read model. 개발은 모든 row를 raw task projection에서 보수적으로 집계한다.
- row 최소 필드: agent name, latest evidence class, current task count, pending review count, stage/derived task id(있을 때), evidence time, source label, limitation/reason.
- current task count와 review pending count는 task id dedupe 후 산출한다. result files 수, historical attempt 수를 task 수로 세지 않는다.
- agent의 최근 상태가 stale/unknown이면 그 이유를 row 2행에 표시한다.

### 허용 액션

- row click/keyboard Enter → 해당 agent가 귀속된 task detail의 `Agent execution / attempts` anchor를 열거나 focus.
- `전체 agent 보기`는 읽기 전용 목록 expansion.

### 금지 액션

- agent card에서 dispatch/retry/approve/worker config write.
- `전송 확인` row에 완료 체크/green full surface.

## 4.3 3영역 — Projects

### 목적

프로젝트를 task backlog로 대체하지 않고, **진행 중/완료의 맥락 전환점**으로 사용한다.

### Pane 구성

```text
03 · PROJECTS
진행 중인 맥락
────────────────────────────────────────
● Agent Hub Dashboard              진행 중
  task 4 · 판단 필요 2 · 최근 근거 14:22
  [관련 task 보기]
────────────────────────────────────────
○ Operations Foundation             완료
  task 8 · 마지막 canonical event 09:16
  [관련 task 보기]
────────────────────────────────────────
완료 프로젝트 6개 보기 ▾
```

### 표시 데이터

- default는 `진행 중`과 `완료` 그룹만 보이며, project별 task 수와 Mission Control 관련 개수는 읽기 전용 요약이다.
- status가 없는 project는 `상태 확인 불가`; 완료 그룹으로 자동 이동 금지.
- 현재 API에 project raw model이 없다면, task의 explicit project field만 집계한다. title/path/free text로 project를 추론하지 않는다.
- 한 project row의 상세 task는 최대 1개 preview만; 선택 후 task detail/context로 연결한다.

### 허용 액션

- project row 또는 `관련 task 보기` → task filter/context panel 또는 task detail. URL state는 허용하되 raw data 변경은 없다.
- completed group expand/collapse.

### 금지 액션

- 프로젝트 card 내 task 생성, priority 변경, dispatch, approval, project 상태 편집.

## 4.4 4영역 — Mission Control

### 목적

기존 `지금 판단할 일`의 권한·우선순위·근거 보존을 더 빠른 조치 판단 구조로 강화한다. 이 pane은 대시보드의 **decision desk**이며, execution control이 아니다.

### Pane 구성

```text
04 · MISSION CONTROL                     4 판단 필요
지금 판단할 일
[ Blocker 1 ] [ Decision 1 ] [ Reviewable 1 ] [ Unknown 1 ]
────────────────────────────────────────────────────────────
! BLOCKER · T-…
  verification dispatch가 보류됨
  근거: dispatch_blocked · 14:18 · source: task raw
  다음 조치: 업무 상세에서 보류 사유 확인
  [업무 상세]
────────────────────────────────────────────────────────────
◇ REVIEWABLE · T-…
  결과는 도착했으나 final binding 확인 필요
  근거: verify result received · 14:20
  다음 조치: Final Deliverable과 검증 근거 확인
  [업무 상세]
```

### 우선순위와 정렬

1. blocker (`dispatch_blocked`, failed, active hold)
2. explicit decision/review 필요 (`needs_pm_review`, final review/authority evidence)
3. reviewable evidence (결과가 도착했으나 binding/판정 분리 필요)
4. unknown/stale/malformed

동일 class 안에서는 canonical event time 내림차순, time 부재는 마지막이다. `sync success`는 global observation이며 개별 task 완료보다 낮은 utility strip에만 둔다.

### 표시 데이터

- `dashboard_projection.decision_queue_item`, `progress.next_pm_action`, `audit_rows`, `operations_evidence`, `final_deliverable`, verification/follow-up summary를 사용한다.
- 각 item은 **분류 / task / 질문 또는 상태 / canonical 근거 / 근거 시각 / 권장 다음 조치**의 6요소를 갖는다.
- 권장 조치는 `업무 상세 보기`, `근거 확인`처럼 inspect-only 문구로 제한한다.
- `unknown`은 빈 상태가 아니라 우선순위 item으로 표시하되, 해결할 수 있는 확정 지시로 과장하지 않는다.

### 허용 액션

- 모든 item의 primary action은 동일한 `업무 상세 보기` 또는 읽기 전용 artifact/final deliverable inspect.
- count pill은 해당 class의 read-only filter로만 동작.

### 금지 액션

- approve, override, retry, dispatch, gate control, request accept/reject.
- `결과 도착`, `reviewable`을 `승인 완료` 또는 `전체 완료`로 축약.

---

## 5. interaction 및 접근성 상태

### 5.1 Pane 공통

- Pane title은 `h2`, list는 semantic list 또는 table-equivalent 구조를 사용한다.
- clickable row는 `<button>` 또는 `<a>`로 구현하고, `div` click-only를 사용하지 않는다.
- hover는 border/shadow 변화만; 상태 의미를 hover에 숨기지 않는다.
- focus-visible은 기존 accent 대비를 유지하며 2px outline을 제공한다.
- 모든 count pill은 색상 외 `Blocker 2`처럼 텍스트를 가진다.
- ID/filename은 `overflow-wrap:anywhere`; truncation 시 accessible full name을 `aria-label` 또는 title로 제공한다.

### 5.2 loading / empty / error / stale

| 상태 | pane 표현 |
|---|---|
| Loading | 2–3행 skeleton. 이전 데이터가 있으면 stale label과 함께 유지 |
| Empty | 해당 pane 목적에 맞는 empty copy. 예: `현재 판단할 raw 근거 없음` |
| API error | `표시 데이터를 불러오지 못했습니다` + 재시도(읽기 fetch) |
| Stale | `오래된 관찰 · 현재 raw 상태를 덮어쓰지 않음` |
| Unknown | `알 수 없음`과 결손/형식 오류의 근거를 함께 표시 |

### 5.3 모달 및 상세 연결 보존

- task detail은 기존 Final Deliverable을 body 첫 section으로 유지한다.
- artifact viewer는 `taskDetailModal`보다 항상 top-layer. existing `modalStack`, focus trap, Escape topmost-close, scroll lock ref-count를 보존한다.
- 콘솔 pane row가 artifact viewer를 직접 열 수 있는 경우도 같은 `openArtifactViewer/openDetail` coordinator만 사용한다.
- viewer close 후 focus는 원 pane row로 복귀하고, task detail이 남아 있으면 detail의 inert 상태를 복원한다.

---

## 6. 반응형 규칙

### Desktop ≥ 1280px

- 2×2 grid, 1=좌상 / 2=우상 / 3=좌하 / 4=우하.
- Mission Control에 active blocker/decision이 있으면 pane header에 `aria-live=polite` summary를 제공하되 상세 목록을 매 refresh마다 강제 announce하지 않는다.

### Tablet 768–1199px — priority stack

- **768px acceptance viewport의 기준 레이아웃은 1열 stack**이며 DOM과 visual order를 모두 **4 Mission Control → 1 PM Conversation/Instruction → 2 Agents → 3 Projects**로 둔다. 따라서 keyboard/reader 순서도 위험·지시 우선순위를 그대로 따른다.
- 화면 폭 1024–1199px에서만 충분한 높이가 확인되면 2열 보조 배치(첫 행 `4 | 1`, 둘째 행 `2 | 3`)를 허용한다. 이 경우에도 DOM order와 jump nav 순서는 4→1→2→3이다.
- sticky jump nav: `판단(4) · 지시(1) · Agents(2) · Projects(3)`. 각 link는 pane heading id로 이동하고, `scroll-margin-top`으로 header에 가리지 않게 한다. 현재 pane은 scrollspy로 `aria-current="location"`만 갱신한다.
- Mission Control은 top 3 items를 heading 직후 표시하고, Instruction composer CTA는 thread 길이와 무관하게 첫 1.5 viewport 안에 남긴다.
- Agents 목록은 5 rows 후 `더 보기`; Projects 완료 그룹은 접힘. resize divider는 제거하고 pane height는 content-aware로 전환한다.

### Mobile ≤ 767px — priority stack + quick navigation

- 1열 priority stack: **4 Mission Control → 1 PM Conversation/Instruction → 2 Agents → 3 Projects**.
- 상단 compact jump nav는 Tablet과 동일한 4개 anchor를 유지하고, horizontal scroll 대신 2×2 compact grid 또는 줄바꿈을 허용한다. 각 target은 44px 이상이다.
- Mission Control은 상단에 최대 3 items + `전체 판단 항목` expand. `전체 판단 항목`은 새 상태를 만들지 않는 local disclosure다.
- Instruction compose CTA는 view 첫 1.5 screen 내에 유지한다. thread가 있으면 최근 3개만 기본 노출하고 `대화 더 보기` 뒤에 나머지를 둔다.
- agents/project rows와 jump nav는 44px 이상 tap target. badge는 row 아래로 wrap 가능하며 ID는 `overflow-wrap:anywhere` 처리한다.
- task/artifact detail은 기존 full-height modal 원칙을 유지한다.

### Motion

- pane reposition/expand: 160–200ms ease, `prefers-reduced-motion: reduce`에서 animation 제거.
- blocked/unknown을 지속 pulse로 표현하지 않는다. in-progress만 기존의 약한 pulse를 허용한다.

---

## 7. 현재 v1.1과의 정합성 / 충돌 방지

| 기존 계약 | v1.2 UI 적용 |
|---|---|
| Raw task/stage/dispatch/result/verification/PM review는 canonical | 4 pane은 모두 additive projection이며 raw 상태를 write/override하지 않는다. |
| result received ≠ stage/task complete | Agents와 Mission Control에서 별도 label 및 색으로 분리한다. |
| PM review/meets + binding 부족 ≠ final approved | Mission Control은 `검토 기록 있음 · 대상 연결 확인 필요`로만 보인다. |
| Final Deliverable은 task detail 첫 section | 콘솔 어디에서도 Final Deliverable을 축약한 성공 선언으로 대체하지 않는다. 상세 진입 시 기존 첫 section을 사용한다. |
| artifact viewer top-layer/focus | pane 기반 artifact action도 기존 coordinator를 통과하고 modal stack을 보존한다. |
| follow-up request는 detail-only intake | 1·4영역은 pending count/상태만 read-only로 보이며 accept/dispatch UI를 두지 않는다. |
| cards are read-only | 모든 pane card/row는 inspect/filter/navigate만 가능하다. |
| sync/watchdog는 관찰 증거 | utility/evidence line으로 분리하며 stale snapshot이 task 상태를 덮어쓰지 않는다. |

---

## 8. Developer handoff — UI/API acceptance criteria

### 8.0 Component / state / focus contract

| Component | Required inputs / states | Allowed output | Focus contract |
|---|---|---|---|
| `ConsoleShell` | snapshot freshness, viewport tier, saved split | 4 pane landmarks, global refresh/reset, jump nav | tier change 시 현재 pane heading에 안전 복귀 |
| `ConsolePane` | id, number, title, purpose, summary, load state | header + body + pane-level empty/error/stale | landmark label과 `h2`가 keyboard heading navigation 대상 |
| `InstructionComposer` | mode, target, capability, draft, submit state | append-only record 또는 explicit brief flow | open 시 mode heading, submit 후 submitted record; error 시 textarea로 복귀 |
| `AgentEvidenceRow` | availability, dispatch, result, workload, limitation | task detail navigation | Enter/Space → task detail의 Agent execution anchor |
| `ProjectContextRow` | explicit identity, counts, status, limitation | read-only filter/selector/detail | selector 종료 후 row trigger 복귀 |
| `MissionItemRow` | kind, target, question, evidence, time, next inspect action | detail/evidence inspect | detail close 후 original row 복귀 |
| `PaneDivider` | orientation, split, min/max, tier | local layout preference만 변경 | Arrow/Shift+Arrow 조절 후 divider focus 유지 |
| `TaskDetail` / `ArtifactViewer` | existing v1.1 contracts | Final Deliverable → viewer inspect | viewer Escape → artifact trigger, detail Escape → pane row |

**행 상태 우선순위:** `error` → `stale/unknown` → evidence class → neutral empty. 즉 결과가 있어도 exact binding이 없으면 green success가 아니라 `알 수 없음`을 우선하고, failed/blocked evidence는 결과 수신보다 앞선다.

**DOM contract:** desktop의 visual order는 1→2→3→4로 유지하되, 768px 이하에서는 DOM 자체를 4→1→2→3으로 재정렬한다. CSS `order`만으로 시각 순서를 뒤집어 screen reader 순서가 달라지는 구현은 금지한다.

**row action contract:** 모든 pane row의 action은 단 하나의 inspect/navigation 경로만 제공한다. filter pill, disclosure, local expand는 예외지만 dispatch/approval/gate override/follow-up accept/reject write control을 row 안에 두지 않는다.

### 8.1 UI acceptance criteria

- [ ] Desktop 1280px 이상에서 1/2/3/4 영역이 좌상/우상/좌하/우하 2×2 grid로 보인다.
- [ ] 각 pane이 purpose, displayed data, allowed action, authority boundary를 pane-level copy 또는 affordance로 구분한다.
- [ ] 모든 card/row는 read-only inspect/filter/navigation만 제공하며 dispatch, approval, retry, gate override, follow-up approval control이 없다.
- [ ] `dispatch confirmed`와 `result received`는 서로 다른 label/surface를 사용하고 dispatch confirmed에 completed icon/success surface가 없다.
- [ ] Mission Control item은 category, task, evidence/source, evidence time, next inspect action을 모두 표시한다.
- [ ] 1영역의 free text/transcript는 raw status 변화의 근거로 표시되지 않으며 target task/project가 없으면 unlinked로 명시된다.
- [ ] 3영역 기본 뷰는 in-progress/completed 프로젝트와 최소 요약만 표시한다.
- [ ] task detail의 Final Deliverable 최상단 순서와 artifact viewer top-layer/focus return이 회귀하지 않는다.
- [ ] 768px 미만에서 Mission Control → Instruction → Agents → Projects 1열 순서가 유지된다.
- [ ] keyboard Tab, Enter/Space, Escape, visible focus, 44px mobile targets가 동작한다.
- [ ] divider는 1440px에서 pointer/keyboard resize, min-size clamp, localStorage fail-safe, Reset을 모두 지원하고 workflow API를 호출하지 않는다.
- [ ] 768px와 390px에서 jump nav가 `판단 → 지시 → Agents → Projects` 순으로 같은 heading target에 도달한다.
- [ ] 768px 이하에서 visual/DOM/focus 순서가 4→1→2→3으로 일치한다.

### 8.2 API/read-model acceptance criteria

- [ ] `/api/tasks`, `/api/agents`, `/api/workers`, `/api/overview`만으로 표시 가능한 값을 우선 사용하며, unavailable data는 fabricated aggregate 없이 `알 수 없음` 또는 `표시할 근거 없음`으로 처리한다.
- [ ] agent aggregate는 `current_task_count`, `pending_review_count`, `latest_evidence`, `evidence_at`, `source`, `limitation` 같은 additive view model로 제공하거나 클라이언트에서 같은 의미로 보수 집계한다.
- [ ] project aggregate는 explicit project relation이 있을 때만 생성한다. task title/free text/파일 경로로 관계를 추론하지 않는다.
- [ ] Mission Control은 existing `decision_queue_item`, `next_pm_action`, operations evidence/final deliverable/verification projection을 소비하되 raw canonical payload를 수정하지 않는다.
- [ ] timestamp parse 실패 시 원문과 timezone limitation을 표시하고 rendered time을 evidence time으로 사용하지 않는다.
- [ ] empty/malformed/stale API fixture가 500 없이 pane-level error/unknown state로 렌더링된다.

### 8.3 QA fixture / browser cases

- [ ] configured agent only, dispatch confirmed only, result received, failed/blocked, unknown의 5 row 상태를 한 화면에서 확인한다.
- [ ] dispatch confirmed인데 report/result 없는 fixture가 `전송 확인`, 완료가 아닌 것으로 보인다.
- [ ] result envelope + report가 있어도 stage `in_progress`인 fixture가 `결과 도착 · 단계 전이 대기`로 병기된다.
- [ ] PM review `meets` + artifact binding 없음 fixture가 final-approved copy 없이 표시된다.
- [ ] stale watchdog/sync fixture는 pane 상태를 raw task보다 우선하지 않는다.
- [ ] mobile 390px, tablet 768px, desktop 1440px screenshot/keyboard evidence를 남긴다.
- [ ] task detail에서 Final Deliverable CTA → viewer → Escape 순서가 viewer만 닫고 return focus가 유지됨을 확인한다.

### 8.4 PRD UI acceptance trace

| PRD acceptance cluster | 디자인 명세 대응 | 구현/QA 확인점 |
|---|---|---|
| 13.1 IA/Layout | §3 desktop wireframe·size, §3.3 divider, §6 responsive | 1440 2×2, 768/390 4→1→2→3, jump nav, min clamp/reset |
| 13.2 PM Instruction | §4.1 pane wireframe·Composer state contract | pending review, unlinked, draft preservation, non-mutation copy |
| 13.3 Agents | §4.2 taxonomy/row rules | availability·dispatch·result 분리, dispatch-only false completion 0건 |
| 13.4 Projects | §4.3 explicit identity/minimum density | no inferred project, unassigned/unknown, navigation-only row |
| 13.5 Mission Control | §4.4 priority/row system | blocker→decision→unknown→reviewable, 6-field evidence row, error≠empty |
| 13.8 v1.1 regression | §5.3, §7 | Final Deliverable first, viewer top-layer/Escape/focus, detail-only follow-up |
| 13.9 responsive/a11y fixture | §5, §6, §8.0–8.3 | 390/768/1440, keyboard separator, visible focus, 44px target, reduced motion |

이 표의 각 행은 개발 static/browser test 이름 또는 QA evidence 섹션으로 하나 이상 연결해야 한다. PRD 원문과 이 디자인 문서가 충돌하면 **PRD의 상태·권한 규칙이 우선**하고, visual density는 이 문서를 따른다.

---

## 9. 구현 순서와 리스크

### 권장 slice

1. **Structure:** `console-grid` markup/CSS와 DOM order; 기존 sections를 새 4 pane의 slot에 배치하되 rendering data는 그대로 유지.
2. **Mission Control:** 기존 decision queue/mission projection을 우하단 decision desk로 합성; global evidence는 compact utility strip.
3. **Agents/Projects:** missing-safe read models 및 empty/error states. project explicit relation이 없으면 layout만 준비하고 false grouping을 하지 않는다.
4. **Responsive & QA:** visual reorder, keyboard/modal regression, unknown/stale fixture browser evidence.

### 주요 리스크와 방어

- **리스크: source data가 agent/project overview에 불충분함.** → 새 status를 추론하지 않고 unknown/empty를 정직하게 렌더링한다.
- **리스크: console 밀도가 높아져 task detail과 중복됨.** → pane은 ‘판단/진입’만, raw audit·timeline·artifact evidence는 detail에 둔다.
- **리스크: command center 외형이 write 권한을 암시함.** → primary button은 instruction compose만; 모든 운영 row의 CTA를 `업무 상세`로 통일한다.
- **리스크: mobile에서 PM input이 밀림.** → 1열 시 4→1을 최상단 priority stack으로 고정한다.
- **리스크: 기존 modal stack 회귀.** → artifact viewer 신규 진입점도 named coordinator를 통과시키고 focus browser QA를 필수화한다.

---

## 10. Assumptions 및 다음 핸드오프

### Assumptions

- 기존 `/api/agents`, `/api/workers`, `/api/tasks`, `/api/overview`는 read-only display source로 유지된다.
- 프로젝트의 explicit canonical relation이 아직 없을 수 있으며, 이 경우 Projects pane은 `상태 확인 불가`를 보여도 괜찮다.
- 허용된 PM instruction 작성 flow는 현재 brief modal과 task-detail follow-up intake 계약을 보존한다.

### Handoff targets

- **Developer:** `index.html`/`styles.css`/`app.js`에 console grid 및 missing-safe view model 구현. `operations_dashboard_projection.py`에 필요한 additive aggregation만 추가.
- **Verifier/QA:** static contract, projection fixture, desktop/tablet/mobile browser, modal focus/stack regression 검증.
- **PM:** project relation/source schema의 canonical owner를 확정하고, slice 순서와 dashboard-wide auto-dispatch 노출 여부를 최종 판단.

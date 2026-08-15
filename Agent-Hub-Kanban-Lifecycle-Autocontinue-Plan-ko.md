---
title: Agent Hub Kanban lifecycle 자동 연속 진행·stale blocked 복구 계획
id: PLAN-OPS-1
status: implementation-ready
applies_to: Hermes Kanban default board, Agent Hub Dashboard v1.1/v1.2 workflow
snapshot_at: 2026-08-01
owner: HermesPM
---

# Agent Hub Kanban lifecycle 자동 연속 진행·stale blocked 복구 계획

## 0. 기획 요약

현재 정지의 주원인은 작업 실패가 아니라 `review-required`를 `blocked`로 표현하면서, 그 blocked developer를 reviewer 또는 downstream 작업의 parent로 연결한 그래프 모델이다. Dispatcher는 모든 parent가 `done`일 때만 child를 실행하므로 “리뷰가 필요해서 blocked → reviewer가 blocked parent를 기다림”이라는 순환 대기가 생긴다.

권고안은 다음 세 축이다.

1. **즉시 복구:** 원본 task/comment/run/event를 삭제하지 않고 잘못된 parent edge만 제거하며, 오래된 blocked 34건을 active 4건, superseded 16건, irrecoverable 2건, historical evidence 12건으로 분류한다.
2. **운영 계층:** PM이 active workflow registry와 review-ready handoff를 관리한다. Developer와 reviewer는 sibling이며 reviewer는 blocked developer를 parent로 갖지 않는다. PM gate만 reviewer를 promote하고 downstream은 최신 승인 reviewer에만 의존한다.
3. **제품 계층:** Hermes Kanban core에 `review_ready` 상태/typed dependency/atomic dependency replacement/supersession을 도입해 `blocked`를 코드 리뷰 대기 용도로 쓰지 않게 한다.

최우선 복구 대상은 현재 실제 chain을 막는 세 edge다.

- `t_1631cefc(blocked) → t_18fc1fe8(todo)`
- `t_4d067679(blocked) → t_a1b18044(todo)`
- `t_44e06f2c(blocked) → t_4382ece8(todo)`

첫 두 reviewer는 blocked parent edge를 제거하고 PM review-ready gate로 실행시킨다. v1.2는 backend 전용 `VERIFY-V12-1A`를 먼저 독립 실행해 승인된 reviewer를 만든 뒤 `DEV-V12-2`가 그 승인만 parent로 갖게 한다.

---

## 1. 범위와 성공 조건

### 1.1 목표

- 결과 도착 후 다음 reviewer/QA/deploy가 사람의 반복 재지시 없이 안전하게 이어진다.
- 코드 handoff와 코드 승인, downstream 실행을 서로 다른 사실로 기록한다.
- obsolete blocked parent 때문에 ready task가 영구 정지하지 않는다.
- monitor가 active workflow의 의미 있는 상태 변화만 알리고 Dashboard/service timeout을 프로젝트 실패로 오인하지 않는다.
- 원본 task body, comment, run, event, attachment는 삭제하지 않는다.

### 1.2 비목표

- 과거 evidence를 정리한다는 이유로 task row/comment/run/event를 물리 삭제하지 않는다.
- reviewer 없이 코드 변경을 자동 승인하지 않는다.
- free text만 보고 승인, 실패, terminal close를 추론하지 않는다.
- Dashboard v1.1/v1.2의 제품 기능을 이 계획에서 직접 구현하지 않는다.
- blocked 전체를 일괄 done으로 바꾸지 않는다.

### 1.3 정량 성공 조건

- `todo/running` task가 `blocked/archived` parent를 갖는 잘못된 edge: **0건**.
- active code handoff마다 독립 reviewer gate 존재: **100%**.
- downstream implementation/QA/commit/deploy의 승인 근거가 최신 PASS reviewer 하나로 수렴: **100%**.
- superseded dependency가 active child에 남는 경우: **0건**.
- monitor 첫 실행 알림: **0건(silent baseline)**.
- 같은 fingerprint의 반복 알림: 상태/결과/stage 변화 전까지 **0건**.
- terminal workflow close 이후 heartbeat/exception 반복 알림: **0건**.
- migration 중 task/comment/run/event/attachment 물리 삭제: **0건**.

---

## 2. 실측 기준선

### 2.1 Kanban DB

`~/.hermes/kanban.db`를 직접 읽은 snapshot은 다음과 같다.

| 상태 | 건수 |
|---|---:|
| done | 99 |
| blocked | 34 |
| todo | 9 |
| running | 1 (`PLAN-OPS-1`) |
| archived | 4 |

Blocked 34건 중 `block_kind=needs_input` 다수는 실제 human input 부족이 아니라 developer의 `review-required` handoff다. 또 worktree path 누락, body shell-substitution 훼손, 이전 correction generation, 이미 reviewer/QA/commit/deploy가 끝난 task가 blocked로 남아 있다.

### 2.2 확인된 잘못된 active edge

| Child | 현재 parent | 문제 |
|---|---|---|
| `t_79b27437` DEV-1R | `t_5dec0067` blocked/superseded | replacement가 원본 blocked parent를 가져 영구 todo |
| `t_1f8c9314` QA-PROGRESS-1 | `t_30a3d533` blocked | 이후 reviewer/브라우저 QA/fix가 이미 존재하는 stale chain |
| `t_18fc1fe8` VERIFY-V11-1B | `t_1631cefc` blocked review-required | reviewer가 검토 대상 developer의 blocked 상태를 기다림 |
| `t_1fdb2444` QA-V11-1 | `t_18fc1fe8` todo | reviewer가 풀리기 전까지 정상 대기지만 upstream edge가 잘못됨 |
| `t_a1b18044` VERIFY-V11-2 | `t_4d067679` blocked + `t_5b3960ec` done | reviewer가 blocked viewer developer를 기다리고 producer handoff도 gate에 포함되지 않음 |
| `t_5b823723` QA-V11-2 | `t_a1b18044` todo | reviewer 승인 후 실행해야 하므로 edge 자체는 정상 |
| `t_4382ece8` DEV-V12-2 | `t_44e06f2c` blocked + design done | downstream implementation이 미승인 developer handoff에 직접 의존 |
| `t_901de9a3` VERIFY-V12-1 | `t_4382ece8` todo | 최종 통합 reviewer로는 정상이나 backend 선행 승인 gate가 없음 |
| `t_5bb98cd5` QA-V12-1 | `t_901de9a3` todo | 최종 reviewer 승인 후 실행하므로 정상 |

### 2.3 Monitor 기준선

- planner profile cron list에는 job이 없다. PM monitor의 paused 상태는 task brief의 운영 증거로 취급한다.
- file-backed `operations_watchdog.py`는 active Operations brief 전체를 읽어 15분 stall/blocked/worker unavailable을 감지한다.
- `operations/watchdog/state.json`과 `latest.json`은 모두 `2026-07-29T06:56:33.784357+00:00`, active 1건, issues `{}`인 오래된 snapshot이다.
- 현 watchdog은 first-run silent baseline이 아니다. 이전 state가 없고 issue가 있으면 첫 실행부터 전부 출력한다.
- 현 watchdog은 Kanban active workflow registry를 모르며, Dashboard API timeout과 workflow failure를 분리하는 service-health event model도 없다.
- 따라서 기존 watchdog은 보존하되 “Operations file 상태 모니터”로 한정하고, Kanban lifecycle monitor를 별도 script/state로 만든다.

---

## 3. 상태·그래프 표준

### 3.1 서로 분리해야 하는 사실

| 사실 | 표준 표현 | 금지 표현 |
|---|---|---|
| Developer가 변경과 검증 증거를 제출 | `review_ready` handoff record | 실패/입력부족 의미의 `blocked` |
| Reviewer가 아직 시작하지 않음 | independent reviewer `held_by_pm_gate` | blocked developer parent |
| Reviewer PASS | reviewer task `done`, verdict `PASS`, candidate binding | developer comment만으로 승인 |
| Reviewer NEEDS_CHANGES | reviewer `done` 또는 terminal verdict record + correction generation 생성 | reviewer를 영구 blocked evidence로 유지 |
| 실제 외부 차단 | `blocked` + typed `block_kind` + owner/next check | review-required와 혼합 |
| 과거 generation | `archived` + `superseded_by` | active blocked로 계속 노출 |

Core에 `review_ready`가 생기기 전에는 compatibility 방식으로 developer task는 기존 규칙대로 `blocked`가 될 수 있다. 단, PM registry의 `handoff_state=review_ready`가 canonical orchestration 사실이며 reviewer dependency에는 그 task ID를 넣지 않는다.

### 3.2 표준 workflow graph

```text
PLAN / DESIGN / POLICY (done)
        ├──────────────> DEV candidate (sibling; handoff_state=review_ready)
        └──────────────> REVIEW task (independent; PM gate가 hold/promote)

DEV review-ready event
        └── PM gate validates candidate binding ──> REVIEW running

REVIEW PASS (done; candidate_id/version/hash bound)
        └──────────────> downstream DEV / QA / COMMIT / DEPLOY

REVIEW NEEDS_CHANGES
        ├──────────────> correction DEV generation N+1
        └──────────────> new REVIEW generation N+1 (independent/PM-held)

REVIEW N+1 PASS
        └── atomic edge replacement ──> downstream depends only on REVIEW N+1
```

### 3.3 필수 불변조건

1. Developer handoff와 reviewer는 같은 planning/decision parent를 갖는 sibling이다.
2. Reviewer는 developer가 `blocked`, `review_ready`, `archived`인지와 무관하게 PM gate에서 promote된다.
3. PM gate는 structured handoff의 candidate identity, changed files, test evidence, workspace/commit/diff locator를 확인해야 한다.
4. Downstream implementation, QA, commit, deploy는 **최신 PASS reviewer task만** parent로 갖는다.
5. correction 시 old reviewer/developer parent를 active downstream에서 모두 제거한 뒤 newest review gate 하나만 추가한다.
6. edge replacement는 한 transaction으로 처리한다. 중간 순간에 parent가 0개이거나 old/new가 함께 남아 dispatcher가 잘못 실행하지 않아야 한다.
7. `NEEDS_CHANGES`는 승인 parent가 아니다. reviewer task status만 `done`이어도 verdict가 PASS가 아니면 downstream gate를 충족하지 않는다. Core가 verdict-aware dependency를 지원하기 전에는 PM이 PASS reviewer에만 edge를 만든다.
8. Reviewer가 이미 시작한 뒤 developer handoff가 바뀌면 그 review attempt는 stale로 닫고 새 reviewer generation을 만든다.
9. archive는 삭제가 아니다. task/comment/run/event/attachment와 supersession link를 보존한다.

### 3.4 PM-owned review-ready gate

PM reconciler는 다음 조건을 모두 만족할 때만 held reviewer를 promote한다.

- registry에 developer와 reviewer가 같은 `workflow_id`, `generation`, `candidate_key`로 등록됨
- developer의 최신 run outcome이 `blocked`이고 reason prefix가 정확히 `review-required:`이거나 future core 상태가 `review_ready`
- structured comment/metadata에 changed files, test command/result, candidate locator가 존재
- task가 crash/timeout/capability/needs_input 차단이 아님
- reviewer profile이 실제로 존재
- 동일 candidate를 위한 running/done reviewer가 중복 존재하지 않음

조건 불충족이면 promote하지 않고 PM exception `handoff_invalid`를 1회 알린다.

---

## 4. Blocked 34건 분류 및 migration 표

### 4.1 분류 기준

- **active workflow:** 현재 v1.1/v1.2 candidate로 후속 reviewer/downstream이 필요하다. 원본을 retain하고 edge/gate만 정상화한다.
- **superseded:** replacement/correction/re-review/deploy가 존재하거나 해당 generation이 더 이상 실행 대상이 아니다. comment로 successor를 고정하고 archive한다.
- **irrecoverable:** 현재 card 그대로는 재실행해도 안전한 완료가 불가능하고 최신 대체 증거가 없다. blocked retain 후 PM이 fresh recovery/waiver를 결정한다.
- **historical evidence:** 해당 handoff/실패 자체는 유효한 감사 증거지만 후속 review/QA/commit이 이미 끝나 active blocker가 아니다. archive하되 모든 evidence를 보존한다.

### 4.2 전체 migration 표

| ID | 분류 | 실측 근거 | 안전 조치 |
|---|---|---|---|
| `t_2e888c82` | irrecoverable | researcher crash 2회, 결과/후속 없음, 이후 Dashboard 기획이 별도로 완성됨 | blocked retain, PM이 “폐기” 승인 시 archive; 재시도 금지 |
| `t_5dec0067` | superseded | worktree path 오류, PM superseded comment, child DEV-1R 존재 | child edge unlink, parent와 stale child archive |
| `t_445f525c` | historical evidence | DEV handoff 후 REV-1/2/3, QA-2, commit 완료 | archive; comments/runs retain |
| `t_2de777ba` | historical evidence | REV-1 correction, 이후 REV-2 done | archive |
| `t_04e26a39` | historical evidence | test correction, REV-3 done | archive |
| `t_d9c2b428` | superseded | loopback QA 불가, host-network QA-2 done | archive, QA-2 successor link |
| `t_71a84bc6` | superseded | dirty worktree deploy 중지, DEPLOY-1A done | archive |
| `t_49a4c803` | historical evidence | Decision-first handoff 이후 REV/QA/correction/commit 완료 | archive |
| `t_d194d5cc` | superseded | label smoke 실패 후 rollback, correction/verified deploy chain 완료 | archive, rollback evidence retain |
| `t_0b881c8f` | superseded | missing worktree path, DEV-C4A done | archive |
| `t_9edaff12` | superseded | missing worktree path, DEV-C5A done | archive |
| `t_def31f44` | superseded | missing worktree path, DEV-D2A done | archive |
| `t_21ee8752` | superseded | shell substitution으로 QA body 훼손, dispatch 전 corrected task 발행 | archive; malformed body evidence retain |
| `t_ad84dd21` | superseded | missing worktree path, DEV-D4A done | archive |
| `t_319566c2` | superseded | missing worktree path, E1R로 교체 | archive |
| `t_4d5dffcc` | historical evidence | review-ready 후 REV-E1/QA-E1/commit done | archive |
| `t_316a8de1` | irrecoverable | 배포 후 GET timeout 재현, root cause/대체 task 확인 안 됨 | blocked retain; 현재 baseline에서 fresh OPS diagnosis 또는 명시적 waiver 필요 |
| `t_b9b5eb97` | superseded | browser runtime missing, DEV-BROWSER-ENV-1 done | archive; 필요 시 새 baseline QA만 생성 |
| `t_989ddf92` | historical evidence | Slice A handoff, 이후 remediation/review/browser evidence 완료 | archive |
| `t_30a3d533` | superseded | child QA가 blocked parent를 대기하지만 이후 review/QA/fix chain 존재 | child edge unlink, stale child archive, 본 task archive |
| `t_abc8888a` | historical evidence | research policy handoff, independent review done | archive |
| `t_0591df15` | historical evidence | fail-safe correction, REVIEW-PROGRESS-1 done | archive |
| `t_8bb2d2b3` | historical evidence | card control correction, 64 tests/browser evidence, review chain 완료 | archive |
| `t_4e9f89f0` | historical evidence | sync correction handoff, REV-SYNC-STATUS-1 done | archive |
| `t_86a63115` | superseded | v1.1 Slice 1 최초 handoff가 blocker 발견 후 A/A2 correction으로 교체 | archive |
| `t_00c3c47f` | superseded | initial verifier NEEDS_CHANGES, correction generations 존재 | archive, findings retain |
| `t_1631cefc` | active workflow | v1.1 follow-up intake review-ready, child verifier가 blocked parent 대기 | **retain**; child edge unlink 후 reviewer PM-promote |
| `t_fe2905a9` | superseded | A correction이 재검토에서 blocker 유지, A2로 교체 | archive |
| `t_725f8274` | superseded | re-review NEEDS_CHANGES, A2 fix/re-review done | archive |
| `t_be45ffd6` | historical evidence | A2 final correction, `t_de571f93` PASS/done | archive; PASS reviewer가 downstream 승인 근거 |
| `t_d369ba57` | historical evidence | Final Deliverable handoff, REV-V11-2A done | archive |
| `t_4d067679` | active workflow | viewer review-ready, verifier `t_a1b18044`가 blocked parent 대기 | **retain**; edge unlink, reviewer gate에 candidate 포함 |
| `t_3b629b40` | active workflow | producer schema v2 review-ready, 통합 verifier가 이 candidate도 검토해야 함 | **retain**; `t_a1b18044` gate candidate set에 추가, parent edge는 만들지 않음 |
| `t_44e06f2c` | active workflow | v1.2 backend review-ready, DEV-V12-2가 blocked parent 대기 | **retain**; edge unlink, backend reviewer 신설 후 PASS에 relink |

분류 합계: active 4 + superseded 16 + irrecoverable 2 + historical evidence 12 = 34.

### 4.3 Archive와 retain의 의미

- `archive`: active board에서 숨기되 DB row, comment, run, event, attachment는 그대로 둔다. archive comment에 category, reason, successor/PASS reviewer, migration batch ID를 남긴다.
- `retain`: blocked 또는 review-ready evidence를 당장 active registry에 유지한다. dependency로 사용한다는 뜻은 아니다.
- 어떤 항목도 `DELETE`하지 않는다.

---

## 5. v1.1/v1.2 구체 migration

### 5.1 공통 Phase 0 — freeze와 snapshot

Owner: PM

1. Dispatcher를 짧게 pause하거나 migration lock을 획득한다.
2. Kanban DB online backup을 timestamped read-only 파일로 만든다.
3. `tasks`, `task_links`, `task_comments`, `task_runs`, `task_events`, `task_attachments`의 row count와 SHA-256 manifest를 기록한다.
4. blocked 34건과 todo 9건의 current state/parent graph를 JSON migration manifest로 저장한다.
5. active workflow registry v1을 생성하되 첫 실행은 `mode=dry_run`으로 둔다.

AC:

- snapshot에서 모든 task/edge/evidence를 재구성할 수 있다.
- migration 중 새 dispatcher claim이 없다.
- 원본 DB와 backup을 서로 다른 경로에 보존한다.

Rollback:

- dispatcher를 계속 pause한 채 DB backup restore 또는 inverse edge/status manifest를 적용한다.

### 5.2 Phase 1 — evidence annotation

Owner: PM

각 blocked task에 삭제 없는 migration comment를 추가한다.

```text
lifecycle-migration:<batch-id>
category: active_workflow|superseded|irrecoverable|historical_evidence
action: retain|archive|unlink
successor_or_gate: <task-id/none>
reason: <structured reason>
original evidence preserved: yes
```

AC: 34/34 task가 category와 action을 갖고 합계가 일치한다.

Rollback: comment는 감사 증거로 유지하고 `migration_rolled_back` 후속 comment만 추가한다.

### 5.3 Phase 2 — stale edge 제거

Owner: PM operation script, verifier observation

한 transaction에서 다음을 수행한다.

1. `t_5dec0067 → t_79b27437` 제거 후 두 task를 superseded archive 대상으로 지정.
2. `t_30a3d533 → t_1f8c9314` 제거 후 stale QA를 superseded archive 대상으로 지정.
3. `t_1631cefc → t_18fc1fe8` 제거.
4. `t_4d067679 → t_a1b18044` 제거. `t_5b3960ec(done)` parent는 planning/review history로 제거하거나 비실행 evidence link로 전환한다.
5. `t_44e06f2c → t_4382ece8` 제거.

AC:

- `todo/running` child의 parent status가 blocked/archived인 edge 0건.
- child가 parent 0개가 되어 즉시 실행되는 race가 없다. reviewer는 PM-held registry, downstream은 replacement PASS gate가 준비될 때까지 held다.

Rollback: inverse edge manifest를 transaction으로 재적용하되 dispatcher는 pause 상태를 유지한다.

### 5.4 Phase 3 — v1.1 review 연속 진행

Owner: PM

#### Follow-up intake chain

- Developer candidate: `t_1631cefc`.
- Reviewer: `t_18fc1fe8`.
- PM gate가 developer structured handoff와 89-test evidence를 확인한 후 reviewer를 promote한다.
- Reviewer PASS 시 QA `t_1fdb2444`의 유일한 승인 parent를 `t_18fc1fe8`로 유지한다.
- NEEDS_CHANGES 시 old QA edge를 제거하고 correction + reviewer generation을 만든다. QA는 newest PASS reviewer에만 relink한다.

#### Final artifact chain

- Candidate set: viewer `t_4d067679`, producer `t_3b629b40`, 이미 승인된 projection reviewer `t_5b3960ec`.
- Reviewer `t_a1b18044`는 blocked developer parent 없이 PM gate에서 promote한다.
- Reviewer body/registry에 viewer와 producer candidate locator를 모두 명시한다.
- PASS 시 QA `t_5b823723`는 `t_a1b18044` 하나만 parent로 유지한다.
- producer가 reviewer 시작 뒤 변경되면 현재 review는 stale close하고 새 reviewer generation을 생성한다.

v1.1 AC:

- reviewer 두 건이 dispatcher에서 실제 claim된다.
- review evidence가 exact candidate set에 bind된다.
- QA는 PASS 전 실행되지 않고 PASS 뒤 자동 ready가 된다.
- old developer/reviewer edge가 QA에 남지 않는다.

Rollback:

- 아직 reviewer 미실행이면 PM hold로 되돌린다.
- reviewer 실행 후에는 evidence를 삭제하지 않고 stale/void reason을 기록한 새 generation을 만든다.

### 5.5 Phase 4 — v1.2 backend→shell→통합 검토

Owner: PM

현재 `DEV-V12-2`를 바로 실행시키지 않는다. `t_44e06f2c` backend가 review-ready일 뿐 아직 approved가 아니기 때문이다.

1. 새 independent `VERIFY-V12-1A — Console v2 backend projection/API/instruction boundary review`를 planning/design/policy task의 sibling으로 생성하고 PM-held 상태로 둔다.
2. `t_44e06f2c` handoff 감지 후 PM이 backend reviewer를 promote한다.
3. PASS 시 `t_4382ece8`의 유일한 implementation gate를 이 PASS reviewer로 설정하고 실행한다.
4. `DEV-V12-2` handoff 후 기존 `t_901de9a3` final integrated reviewer를 PM-promote한다. 이 reviewer도 blocked DEV-V12-2를 parent로 갖지 않는다.
5. final reviewer PASS 시 QA `t_5bb98cd5`가 자동 ready가 된다.
6. QA PASS 후 commit/deploy task를 만들 경우 parent는 QA PASS 또는 별도 release reviewer PASS 하나만 사용한다.

v1.2 AC:

- backend→shell 사이에 독립 PASS가 존재한다.
- instruction parent non-mutation/authority boundary가 UI integration 전에 검증된다.
- final reviewer는 backend reviewer 결과와 shell candidate를 함께 검토한다.
- QA는 final reviewer PASS 전 실행되지 않는다.

Rollback:

- backend reviewer FAIL이면 `DEV-V12-2`를 held 상태로 유지하고 correction generation을 만든다.
- shell reviewer FAIL이면 QA edge를 newest reviewer로 atomic replace한다.
- 어떠한 rollback도 이미 기록된 developer/reviewer evidence를 삭제하지 않는다.

### 5.6 Phase 5 — archive batch

Owner: PM, verifier spot-check

- superseded 16건과 historical evidence 12건을 annotation 후 archive한다.
- irrecoverable 2건은 active registry에 넣지 않는다. PM decision queue에 “fresh recovery/waiver 필요”로 retain한다.
- active 4건은 review가 끝나고 successor gate가 세워질 때까지 retain한다. 그 후 historical evidence로 archive할 수 있다.

AC:

- blocked count는 실제 외부/운영 차단과 현재 review-ready compatibility record만 남는다.
- archived task를 검색했을 때 body/comment/run/event를 모두 조회할 수 있다.
- stale task가 Dashboard active workflow count에 포함되지 않는다.

Rollback: archived status를 manifest의 원래 status로 복원한다. Evidence row는 처음부터 손대지 않는다.

---

## 6. Active workflow registry

### 6.1 즉시 구현할 registry v1

권고 위치: `operations/kanban/workflows.v1.json` 또는 PM profile의 전용 state directory. Dashboard raw task와 혼합하지 않는다.

```json
{
  "schema_version": 1,
  "workflows": {
    "wf-v12-console": {
      "state": "active",
      "generation": 1,
      "tasks": {
        "developer": "t_44e06f2c",
        "reviewer": "<VERIFY-V12-1A>",
        "downstream": ["t_4382ece8"]
      },
      "candidate_key": "workspace-or-commit+diff-manifest",
      "latest_approved_reviewer": null,
      "expected_terminal_gates": ["review_pass", "qa_pass", "release_decision"],
      "heartbeat_minutes": 30,
      "delivery_target": "pm-configured-gateway-target"
    }
  }
}
```

필수 필드:

- `workflow_id`, `schema_version`, `state`, `generation`
- role별 task ID와 candidate key
- latest approved reviewer ID/verdict/candidate binding
- expected terminal gates
- last event cursor/fingerprint, last heartbeat, delivery preflight result
- superseded task IDs와 replacement mapping

### 6.2 Registry 안전 규칙

- 명시 등록된 workflow만 monitor/reconciler가 본다.
- title prefix나 created_at만으로 project/workflow를 추론하지 않는다.
- task가 archive되어도 registry history에서 ID를 삭제하지 않는다.
- active generation에는 reviewer 최대 1개, approved reviewer 최대 1개다.
- write 전 expected DB state/version을 비교하고 다르면 no-op + conflict event를 낸다.

---

## 7. Monitor 설계

### 7.1 구성 분리

- `operations_watchdog.py`: 기존 file-backed Agent Hub Operations task/stage stall 감시. 유지.
- 신규 `kanban_workflow_monitor.py`: Kanban DB/event와 active workflow registry만 감시.
- 신규 `kanban_workflow_reconciler.py`: reviewer promote, edge replace, archive candidate 제안/적용. monitor와 write 권한 분리.

Monitor는 read-only다. Reconciler만 명시적 PM 정책으로 write한다.

### 7.2 First run silent baseline

State가 없거나 schema version이 바뀐 첫 실행:

1. active registry의 현재 task/run/comment/event cursor를 snapshot한다.
2. 기존 blocked/done/result를 “새 사건”으로 출력하지 않는다.
3. `baseline_created_at`, `registry_hash`, `last_event_id`, task fingerprints를 저장한다.
4. stdout은 비운다.
5. delivery preflight 실패만 local service log에 기록하고 user workflow failure로 보내지 않는다.

`--rebaseline`도 동일하게 silent이며 audit log만 남긴다.

### 7.3 알림 event allowlist

Active registry 안에서 아래 transition만 알린다.

- task가 `done`, `blocked`, `failed`, `timed_out`으로 새 전이
- 새로운 `review-required` handoff 또는 future `review_ready`
- 새 structured result/comment/run summary 도착
- reviewer verdict PASS/NEEDS_CHANGES 및 candidate binding 변화
- Dashboard workflow stage 변화
- dependency conflict, invalid handoff, duplicate reviewer generation
- terminal workflow close

알리지 않는 것:

- 동일 상태 polling
- historical/superseded/archived task 변화 없음
- 단순 `updated_at`/mtime 변화
- active registry 밖의 blocked 34건
- Dashboard service timeout을 project task failed로 변환한 추론

### 7.4 Dashboard timeout 분리

Event namespace를 분리한다.

| Namespace | 예시 | 프로젝트 상태 영향 |
|---|---|---|
| `workflow.*` | `workflow.task_blocked`, `workflow.review_ready`, `workflow.review_pass` | 가능, explicit evidence만 |
| `service.dashboard.*` | `service.dashboard.timeout`, `service.dashboard.http_error` | 없음 |
| `monitor.*` | `monitor.db_read_error`, `monitor.delivery_error`, `monitor.state_corrupt` | 없음 |

Dashboard HTTP timeout 발생 시 출력 예:

```text
[Monitor/Service 예외] Dashboard health 조회 timeout
workflow 상태: 변경 없음
영향: 관찰 surface 실패; Kanban task failure로 승격하지 않음
다음 확인: service retry/backoff 및 마지막 성공 시각
```

### 7.5 30분 heartbeat

- active workflow가 하나 이상이고 의미 있는 event가 30분 없을 때만 heartbeat 1건을 보낸다.
- 내용: workflow ID, 현재 gate, active task, last evidence time, next expected event, monitor/service health.
- blocked/failed를 반복 전송하지 않는다. 해당 사건 fingerprint는 첫 발생 1회이며 heartbeat에는 요약만 싣는다.
- active workflow가 0이면 heartbeat를 보내지 않는다.

### 7.6 Terminal workflow close

아래를 모두 만족할 때 한 번만 `workflow.closed`를 보낸다.

1. registry의 required implementation/reviewer/QA/release gates가 terminal.
2. 최신 reviewer verdict가 PASS이거나 PM이 explicit cancel/waiver를 기록.
3. 실행 중/held review-ready/correction-required task가 없음.
4. downstream task가 done/archived/cancelled 중 하나.
5. delivery preflight가 성공했거나 close message가 durable outbox에 저장됨.

Close 후 registry state를 `closed`로 바꾸고 polling/heartbeat 대상에서 제외한다. 후속 correction은 같은 workflow를 다시 열지 않고 generation N+1 또는 새 workflow ID를 만든다.

### 7.7 Delivery preflight

Monitor 활성화 전에 PM이 다음을 검증한다.

- gateway destination이 실제 연결된 platform/chat/thread로 resolve되는가
- notifier profile이 해당 source profile notification을 허용하는가
- test event의 message ID/HTTP success가 기록되는가
- 실패 시 retry/backoff와 durable outbox가 작동하는가
- local-only `origin` 전달을 Discord 전달로 오인하지 않는가

Preflight 실패 시 workflow monitor는 관찰을 계속하되 delivery 상태를 degraded로 표시하고, project failure alert는 만들지 않는다.

### 7.8 실행 주기

- 5분 polling은 유지 가능하나 deterministic script로 실행한다.
- first baseline/transition detection/fingerprint/heartbeat는 LLM 없이 처리한다.
- PM 판단이 필요한 conflict만 PM task/comment로 escalation한다.
- monitor와 reconciler는 lock을 공유하되 monitor read failure가 reconciler write를 촉발해서는 안 된다.

---

## 8. 즉시 PM 운영 스크립트 vs Hermes Kanban core/config

### 8.1 PM 운영 계층에서 즉시 구현

| 기능 | 이유 |
|---|---|
| active workflow registry | 제품 core 변경 없이 감시 범위를 명시 가능 |
| blocked inventory dry-run/classification report | 현 board를 즉시 안전하게 정리 가능 |
| review-ready structured handoff detector | comment/run evidence를 기준으로 reviewer promote 가능 |
| held reviewer PM promotion | blocked developer parent를 제거해 deadlock 해소 |
| latest PASS reviewer edge reconciler | correction 때 obsolete parent 전수 제거 가능 |
| first-run silent monitor, fingerprint dedupe, 30분 heartbeat | deterministic 운영 정책으로 즉시 구현 가능 |
| Dashboard/service/monitor namespace 분리 | 오탐을 즉시 줄임 |
| delivery preflight/outbox/terminal close | cron 운영 신뢰성 확보 |
| archive annotation과 supersession manifest | evidence를 삭제하지 않고 board noise 감소 |

### 8.2 Hermes Kanban core 개선

| Core 개선 | 필요성 | 우선순위 |
|---|---|---:|
| `review_ready`/`awaiting_review` 상태 | review handoff를 failure blocked와 분리 | P0 |
| typed dependency (`completion`, `approval`, `informational`) | done만 보는 parent semantics 한계 해소 | P0 |
| verdict-aware approval gate + candidate binding | reviewer done이 PASS를 의미하지 않는 문제 해결 | P0 |
| atomic replace-parents API | correction 시 stale edge/race 방지 | P0 |
| `superseded_by`/archive reason first-class field | comment free text 의존 제거 | P1 |
| workflow template/generation | developer/reviewer/QA 표준 graph 자동 생성 | P1 |
| review-ready event/webhook | polling 대신 PM gate event-driven promote | P1 |
| active workflow query/registry core support | 별도 sidecar drift 감소 | P1 |
| block kind validator | `review-required`를 needs_input으로 저장하지 않게 함 | P1 |
| migration/dry-run/invariant checker | blocked/archived parent edge 사전 차단 | P1 |

### 8.3 Hermes config 개선

- default board `default_workdir=/home/raphael/myproject`를 명시하거나 project-linked task 생성만 허용한다.
- `workspace_kind=worktree`인데 path/project가 없으면 task 생성 시 reject한다. Dispatcher spawn 시점까지 미루지 않는다.
- profile aliases는 실제 `developer`, `verifier`, `qa`, `pm` 존재를 create 시 검증한다.
- failure circuit breaker와 review-ready 상태를 분리한다.
- monitor delivery source/target allowlist를 명시한다.

---

## 9. 구현 순서와 owner

| 순서 | 작업 | Owner | 선행 | 완료 기준 |
|---:|---|---|---|---|
| 0 | DB backup, graph/evidence manifest, dispatcher migration lock | PM | 없음 | 복원 가능한 snapshot |
| 1 | registry/monitor/reconciler dry-run 구현 | developer | 본 계획 | fixture와 현재 DB에서 write 0건 dry-run |
| 2 | 독립 safety review | verifier | developer handoff 감지(PM gate) | 삭제/edge race/오승인 blocker 0건 |
| 3 | blocked 34건 annotation | PM | verifier PASS | 34/34 분류 합계 일치 |
| 4 | stale edge transaction 및 active reviewer promote | PM | annotation | blocked/archived parent active edge 0건 |
| 5 | v1.1 reviewer→QA chain 실행 | PM + verifier + QA | Phase 4 | reviewer PASS 후만 QA ready |
| 6 | v1.2 backend reviewer 신설/승인→shell | PM + verifier + developer | Phase 4 | DEV-V12-2가 PASS reviewer만 parent |
| 7 | superseded/historical archive batch | PM | edge 검증 | evidence 보존, board noise 제거 |
| 8 | monitor silent baseline 및 delivery preflight | PM | registry 안정 | first run stdout empty, preflight success |
| 9 | 24시간 관찰 후 write mode 전환 | PM | dry-run clean | false promote/archive 0건 |
| 10 | Hermes core/config backlog 실행 | Hermes core developer/reviewer | 운영 안정화 | P0 invariant tests pass |

---

## 10. 정확한 후속 task 명세

### 10.1 Developer — `t_ec8cf879` / `DEV-OPS-1: Kanban workflow registry·reconciler·monitor 구현`

Assignee: `developer`

범위:

- `operations/kanban/` 아래 schema v1 registry/state/outbox 또는 동등한 명시 위치
- blocked inventory/classification dry-run report
- review-ready handoff detector
- independent reviewer PM hold/promote contract
- latest PASS reviewer atomic edge replacement plan/apply
- first-run silent monitor, allowlisted transitions, fingerprint dedupe
- service/workflow/monitor namespace, 30분 heartbeat, terminal close
- delivery preflight와 durable outbox
- fixture 기반 migration tests; default는 dry-run

금지:

- 원본 task/comment/run/event/attachment 삭제
- reviewer 자동 승인
- active registry 밖 task의 자동 archive
- Dashboard timeout을 workflow failure로 승격
- 바로 production write mode 활성화

AC:

- 현재 snapshot을 입력한 dry-run이 이 문서의 34건 분류와 5개 stale edge 조치를 재현한다.
- first run output empty, second run 동일 snapshot output empty.
- review-ready 새 사건 1회, PASS reviewer edge replacement 1회, heartbeat 30분 1회.
- correction generation에서 old parent 0개, newest PASS parent 1개.
- service timeout에서 workflow status mutation 0건.
- DB evidence row 삭제 0건.

### 10.2 Verifier — `t_d233b21a` / `VERIFY-OPS-1: Lifecycle migration·autocontinue safety review`

Assignee: `verifier`

형태: developer의 blocked parent를 갖지 않는 independent sibling. PM-held 후 handoff 감지 시 promote.

검증:

- 현재 DB snapshot 대비 34건 분류/합계/근거
- archive가 delete가 아닌지
- active child의 blocked/archived parent 0건
- reviewer가 blocked developer를 parent로 갖지 않는지
- PASS verdict/candidate binding 없이 downstream이 열리지 않는지
- correction 시 old edge atomic removal
- first baseline silence, dedupe, heartbeat, terminal close
- Dashboard timeout namespace 분리
- delivery preflight failure가 project failure로 오표시되지 않는지
- rollback manifest로 pre-migration graph 복원 가능한지

출시 차단:

- evidence 삭제/유실 가능성
- parent 0 race로 premature dispatch 가능성
- reviewer done만 보고 PASS로 간주
- active registry 밖 task mutation
- write mode가 dry-run 검토 전 켜짐

### 10.3 PM — `t_b52872ce` / `PM-OPS-1: Board migration 승인·v1.1/v1.2 gate 운영 전환`

Assignee: `pm`

범위:

- backup/lock/delivery preflight 승인
- verifier PASS 후 migration batch 실행
- `t_18fc1fe8`, `t_a1b18044` PM promote
- v1.2 backend reviewer 생성/promote 및 PASS 후 `t_4382ece8` relink
- irrecoverable `t_2e888c82`, `t_316a8de1`에 recovery/waiver 결정
- archive batch와 24시간 dry-run 관찰
- terminal close 및 Hermes core P0 backlog 승인

AC:

- v1.1/v1.2 active graph가 §3 표준을 만족한다.
- 모든 status/edge 변경에 batch ID, before/after, reason이 있다.
- false alert/false promote/false archive 0건.
- rollback drill 1회 성공.

### 10.4 Hermes core backlog — `DEV-KANBAN-CORE-1`

Assignee: Hermes core 담당 developer; 별도 repository/worktree 확정 후 생성.

범위: `review_ready`, typed dependency, verdict-aware gate, atomic parent replacement, supersession/archive reason, invariant tests. 이 task는 Dashboard repository의 DEV-OPS-1과 혼합하지 않는다.

---

## 11. Test matrix

| ID | 시나리오 | 기대 |
|---|---|---|
| K-01 | first run, active workflows already blocked/done 포함 | baseline 저장, stdout empty |
| K-02 | 동일 snapshot 재실행 | output empty |
| K-03 | developer review-required comment 신규 | `workflow.review_ready` 1회 |
| K-04 | reviewer가 blocked developer parent를 가짐 | invariant error, promote 금지 |
| K-05 | reviewer independent + valid candidate | PM promote candidate 생성 |
| K-06 | reviewer status done, verdict NEEDS_CHANGES | downstream gate 미충족 |
| K-07 | reviewer PASS but candidate hash mismatch | gate 미충족, stale review event |
| K-08 | correction N+1 PASS | old parents 제거, N+1 reviewer 하나만 parent |
| K-09 | archive 28건 | body/comment/run/event/attachment row count 불변 |
| K-10 | Dashboard HTTP timeout | service event만, workflow mutation 없음 |
| K-11 | 30분 변화 없음 + active workflow 있음 | heartbeat 1회 |
| K-12 | active workflow 0 | heartbeat 없음 |
| K-13 | terminal gates 완료 | close 1회, 이후 polling silent |
| K-14 | delivery preflight 실패 | outbox 저장, project failure 없음 |
| K-15 | concurrent DB state 변경 | optimistic conflict, write 0건 |
| K-16 | rollback | original status/edge graph 복원, evidence 보존 |
| K-17 | worktree path 없음 | create/preflight 단계에서 reject |
| K-18 | registry 밖 historical blocked 변화 | 알림/mutation 없음 |

---

## 12. 가정

- [가정 A1] `archived`는 task evidence를 물리 삭제하지 않는 상태이며 조회 가능하다.
- [가정 A2] PM은 migration 동안 dispatcher를 pause하거나 동등한 lock을 획득할 수 있다.
- [가정 A3] v1.1/v1.2 developer comments의 changed files/tests/candidate locator를 structured handoff로 정규화할 수 있다.
- [가정 A4] verifier/qa/developer/pm profile은 현재 `hermes profile list`에 존재한다.
- [가정 A5] PM gateway의 실제 Discord destination은 PM runtime에서 preflight할 수 있다. planner profile의 local cron list 0건은 PM delivery 상태의 증거로 사용하지 않는다.
- [가정 A6] Hermes core 개선은 `/home/raphael/myproject`와 별도 repository일 수 있으므로 별도 task/worktree가 필요하다.

---

## 13. 리스크와 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| Archive를 삭제로 구현 | 감사 evidence 유실 | row-count/hash manifest, delete 금지 test, backup |
| Edge 제거 순간 child 즉시 dispatch | 미승인 실행 | dispatcher lock + atomic replacement + PM hold |
| reviewer done을 PASS로 오인 | 결함 배포 | explicit verdict/candidate binding 필수 |
| shared workspace candidate drift | stale review | candidate key/hash, 변경 시 새 generation |
| monitor baseline flood | 알림 피로 | first-run silent baseline, registry allowlist |
| Dashboard timeout 오탐 | 프로젝트 실패 오보고 | namespace/상태 영향 분리 |
| delivery target 미연결 | close/exception 유실 | preflight + durable outbox |
| PM script와 core가 이중 write | edge 충돌 | versioned ownership, core 전환 시 reconciler write disable |
| old blocked가 Dashboard active count에 남음 | 운영 판단 왜곡 | registry-only monitor와 archive batch |
| irrecoverable task를 무작정 재시도 | 과거 baseline에 잘못된 변경 | fresh recovery/waiver decision |

---

## 14. 변경 영향

- Kanban board: blocked noise가 감소하고 실제 active/review-ready/incident가 구분된다.
- Dispatcher: 현재 core를 바꾸기 전에도 blocked parent deadlock이 제거된다.
- PM 운영: reviewer promote와 dependency correction의 단일 owner가 된다.
- Developer: review-required handoff metadata가 더 엄격해진다.
- Verifier: independent sibling으로 실행되며 exact candidate binding을 판정한다.
- QA/deploy: 최신 PASS reviewer만 dependency로 받는다.
- Dashboard: active workflow registry 기반의 신뢰 가능한 workflow 상태를 표시할 수 있으나, 이 계획 자체는 UI를 변경하지 않는다.
- Monitor: Operations watchdog과 Kanban lifecycle monitor가 분리되어 timeout/서비스 예외 오탐이 줄어든다.

---

## 15. 미결 질문

1. Core 변경 전 reviewer PM hold를 task `blocked`로 둘지 registry-only held state로 둘지? 권고: task는 parent 없이 `todo`로 만들되 dispatcher claim 방지를 위해 PM-controlled hold capability를 사용한다. 해당 capability가 없으면 `initial_status=blocked` + typed PM comment로 두고 handoff 때 unblock한다.
2. archive된 task를 Dashboard 기본 검색에서 어느 범위까지 노출할지? 권고: active board 제외, history/search에서는 전체 evidence 조회.
3. `t_316a8de1`의 timeout이 현재 main에서도 재현되는가? 운영 surface를 직접 점검한 fresh task에서만 판단한다. 과거 card 재실행은 금지한다.
4. PM Discord delivery target/thread ID는 무엇인가? 구현 task에서 secret/PII를 문서에 쓰지 않고 preflight 결과 ID만 기록한다.
5. Hermes core repository와 owner는 누구인가? PM이 별도 core task 생성 전에 확정한다.

---

## 16. Acceptance checklist

- [x] blocked 34건을 active workflow / superseded / irrecoverable / historical evidence로 전수 분류했다.
- [x] 각 task별 archive/unlink/retain 조치와 근거를 표로 제시했다.
- [x] 원본 evidence 삭제 금지와 archive/rollback 규칙을 명시했다.
- [x] developer handoff와 reviewer를 sibling/independent로 정의했다.
- [x] reviewer가 blocked developer parent에 의존하지 않도록 했다.
- [x] PM-owned review-ready gate와 promote 조건을 정의했다.
- [x] downstream이 최신 PASS reviewer에만 의존하도록 했다.
- [x] correction 시 obsolete dependency 전수 제거와 atomic replacement를 정의했다.
- [x] first-run silent baseline, registry-only 감시, event allowlist, timeout 분리, 30분 heartbeat, terminal close, delivery preflight를 정의했다.
- [x] PM 운영 스크립트와 Hermes Kanban core/config 개선을 분리했다.
- [x] v1.1/v1.2 migration 순서, owner, AC, rollback을 제시했다.
- [x] 정확한 developer/verifier/PM 후속 task 명세를 포함했다.
- [x] 가정, 리스크, 변경 영향, 미결 질문을 명시했다.

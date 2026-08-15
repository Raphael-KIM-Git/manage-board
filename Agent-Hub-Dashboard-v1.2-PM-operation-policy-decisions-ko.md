---
title: Agent Hub Dashboard v1.2 PM 운영 정책 결정 기록
id: PM-V12-1
status: decided
applies_to: Raphael Agent Hub Dashboard-only v1 / Dashboard v1.2
source_prd: Agent-Hub-Dashboard-v1.2-quadrant-operations-console-PRD-ko.md
updated_at: 2026-07-31
---

# PM-V12-1 — Project identity·instruction triage 운영 정책 결정

## 1. 결정 요약

| 항목 | v1.2 결정 | 핵심 경계 |
|---|---|---|
| Canonical project identity | raw task의 명시적 `project_ref.project_id` | 프로젝트명·제목·경로·task ID 접두어·최근 선택값으로 귀속하지 않는다. |
| Project registry | v1.2에서 도입하지 않음 | registry는 향후 cross-task project metadata가 실제로 필요할 때 별도 migration으로 도입한다. |
| Additional instruction accept/reject | Dashboard 4-pane 밖의 PM-only decision writer | 제출 UI와 accept/reject 권한·route·감사 근거를 분리한다. |
| `new_task_brief` | 명시적 최종 submit 직후 새 `queued` task 생성 | 생성은 dispatch/approval/completion이 아니다. |
| Mission Control deadline/SLA | v1.2에 새 source를 도입하지 않음 | priority와 정확한 evidence만으로 정렬하며, text/aging으로 SLA를 추론하지 않는다. |

이 기록은 PRD §5, §7, §8, §12의 열린 질문에 대한 구현 우선순위 계약이다. 충돌 시에는 이 문서의 결정과 기존 v1.1의 non-mutation/authority boundary를 우선하며, 코드 변경은 별도 Developer·Verifier·QA gate를 거친다.

## 2. 결정 1 — Project identity는 raw task `project_ref`를 canonical source로 사용

### 결정 및 근거

v1.2의 task→project 귀속 canonical source는 task raw의 optional `project_ref.project_id` 하나로 확정한다. 아직 project registry를 만들지 않는다.

근거:

1. 현재 task writer와 `/api/tasks`는 task JSON을 canonical raw로 생성·조회하며, 별도 registry writer/read consistency/삭제 정책이 존재하지 않는다.
2. v1.2 Projects pane의 목적은 portfolio 편집이 아니라 read-only group/navigation이다. 별도 entity registry는 이번 slice의 목적보다 migration·충돌·운영 권한 범위를 불필요하게 넓힌다.
3. task에 identity를 직접 기록하면 task snapshot만으로 동일한 재현 가능한 group을 계산할 수 있다. identity 미지정 task는 안전하게 `unassigned`로 남긴다.

### Raw contract: task `project_ref` v1

`project_ref`는 optional object다. 없거나 malformed면 identity는 `unknown/unassigned`이며, 서버·projection은 이를 보정하거나 유추하지 않는다.

```json
{
  "project_ref": {
    "schema_version": 1,
    "project_id": "opaque-stable-project-id",
    "display_name": "표시용 프로젝트명"
  }
}
```

규칙:

- `project_id`는 non-empty opaque stable string이며, project identity의 유일한 key다.
- `display_name`은 표시용 snapshot이다. identity key가 아니며 title·path·slug로 생성하거나 보정하지 않는다.
- 같은 `project_id`에 서로 다른 non-empty `display_name`이 관측되면 한 이름을 임의로 선택하지 않는다. Projects pane은 해당 group을 `확인 필요`로 표시하고 raw values/evidence를 task detail에서 확인 가능하게 한다.
- `project_ref` 자체가 string, 배열, `project_id` 없는 object, 또는 지원하지 않는 schema version이면 `unknown/unassigned`이다. 원본 raw task는 변경하지 않는다.
- 기존 task에 `project_ref`를 backfill하지 않는다. 기존 task는 migration 후에도 기본적으로 `프로젝트 미지정`이다.
- `project_ref`를 수정하거나 재배정하는 Dashboard pane action은 v1.2 범위 밖이다.

### API/projection contract

- `POST /api/tasks`는 client가 optional `project_ref`를 보내면 위 schema를 검증해 신규 task raw에 그대로 기록할 수 있다. 유효하지 않으면 `422 invalid_project_ref`로 실패하며 task를 만들지 않는다.
- client가 `project_ref`를 보내지 않으면 task 생성은 계속 성공하고 `project_ref`는 absent다.
- `/api/dashboard-console` v2의 project row/task ref는 `project_ref.project_id`가 유효한 task만 실제 project group에 넣는다. 그 밖의 task는 단일 synthetic bucket `unassigned`에 넣되 실제 project ID로 노출하지 않는다.
- `project_ref` 유무는 기존 `/api/tasks`, `/api/overview`, task detail의 status/stage/gate/final-review/dispatch 의미를 변경하지 않는 additive field다.
- `project_ref`가 없다는 사실은 task가 실패·보류·완료라는 의미가 아니다.

예시 projection:

```json
{
  "projects": [
    {
      "project_id": "proj-agent-hub-v12",
      "display_name": "Agent Hub Dashboard v1.2",
      "identity_state": "explicit",
      "task_ids": ["T-20260731-001"]
    }
  ],
  "unassigned": {
    "identity_state": "unassigned",
    "task_ids": ["T-20260731-002"]
  }
}
```

### Migration/compatibility 영향

- 기존 raw task는 변경하지 않는다. projection은 missing field를 `unassigned`로 처리한다.
- 기존 consumer는 `project_ref`를 무시해도 정상 동작해야 한다.
- 향후 registry 도입이 필요하면 `project_ref.project_id`를 계속 canonical binding key로 유지하고, registry는 display metadata/명시적 lifecycle만 제공한다. registry와 raw ref의 양방향 자동 동기화·title 기반 backfill은 금지한다.

## 3. 결정 2 — additional instruction의 accept/reject는 PM-only decision writer에서 처리

### 결정 및 근거

`additional_instruction`은 Dashboard 1영역에서 append-only record로만 제출한다. accept/reject/clarification/supersede는 4-pane 및 일반 Dashboard 사용자 surface가 아닌 PM-only decision writer에서 수행한다.

이는 현재 v1.1 follow-up request의 “submit endpoint와 PM decision endpoint를 분리”한 authority pattern을 따른다. 자유 텍스트의 저장이나 PM reply text만으로 task/stage/gate/approval/dispatch/completion을 바꾸지 않는다.

v1.2 초기 구현은 PM service/CLI가 호출하는 서버 측 decision writer로 제한한다. 별도 PM 운영 UI가 필요해질 때에도 같은 writer/API와 audit record를 재사용하며, 4-pane row에 write CTA를 추가하지 않는다.

### Raw sidecar contract: instruction record v1

저장 위치는 task raw가 아닌 additive sidecar로 한다.

- task target: `operations/instructions/tasks/<task-id>/<instruction-id>.json`
- project target: `operations/instructions/projects/<project-id>/<instruction-id>.json`
- target 없음/new-work context: `operations/instructions/unbound/<instruction-id>.json`

```json
{
  "schema_version": 1,
  "instruction_id": "INS-opaque-id",
  "version": 1,
  "mode": "additional_instruction",
  "target": {"kind": "task", "id": "T-20260731-001"},
  "text": "추가로 확인할 운영 맥락",
  "state": "submitted_pending_pm_review",
  "submitted_by": {"actor_id": "server-resolved-actor", "auth_source": "dashboard-local"},
  "submitted_at": "ISO-8601",
  "idempotency_key": "server-recorded-opaque-key",
  "decision": null,
  "links": [],
  "events": [{"event": "submitted", "at": "ISO-8601", "from": null, "to": "submitted_pending_pm_review"}]
}
```

Client는 `instruction_id`, `version`, `state`, `submitted_by`, timestamps, `decision`, `links`, event를 지정할 수 없다. actor는 인증된 server-side context에서 해석하며 client 입력 actor를 신뢰하지 않는다.

### API contract

#### Intake (Dashboard composer permitted)

`POST /api/dashboard/instructions`

- 허용 mode: `additional_instruction`만.
- 필수 header: `Content-Type: application/json`, `Idempotency-Key`.
- same-origin/actor/capability/payload size/target existence를 검증한다.
- 성공은 `201`(새 record) 또는 동일 key·동일 payload의 `200`(기존 record)이며 `parent_changed=false`를 반드시 반환한다.
- 동일 key·다른 payload는 `409 idempotency_conflict`; 유효하지 않은 target/mode/payload는 stable error code와 함께 실패한다.

```json
{
  "ok": true,
  "instruction": {
    "instruction_id": "INS-opaque-id",
    "version": 1,
    "state": "submitted_pending_pm_review"
  },
  "parent_changed": false
}
```

#### Decision writer (PM-only; 4-pane CTA 금지)

`POST /api/pm/instructions/{instruction_id}/decisions`

```json
{
  "instruction_version": 1,
  "decision": "accept_as_context|accept_as_new_brief|needs_clarification|reject|supersede",
  "reason": "판단 근거",
  "links": [
    {"rel": "decision_evidence", "id": "PMD-opaque-id"}
  ],
  "new_brief_spec": null
}
```

- PM 인증/authorizer가 없는 경우 endpoint 자체를 disabled/403 처리한다.
- optimistic concurrency로 `instruction_version`을 요구하며 stale version은 `409`이다.
- writer는 append-only decision event와 `decision_evidence_id`를 기록한다. accepted/rejected state에는 evidence ID가 필수다.
- `accept_as_context`는 context link만 만들고 parent raw workflow를 변경하지 않는다.
- `accept_as_new_brief`만 별도 신규 task creation writer를 호출할 수 있다. 이때 새 task ID를 links에 기록하며 parent task의 state/stage/gate/final review/dispatch는 불변이다.
- `needs_clarification`, `reject`, `supersede`는 workflow mutation을 수행하지 않는다.
- 어느 decision도 dispatch, approval, gate override, final approval, completion을 생성하거나 암시하지 않는다.

### Migration/compatibility 영향

- instruction API가 준비되기 전 composer write capability는 false로 제공하고 draft를 로컬에 보존한다. live note 또는 기존 follow-up endpoint로 silently fallback하지 않는다.
- 기존 follow-up request는 task detail 전용이며, v1.2 instruction과 자동 병합하지 않는다. 중복은 PM decision writer가 evidence를 남겨 reject/supersede한다.
- Mission Control은 pending instruction을 `decision` 후보로 읽기만 하며, action은 record/detail navigation뿐이다.

## 4. 결정 3 — `new_task_brief`는 명시적 submit 시 즉시 `queued` task를 만든다

### 결정 및 근거

기존 `POST /api/tasks` contract를 보존한다. `new_task_brief` mode에서 title·objective를 가진 명시적 최종 submit이 성공하면 서버는 신규 raw task를 즉시 생성하고 status를 `queued`로 기록한다.

이는 additional instruction과 다르다. 새 brief는 독립 업무 identity를 만들기 위한 명시적 intake이고, 추가 지시는 기존 맥락에 대한 append-only 의도 기록이다. 생성 후 PM이 triage/dispatch 판단을 하는 흐름은 유지하되, task identity 생성 자체에 별도 PM review를 추가하지 않는다.

### Raw/API contract

- `POST /api/tasks`의 최소 필수 client field는 기존처럼 `title`, `objective`다.
- 서버 생성 task는 `status: "queued"`, 생성 시각, source, brief artifact를 가진다.
- optional `project_ref`는 §2 validation을 통과할 때만 기록한다.
- client는 task ID, `status`, stages, gate/final review/dispatch/result, server-resolved actor, timestamps를 지정할 수 없다.
- response `201`의 의미는 `brief_created`뿐이다. response/UX copy는 `브리프 저장됨 · 진입 판단 대기`를 사용하며 `dispatch`, `승인`, `실행 시작`, `완료`를 의미하는 표현을 사용하지 않는다.
- `queued` 또는 기존 `dispatch_ready`가 존재하더라도 Dashboard composer가 worker dispatch API를 호출해서는 안 된다. dispatch는 기존 canonical 운영 경로와 권한을 그대로 사용한다.
- title/objective가 없거나 유효하지 않은 `project_ref`는 `422`이며 partial task/brief artifact를 남기지 않는다.

### Migration/compatibility 영향

- 현 `write_task_brief()`가 수행하는 생성 semantics(`queued`, brief JSON/Markdown, 기존 pipeline defaults)를 유지한다.
- 별도 `submitted_pending_pm_review` intermediate state를 새 brief에 도입하지 않는다. 이는 기존 integration이 queued task를 조회하는 계약을 깨기 때문이다.
- 1영역 UX는 mode를 시각적으로 분리하고, additional instruction submit 결과와 새 brief 생성 결과를 동일 success copy로 합치지 않는다.

## 5. 결정 4 — Mission Control deadline/SLA source는 v1.2에서 도입하지 않는다

### 결정 및 근거

v1.2에서는 deadline/SLA raw source, policy owner, timezone, breach calculation, exception/override audit 계약이 없다. 이를 Mission Control 정렬용으로만 성급히 추가하면 free-text date, filesystem mtime, task created_at/updated_at, watcher freshness를 deadline으로 오해할 위험이 크다.

따라서 v1.2 기본 정렬은 PRD대로 `blocker → decision → unknown → reviewable`, 동일 group 내에는 explicit raw priority와 actionable evidence를 사용한다. deadline/SLA 기반 승격은 수행하지 않는다.

### API/projection contract

- `/api/dashboard-console` v2는 `deadline`, `sla`, `breach`, `aging`을 계산·추론·정렬 key로 반환하지 않는다.
- raw task에 임의 deadline-like legacy field가 있더라도 v1.2 Mission ordering에 사용하지 않는다. 원문은 task detail raw evidence에서만 확인할 수 있다.
- generated/observed/updated time은 freshness/evidence 표시에만 사용하며 SLA/기한 의미를 부여하지 않는다.
- future version에서만 explicit policy source, timezone, business calendar, owner, immutable policy version, override reason/evidence를 포함한 별도 contract를 제안할 수 있다.

### Migration/compatibility 영향

- 현재 priority 및 evidence 기반 Mission Control의 안정성을 보존한다.
- legacy metadata를 파싱하지 않으므로 backward incompatibility가 없다.
- SLA 표시가 필요한 사용자 요구는 v1.2 launch blocker가 아니라 후속 discovery/Seed 대상이다.

## 6. 구현자 체크리스트

Developer는 아래를 만족해야 한다.

1. project grouping에서 title/path/task-id prefix/최근 선택을 사용하지 않는 negative test를 추가한다.
2. missing/malformed `project_ref`가 raw task를 mutate하지 않고 `unassigned`로 투영되는 test를 추가한다.
3. `additional_instruction` submit 전후 target task의 status/stages/gates/pm_final_review/dispatch가 byte-for-byte 의미상 동일한 test를 추가한다.
4. decision writer의 PM auth, idempotency, stale version, decision evidence ID 요구를 테스트한다.
5. `new_task_brief` 201 생성이 queued task를 만들지만 dispatch endpoint를 호출하지 않는 test를 추가한다.
6. Mission ordering이 explicit priority/evidence만 사용하며 title/free-text/created_at을 SLA로 쓰지 않는 test를 추가한다.

Verifier는 authority boundary와 parent non-mutation을 독립 검토한다. QA는 pending instruction, malformed project ref, new-brief submit, no-deadline ordering을 browser/API fixture로 확인한다.

## 7. 보류 항목과 owner

| 보류 항목 | 상태 | Owner | 재개 조건 |
|---|---|---|---|
| Project registry entity/lifecycle 및 registry↔task binding migration | v1.2 제외 | PM + Developer | cross-task canonical project metadata, lifecycle/editor 요구가 명시되고 Seed/AC가 승인될 때 |
| PM decision writer의 실제 인증·운영 UI | v1.2 backend contract 우선 | Developer, PM 검토 | PM-only runtime authorizer/운영 surface가 확정될 때 |
| SLA/deadline 정책 | v1.2 제외 | PM | business timezone, calendar, owner, override/audit 기준이 명시된 별도 Seed가 있을 때 |
| 기존 task의 project_ref backfill | 하지 않음 | 없음 | 개별 task의 명시 evidence가 수집되고 별도 migration 승인 시에만 |

## 8. 비가역/안전 경계

- 이 결정은 task raw, instruction sidecar, PM decision evidence의 source-of-truth 경계를 정의할 뿐, 자동 dispatch/approval/completion을 허용하지 않는다.
- Dashboard 4-pane은 read/navigation surface를 유지한다. write는 명시적 composer intake 및 PM-only decision writer로만 제한한다.
- 어떤 migration도 project identity 또는 workflow 상태를 제목·경로·자유 텍스트로 추론해서는 안 된다.

# Hermes Agent Operations 4대 개선 선별 적용 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Orca runtime을 도입하지 않고 lifecycle 상태 hook, coding-task worktree 격리, provider usage/rate-limit 표시, remote worker reconnect/hibernation의 네 개념만 현재 HermesPM + Operations Dashboard에 최소·가역적으로 적용한다.

**Architecture:** Operations Dashboard와 file-backed artifacts를 canonical source of truth로 유지한다. Hermes의 기존 observer hook과 Kanban workspace 계약을 재사용하고, 수집기는 최소 metadata만 원자적으로 기록하며, Dashboard는 버전된 snapshot을 읽기 전용 projection한다. 원격 worker는 상시 socket 대신 기존 inbox·SSH pull·짧은 probe를 사용하고, 모든 write/배포 전환은 PM·verifier·Raphael gate로 분리한다.

**Tech Stack:** Python 3 표준 라이브러리, Hermes plugin hooks, Hermes Kanban SQLite/worktree, JSON v1 schemas, existing `operations_dashboard_server.py` HTTP server, vanilla JS/CSS Dashboard, SSH/SCP/Tailscale, launchd/Windows Task Scheduler, `unittest`.

---

## 0. 계획 요약과 결정

### 0.1 결론

- **Orca 전체 설치: 보류/제외.** Electron, headless server, mobile runtime, Orca runtime 및 전량 대화 payload 수집을 도입하지 않는다.
- **지금 적용:**
  1. coding task에 대한 worktree admission policy와 dirty-main 차단 규칙
  2. Hermes observer hook 기반 최소 lifecycle state snapshot MVP
- **다음 적용:**
  3. remote worker reconnect/hibernation 상태기계
  4. 안전한 local evidence만 사용하는 provider usage/rate-limit projection
- **보류:** provider가 제공하지 않는 quota/remaining/reset의 추정, 자동 merge/cleanup, core hook 추가, 장기 socket, 원격 wake를 위한 별도 daemon, profile 간 raw payload 공유.

### 0.2 우선순위 변경 근거

요청의 권장 순서는 lifecycle → worktree → reconnect → usage였지만, 실제 저장소는 `main`에 13개 tracked modified와 다수 untracked 후보가 있고 Dashboard v1.1/v1.2 및 Kanban lifecycle 후보가 같은 파일을 공유한다. 따라서 **Gate 0(worktree admission policy)을 구현 코드를 쓰기 전 운영 선행조건으로 적용**한 뒤 lifecycle MVP를 시작한다. 기능 rollout 순서는 여전히 lifecycle → reconnect → usage를 유지한다.

### 0.3 성공 지표

- coding implementation card 중 `workspace_kind=worktree` 또는 승인된 예외 비율: 100%.
- main dirty 상태에서 새 coding card가 `dir=/home/raphael/myproject`로 dispatch되는 건수: 0.
- lifecycle event에 prompt/response/tool args/result/credential이 포함되는 건수: 0.
- lifecycle writer 실패가 agent/tool 실행을 실패시키는 건수: 0(fail-open).
- 같은 event fingerprint 중복 저장: 0.
- stale 판정 false-positive: 24시간 shadow observation에서 0.
- remote duplicate runner가 같은 brief를 동시에 claim하는 건수: 0.
- network failure를 quota/rate-limit으로 표시하는 건수: 0.
- provider가 제공하지 않은 remaining/reset을 숫자로 추정하는 건수: 0.

## 1. 사실, 가정, 제약

### 1.1 확인된 사실

1. `/home/raphael/myproject`는 `main`이며 현재 13개 tracked modified와 Dashboard/Kanban 관련 untracked 후보가 공존한다.
2. `DASHBOARD-REVIEW-MANIFEST.md:11-20`은 shared server/UI overlap 때문에 현재 dirty tree를 후보별로 안전하게 merge할 수 없고 isolated branch/worktree 재구성이 필요하다고 명시한다.
3. Operations raw task authority는 `operations/briefs/*.json`이고 Dashboard projection은 `operations_dashboard_server.py`, `operations_dashboard_projection.py`, `operations_dashboard_console.py`가 구성한다.
4. `operations_sync.py:25,119-166`은 MacBook log 최근 250줄을 SSH로 읽어 `operations/worker-status.json`에 rate-limit 상태를 기록한다. 현재 worker 식별이 사실상 `verify-co`에 편향되고, 정상 completion 로그가 보이면 map에서 제거한다.
5. `operations_dashboard_server.py:436-459`는 config availability와 `worker-status.json` runtime status를 단순 override한다. TTL, schema validation, source health, stale 구분이 없다.
6. `operations_dashboard_server.py:826-830,990-1022,1421-1457`은 `/api/dashboard-console`, `/api/overview`, `/api/agents`, `/api/workers`, `/api/health`를 제공한다.
7. `operations_dashboard_projection.py:43-103`은 sync/watchdog evidence에 freshness와 stale을 이미 적용한다. 새 상태도 이 projection 패턴을 재사용해야 한다.
8. `operations/kanban/registry.py`, `monitor.py`, `reconciler.py`와 `tests/test_kanban_lifecycle.py`가 untracked 후보로 존재한다. monitor/reconciler는 workflow gate·edge·heartbeat authority이며, 새 agent lifecycle state의 owner가 아니다.
9. Hermes core `hermes_cli/plugins.py:135-215`에는 `pre/post_tool_call`, `pre/post_llm_call`, `pre/post_api_request`, `api_request_error`, session, approval, Kanban lifecycle observer hooks가 이미 있다.
10. `agent/conversation_loop.py:363-388`은 session start hook과 Nous credits seed를 fail-open으로 수행한다.
11. `model_tools.py:980-1022`의 `post_tool_call`에는 duration/status/error metadata가 있으나 args/result도 전달된다. 새 plugin은 callback 인자를 받아도 raw args/result를 직렬화하면 안 된다.
12. `tools/approval.py:96-167`은 approval hook observer를 제공한다. waiting_approval은 pre/post approval 사이의 상태로 계산 가능하다.
13. Hermes Kanban core `hermes_cli/kanban_db.py:2390-2684`는 `workspace_kind`, `workspace_path`, `branch_name`, `project_id`를 이미 지원한다. project-linked task는 `<repo>/.worktrees/<task-id>` 및 deterministic branch를 만들 수 있다.
14. dispatcher는 `hermes_cli/kanban_db.py:8084-8232`에서 task workspace와 branch를 worker env/cwd에 주입한다. 즉 새 worktree runtime을 만들 필요 없이 admission policy와 gate가 핵심이다.
15. Hermes session DB는 `hermes_state.py`에서 token/model/provider/cost usage를 이미 보존하고 `insights`가 읽는다. Nous provider에는 `agent/credits_tracker.py`의 검증된 credit header 계약이 있다.
16. OpenAI Codex/Claude/OpenRouter의 quota/remaining/reset은 동일한 공통 로컬 계약으로 항상 제공되지 않는다. 없는 값은 `unknown`이어야 한다.
17. MacBook runner는 `tmp_worker_runner.py`의 inbox→workspace→result 구조이며 transient 오류는 brief를 남겨 다음 주기에 재시도한다. local runner도 `hermes_local_runner.py:1-16,193-258`에서 동일한 주기 실행·flock·retry 패턴을 사용한다.
18. `operations/config/workers.json`에는 researcher-co, writer-co, verify-co, researcher_agent, analyst-co 원격 SSH와 HermesResearcher local-inbox가 정의되어 있다.
19. `ensure-agent-hub-services.sh`는 Dashboard health 실패 2회 후 tmux를 재시작하고 PM gateway를 기동한다. Windows/WSL recovery 경로는 이번 범위에서 변경 금지다.
20. 현재 Kanban에는 Dashboard v1.1/v1.2, lifecycle reconciler/monitor/core, PM monitor 보완 작업이 active/todo/blocked로 남아 있어 shared file 수정 충돌 가능성이 높다.

### 1.2 명시적 가정

- **A1:** Operations Dashboard file-backed 상태가 사용자 운영 화면의 canonical projection이며 Hermes native dashboard로 교체하지 않는다.
- **A2:** profile plugin 배포는 각 profile의 `HERMES_HOME` 격리를 존중한다. default profile의 plugin 디렉터리를 다른 profile이 암묵적으로 공유한다고 가정하지 않는다.
- **A3:** lifecycle snapshot은 운영 보조 evidence이며 Kanban task status, workflow registry, raw brief stage를 덮어쓰지 않는다.
- **A4:** MacBook launchd 정의 파일은 현재 저장소에 없으므로 구현 전 remote host read-only discovery가 필요하다.
- **A5:** provider quota API가 공식적으로 노출되지 않으면 token usage와 최근 rate-limit 관찰만 표시한다.
- **A6:** commit/push/deploy/restart/cron resume/Discord send는 별도 승인 카드 없이는 수행하지 않는다.

### 1.3 비목표

- Orca UI/runtime/network stack 복제.
- prompt, assistant response, tool args/result, command, file body, credential 저장.
- Dashboard를 실시간 trace viewer로 만들기.
- Kanban DB를 Operations task JSON으로 대체하거나 반대로 합치기.
- 자동 merge, force cleanup, branch 삭제, dirty main 수정.
- provider quota scraping, 브라우저 로그인 세션 scraping, token decode.
- MacBook/WSL에 상시 bidirectional socket 추가.

## 2. Authority와 경계

### 2.1 Canonical source hierarchy

| 영역 | Canonical source | 보조 evidence | 금지 |
|---|---|---|---|
| Operations task/stage | `operations/briefs/*.json` | result/verification sidecar | lifecycle snapshot이 stage 변경 |
| Kanban task/gate | `~/.hermes/kanban.db` + versioned workflow registry | monitor state/outbox | Dashboard projection이 DB write |
| Agent runtime state | 신규 `operations/runtime/agent-state.v1.json` | append-bounded event ring | `worker-status.json` 무검증 override |
| Remote worker health | 신규 `operations/runtime/worker-runtime.v1.json` | short probe evidence | heartbeat만으로 healthy 확정 |
| Provider usage | 신규 `operations/runtime/provider-usage.v1.json` | Hermes state DB/result envelopes/official headers | missing quota 추정 |
| Dashboard view | projection 결과 | last-known-good cache | UI가 raw authority 변경 |

### 2.2 파일 ownership

- `operations/worker-status.json`은 기존 remote log-derived compatibility artifact로 유지한다.
- 새 runtime state는 `operations/runtime/*.v1.json`으로 분리한다.
- `operations/kanban/workflows.v1.json`은 workflow lifecycle 전용이며 agent lifecycle hook이 쓰지 않는다.
- Dashboard server/projection은 새 파일을 읽기만 한다.
- lifecycle plugin은 Kanban DB, brief, workflow registry를 수정하지 않는다.

## 3. Enhancement A — Lifecycle 상태 hook MVP

### 3.1 목표

Hermes profile별 최소 runtime state를 file-backed snapshot으로 안전하게 투영해 Dashboard에서 idle/queued/thinking/using_tool/waiting_approval/blocked/completed/stale을 구분한다.

### 3.2 비목표

- 대화/도구 payload trace.
- 모든 내부 token stream을 실시간 표시.
- hook 실패로 agent 실행 차단.
- lifecycle state로 Kanban task status 변경.

### 3.3 구조

```text
Hermes observer hook
  -> profile-local callback
  -> bounded metadata normalizer
  -> per-profile spool (atomic replace, 0600)
  -> short-lived consolidator (lock + dedupe)
  -> operations/runtime/agent-state.v1.json
  -> Dashboard projection/API/UI
```

권장 source package는 저장소의 `operations/lifecycle/`에 두고, 배포 시 각 profile plugin 디렉터리에 동일 version/hash를 설치한다. project plugin은 `HERMES_ENABLE_PROJECT_PLUGINS` opt-in이 필요하므로 무조건 활성이라고 가정하지 않는다. shared source를 직접 concurrent-write하지 않고 profile-local spool 후 consolidator가 합친다.

### 3.4 최소 event schema

```json
{
  "schema_version": 1,
  "event_id": "sha256(profile|session|task|state|tool_category|observed_at_bucket)",
  "profile": "developer",
  "session_id": "opaque-id",
  "task_id": "t_xxxxxxxx",
  "state": "using_tool",
  "observed_at": "2026-08-03T12:00:00+09:00",
  "tool_category": "file",
  "duration_ms": 120,
  "approval_wait": false,
  "source_hook": "post_tool_call"
}
```

제약:
- event 직렬화 상한 2 KiB, ring 최대 profile당 100건.
- `tool_name`은 allowlist category(`file`, `terminal`, `web`, `browser`, `kanban`, `other`)로 축약한다.
- session/task id는 opaque correlation ID만 허용한다.
- args/result/error_message/command/path/prompt/response/model request body/credential은 금지한다.
- unknown field는 writer가 버리고 reader는 fail-closed `unknown` 처리한다.

### 3.5 state model

| 상태 | 진입 근거 | 종료/전이 | TTL |
|---|---|---|---|
| `idle` | session 없음 또는 completed 후 grace | 새 task/session | 10분 projection 기본 |
| `queued` | `kanban_task_claimed` 또는 brief dispatch evidence | session start/blocked | 15분 |
| `thinking` | `pre_llm_call`/`pre_api_request` | tool start/post LLM/error | 5분 |
| `using_tool` | `pre_tool_call` | post_tool/approval/timeout | category별 max 15분 |
| `waiting_approval` | `pre_approval_request` | post approval | 30분 |
| `blocked` | Kanban blocked 또는 terminal policy failure | unblock/new generation | authority-linked, TTL 없음 |
| `completed` | Kanban completed/session completed | idle grace 후 idle | 10분 |
| `stale` | last event가 해당 state TTL 초과 | 새 evidence | projection-only |

우선순위: `blocked > waiting_approval > using_tool > thinking > queued > completed > idle`. `stale`은 원래 state를 잃지 않고 `{state:"stale", stale_from:"using_tool"}`로 표시한다.

### 3.6 profile isolation/deployment

- 대상: default, pm, planner, developer, qa, researcher, verifier, designer.
- 각 profile은 자기 `HERMES_HOME` 아래 spool만 쓴다.
- profile name은 plugin context의 `profile_name` 또는 `HERMES_PROFILE` allowlist로 결정한다. path에서 추측하지 않는다.
- source package version/hash를 manifest에 기록한다.
- canary 순서: planner → developer → verifier → pm → 나머지 → default.
- 한 profile 실패는 다른 profile state와 agent execution에 영향이 없어야 한다.

### 3.7 dedupe, atomicity, fail-open

- write는 temp file 생성→flush→`os.replace`; 가능하면 mode 0600.
- process 간 lock timeout은 100 ms 이하. 실패 시 event drop count만 증가시키고 agent flow는 계속한다.
- 동일 fingerprint는 TTL window 안에서 한 번만 저장한다.
- corrupt spool은 overwrite하지 않고 `.corrupt.<timestamp>` 격리 후보로 표시하되 자동 삭제하지 않는다.
- consolidator failure는 `source_health=degraded`이며 이전 LKG snapshot을 유지한다.

### 3.8 Dashboard projection

- `/api/overview`와 `/api/agents`에 additive `runtime_state`만 추가한다.
- 신규 `/api/runtime-status`는 schema v1 snapshot을 read-only 반환하는 후보이며 기존 route 변경보다 선호한다.
- UI는 state, freshness, profile, approval wait, coarse tool category만 표시한다.
- snapshot stale/corrupt/missing은 `unknown` 또는 `stale`; `idle`로 위장하지 않는다.

## 4. Enhancement B — HermesDeveloper worktree isolation

### 4.1 목표

coding task만 isolated worktree에서 실행하고 developer→verifier/QA→PM merge 경계를 candidate hash로 고정해 dirty main과 후보 혼합을 방지한다.

### 4.2 적용 조건

다음 중 하나면 worktree 필수:
- assignee가 `developer`이고 source/config/test/script를 수정한다.
- reviewer/QA가 mutable candidate를 재현하거나 patch를 적용해야 한다.
- task body에 code, fix, implementation, refactor, migration이 명시된다.

다음은 기본 `scratch` 또는 명시 `dir`:
- planner/pm/researcher의 문서·조사만 수행.
- verifier의 read-only external review.
- 운영 artifact를 지정 디렉터리에 쓰는 non-code task.

### 4.3 admission policy

```text
if coding_task:
  require workspace_kind == worktree
  require absolute workspace_path under <repo>/.worktrees/<task-id>
  require deterministic branch
  require clean base SHA recorded
else:
  do not force worktree
```

현재 core가 project-linked worktree와 branch를 지원하므로 신규 worktree manager를 만들지 않는다. 우선 PM card creation template/linter에 policy를 넣고, core hard gate는 운영 검증 후 별도 upstream card로 고려한다.

### 4.4 candidate contract

```json
{
  "schema_version": 1,
  "task_id": "t_xxxxxxxx",
  "repo_root": "/home/raphael/myproject",
  "workspace_path": "/home/raphael/myproject/.worktrees/t_xxxxxxxx",
  "branch": "agent-hub/t_xxxxxxxx",
  "base_sha": "40-hex",
  "head_sha": "40-hex-or-null",
  "diff_sha256": "hex",
  "dirty_paths": ["allowlisted/path"],
  "tests": [{"command": "...", "exit_code": 0}],
  "created_at": "ISO-8601"
}
```

### 4.5 create→review→merge 경계

1. PM creates coding card with project/worktree fields; developer does not self-assign dir main.
2. Developer records base SHA before edit and emits candidate manifest after tests.
3. Verifier reads exact workspace/branch/base/diff hash; no review by title or mutable shared dir.
4. QA tests same candidate hash. hash drift invalidates previous verdict and creates new generation.
5. PM confirms verifier PASS, QA PASS, no dirty-main contamination.
6. Raphael explicitly approves commit/push/merge/deploy card.
7. cleanup/GC is separate post-merge card; force removal forbidden by default.

### 4.6 rollback/cleanup

- pre-merge rollback: abandon candidate worktree; main untouched.
- post-merge rollback: dedicated revert commit, not history rewrite.
- cleanup prerequisites: merged/abandoned decision, artifacts copied, no uncommitted file, no active worker, PM approval.
- `git worktree prune`/remove, branch delete는 별도 card와 evidence가 있어야 한다.

## 5. Enhancement C — Provider usage/rate-limit 표시

### 5.1 목표

provider별로 안전하게 관찰 가능한 usage/limit/reset/최근 timeout을 구분해 표시하고, 미제공 정보는 `unknown`으로 유지한다.

### 5.2 source matrix

| Provider/source | 안전하게 사용 가능 | 제한 |
|---|---|---|
| Hermes session DB | model/provider별 token, API call, cost status | quota/remaining 아님 |
| Nous credit headers | validated remaining/cap/used fraction/paid access/as-of | Nous 전용 |
| result envelopes | worker run usage, model, timestamps | runner가 제공한 범위만 |
| OpenAI Codex OAuth/API | response headers/error metadata가 노출될 때 reset/retry-after | 계정 quota 전체를 추정하지 않음 |
| Anthropic/Claude | CLI/API structured usage 및 429 retry/reset가 노출될 때 | 웹 계정 session limit scraping 금지 |
| OpenRouter | structured token/cost 및 공식 rate-limit header가 있을 때 | key/authorization 원문 금지 |
| runner logs | timeout/429 발생 시각과 coarse category | 원문 message를 Dashboard에 노출하지 않음 |

### 5.3 schema

```json
{
  "schema_version": 1,
  "generated_at": "ISO-8601",
  "ttl_seconds": 300,
  "providers": {
    "openai-codex": {
      "usage": {"input_tokens": 0, "output_tokens": 0, "window": "session-db"},
      "limit": {"value": null, "unit": null, "status": "unknown"},
      "remaining": {"value": null, "status": "unknown"},
      "reset_at": null,
      "last_rate_limit_at": null,
      "last_timeout_at": null,
      "health": "unknown",
      "source": ["hermes_state"],
      "observed_at": "ISO-8601",
      "errors": []
    }
  }
}
```

### 5.4 판정 기준

- HTTP 429, explicit `rate_limit`, `session limit`, official retry/reset header → `rate_limited`.
- connect timeout, DNS, SSH/Tailscale unreachable, 5xx without quota signal → `network_or_provider_error`, quota는 unknown.
- local process timeout → `worker_timeout`, quota는 unknown.
- remaining=0이어도 provider 계약상 access disabled 근거가 없으면 `depleted`로 단정하지 않는다.
- last event가 TTL을 넘으면 `stale`; 이전 숫자를 current처럼 표시하지 않는다.

### 5.5 polling/cache

- local session DB aggregation: 5분.
- remote result/log pull piggyback: 기존 sync 주기, 별도 상시 process 없음.
- provider network probe: 기본 비활성. 공식·저비용 endpoint와 Raphael 승인 시만 15분 이상.
- atomic snapshot + LKG, collector별 failure namespace(`collector.local_db`, `collector.remote_log`, `provider.*`).

### 5.6 UI

provider card는 `사용량`, `한도`, `남음`, `reset`, `최근 제한`, `최근 timeout`, `freshness`, `source`를 분리한다. 숫자 없음은 `알 수 없음`; 0으로 렌더하지 않는다. credential/key/account ID/raw error는 표시하지 않는다.

## 6. Enhancement D — Worker reconnect/hibernation

### 6.1 목표

MacBook launchd worker와 WSL/local runner가 inbox 없을 때 저비용 idle/hibernate 상태를 유지하고, brief 도착 시 bounded wake/retry하며, 연결 단절·중복 runner·result pull 실패를 구분한다.

### 6.2 상태 모델

```text
unknown -> probing -> idle -> running -> result_pending -> idle
                    \-> hibernating -> wake_pending -> probing
probing/running/result_pending -> backoff -> probing
backoff(max attempts) -> cooldown -> degraded -> escalation
```

| 상태 | 의미 | evidence |
|---|---|---|
| `idle` | runner healthy, inbox 0, active claim 0 | recent process/lock probe + inbox count |
| `hibernating` | 주기 scheduler는 살아 있으나 worker process 없음 | launchd/task scheduler state + inbox 0 |
| `wake_pending` | brief가 durable inbox에 있고 다음 scheduler tick 대기 | brief file + mtime |
| `running` | exact brief claim을 한 단일 runner | lease/lock + pid start evidence |
| `result_pending` | remote result 작성됐으나 hub pull/ack 미완료 | result sidecar + no hub ack |
| `backoff` | transient SSH/provider/network 실패 | failure class + next_attempt_at |
| `cooldown` | max bounded attempts 도달 | attempts/window |
| `degraded` | probe 불가 또는 evidence conflict | heartbeat와 probe 불일치 |

### 6.3 heartbeat와 probe 분리

- heartbeat: runner가 마지막으로 자신을 기록한 값. freshness evidence일 뿐 healthy 확정이 아니다.
- probe: SSH/Tailscale/launchd/lock/inbox/result를 짧게 확인한 현재 관찰.
- heartbeat fresh + probe fail → `degraded`, `healthy` 아님.
- probe success + heartbeat stale + no inbox → `hibernating` 가능.

### 6.4 duplicate prevention

- 기존 local `flock`과 remote runner lock을 유지한다.
- brief claim은 `(task_id, worker_key, attempt)` 단위 lease file로 명시한다.
- lease에는 owner_id, acquired_at, expires_at, source brief digest만 저장한다.
- stale lease reclaim은 실제 pid/probe 부재와 grace를 모두 확인한 뒤에만 한다.
- 같은 result envelope가 있으면 idempotent skip; hash conflict는 overwrite 금지, conflict artifact로 남긴다.

### 6.5 bounded backoff

권장: 15s, 30s, 60s, 120s, 300s; jitter ±20%; 5회 후 15분 cooldown. provider rate-limit에 공식 reset이 있으면 reset 전 재시도하지 않는다. SSH/Tailscale failure와 provider limit counter는 분리한다.

### 6.6 적용 범위

- remote: researcher-co, writer-co, verify-co, analyst-co, researcher_agent.
- local: HermesResearcher.
- HermesDeveloper Kanban worker는 durable Kanban dispatcher가 owner이므로 이 remote inbox state machine에 넣지 않는다.

### 6.7 result pull recovery

- remote result write는 temp→atomic rename.
- hub pull 후 digest 확인 및 local ack sidecar 생성.
- SSH 복구 시 `result_pending`부터 먼저 pull하고 새 dispatch보다 우선한다.
- partial/corrupt result는 completed로 승격하지 않는다.

## 7. 중복·충돌 분석

### 7.1 existing Kanban lifecycle와의 경계

| 기존 후보 | owner | 새 개선과 관계 | 충돌 회피 |
|---|---|---|---|
| `operations/kanban/registry.py` | active workflow/gates | agent lifecycle와 이름 유사 | 별도 namespace/file, DB mutation 금지 |
| `operations/kanban/monitor.py` | workflow transition/heartbeat | completed/blocked 관찰 일부 중복 | Kanban 상태는 authority input으로만 참조 |
| `operations/kanban/reconciler.py` | edge/promote/close write | lifecycle hook은 write하면 안 됨 | reconciler 단독 DB writer 유지 |
| `operations_watchdog.py` | Operations brief stall | runtime stale와 일부 중복 | watchdog=task/stage, runtime=process/session |
| PM monitor 보완 cards | Kanban exception alerts | provider/network alert 중복 | namespace와 fingerprint 분리 |

### 7.2 Dashboard v1/v2 후보와 충돌

- `operations_dashboard_server.py`, `operations_dashboard_projection.py`, `operations_dashboard/app.js`, `styles.css`는 여러 dirty 후보가 공유한다.
- 현재 shared tree에서 새 기능을 직접 얹지 않는다.
- 각 enhancement는 isolated worktree에서 clean baseline으로 재구성하고, additive route/schema부터 검토한다.
- v1/v2 semantic contract가 확정되기 전 UI integration은 hold한다.
- `DASHBOARD-REVIEW-MANIFEST.json/.md` snapshot을 candidate attribution authority로 사용한다.

### 7.3 현재 Kanban 충돌 gate

다음 lane들이 끝나거나 PM이 명시적으로 supersede하기 전 shared file implementation 금지:
- lifecycle registry/reconciler/monitor 및 core hold/migration lock 보완.
- Dashboard v1.1 projection/follow-up/artifact producer/viewer.
- Dashboard v1.2 console projection/API/shell/QA.
- PM monitor scoped timeout 보완.

## 8. Dependency graph와 rollout

```text
G0 dirty-tree inventory + candidate isolation + PM approval
  -> B0 worktree admission policy (운영 선행조건)
  -> A1 lifecycle schema/privacy tests
      -> A2 profile-local writer shadow mode
      -> verifier privacy/safety gate
      -> A3 consolidator + read-only API
      -> Dashboard UI canary
  -> D1 remote state schema/probe fixtures
      -> D2 one worker canary(researcher-co)
      -> D3 remaining remote + local runner
  -> C1 local usage collector
      -> C2 rate-limit classifiers
      -> C3 Dashboard provider cards
각 단계 -> PM review -> verifier PASS -> Raphael rollout approval
```

### Phase 0 — Gate/격리

- dirty/untracked manifest refresh.
- active Kanban overlap 확인.
- coding card worktree policy 시행.
- implementation dispatch 금지 유지.

### Phase 1 — Lifecycle shadow MVP

- writer는 profile-local spool만 기록.
- Dashboard 미노출 24시간 observation.
- forbidden key/size/dedupe/TTL/fail-open verifier 검토.

### Phase 2 — Lifecycle read-only projection

- consolidator와 API만 canary.
- UI는 feature flag 뒤 planner/developer 두 profile부터.

### Phase 3 — reconnect/hibernation

- fixture와 fake SSH로 state machine 검증.
- researcher-co 단일 canary 후 확장.
- 기존 launchd/Task Scheduler 정의는 승인 전 변경 금지.

### Phase 4 — usage/rate-limit

- local DB/result envelope부터.
- provider-specific 공식 evidence만 점진 추가.
- unknown-first UI.

## 9. Feature flag와 rollback

| Flag | 기본값 | 역할 | rollback |
|---|---:|---|---|
| `OPS_RUNTIME_LIFECYCLE_ENABLED` | `0` | hook writer | 0으로 전환, spool 보존 |
| `OPS_RUNTIME_PROJECTION_ENABLED` | `0` | server read projection | route가 unavailable 반환 |
| `OPS_WORKTREE_POLICY_MODE` | `report` | `report|enforce` | report로 복귀 |
| `OPS_REMOTE_RUNTIME_ENABLED` | `0` | worker state collector | 기존 runner 동작 유지 |
| `OPS_PROVIDER_USAGE_ENABLED` | `0` | usage collector/projection | card 숨김, snapshot 보존 |

rollback은 data deletion을 하지 않는다. writer/collector/UI를 끄고 이전 LKG와 evidence를 보존한다. schema reader는 unknown version을 무시한다.

## 10. 보안·개인정보·network/resource 위험

| 위험 | 영향 | 완화 | gate |
|---|---|---|---|
| hook args/result 유출 | 비밀·PII 노출 | strict allowlist normalizer, forbidden-key tests | verifier blocker 0 |
| profile cross-write | 상태 오귀속 | profile-local spool, profile allowlist | canary |
| concurrent JSON corruption | Dashboard 오판 | lock + atomic replace + LKG | fault test |
| stale을 idle로 오인 | 작업 유실 | explicit stale/unknown | QA |
| dirty main 후보 혼합 | rollback 불가 | worktree enforce + candidate hash | PM |
| automatic cleanup data loss | evidence 손실 | separate cleanup gate, no force | Raphael |
| SSH probe storm | Mac/WSL resource 사용 | piggyback, backoff, TTL | 24h observation |
| long-lived endpoint 공격면 | network 노출 | 기존 HTTP/SSH만, new socket 없음 | verifier |
| rate-limit 오분류 | 잘못된 재시도/중단 | classifier namespace, unknown-first | tests |
| provider credential 노출 | 계정 침해 | no headers/token/raw error storage | security review |
| duplicate runner | 비용·결과 overwrite | flock/lease/digest conflict | canary |

## 11. 테스트와 관찰 가능성

### 11.1 unit/contract

- schema version, enum, required/forbidden fields, 2 KiB bound.
- fingerprint dedupe, atomic replace, lock timeout fail-open.
- TTL/stale precedence and unknown-version behavior.
- coding vs non-coding worktree classifier.
- candidate base/head/diff binding and drift invalidation.
- provider 429/network timeout/5xx/local timeout classification.
- remote state transition, lease expiry, duplicate prevention, result pull recovery.

### 11.2 integration

- fake profile hooks write only their spool.
- consolidator merges eight profiles without cross-contamination.
- malformed/corrupt/missing snapshot does not break `/api/overview`.
- lifecycle hook does not mutate brief/Kanban DB/workflow registry.
- fake SSH interruption follows bounded backoff and recovers result first.

### 11.3 regression

```bash
python3 -m unittest tests.test_kanban_lifecycle
python3 -m unittest tests.test_operations_watchdog
python3 -m unittest tests.test_dashboard_projection tests.test_dashboard_api_contracts tests.test_dashboard_static_contract
python3 -m unittest test_operations_sync
python3 -m py_compile operations_dashboard_server.py operations_dashboard_projection.py operations_sync.py hermes_local_runner.py tmp_worker_runner.py
node --check operations_dashboard/app.js
git diff --check
```

구현 시 각 phase의 새 test module을 위 명령에 추가한다. browser rollout은 1440/768/390 및 keyboard/freshness/unknown states를 검증한다.

### 11.4 관찰 evidence

각 canary는 `operations/evidence/runtime-four-enhancements/<phase>/<timestamp>/`에 다음만 기록한다.
- schema snapshot(redacted), SHA-256, file size.
- test command/exit code/count.
- feature flag state.
- stale/dedupe/drop/conflict counters.
- candidate base/head/diff hash.
- raw prompt/tool payload/credential은 기록하지 않는다.

## 12. Gate와 의사결정 권한

### 12.1 PM gate

- exact candidate/worktree/changed-file allowlist 확인.
- active Kanban overlap 또는 supersession 확인.
- phase scope와 forbidden scope 확인.
- verifier/QA card가 producer에 종속되어 deadlock하지 않도록 독립 생성.

### 12.2 Verifier gate

- privacy forbidden-field scan.
- authority non-mutation 확인.
- fail-open, atomicity, dedupe, TTL, stale 판정.
- candidate hash binding 및 test evidence 재실행.
- blocker 0일 때만 PASS.

### 12.3 Raphael 승인 gate

별도 승인 필요:
- `report`→`enforce` 전환.
- plugin을 default/pm 등 전체 profile에 배포.
- launchd/Task Scheduler 변경.
- provider network probe 활성화.
- commit/push/merge/deploy/restart/cron resume/Discord send.
- worktree cleanup/branch delete.

## 13. Open questions

1. profile plugin source를 repo-managed package + profile별 install로 할지, opt-in project plugin으로 할지 PM이 선택해야 한다. 권고는 전자다.
2. lifecycle consolidator를 기존 `operations_sync.py`에 piggyback할지 별도 short-lived script로 둘지 결정 필요. 권고는 별도 script다.
3. `operations/worker-status.json`을 deprecate할 시점과 compatibility window가 필요하다. 권고는 두 release 병행 read다.
4. MacBook launchd plist의 실제 label/interval/path는 remote read-only discovery 후 확정해야 한다.
5. provider usage 집계 범위를 active profile별로 분리할지 전체 합산할지 결정 필요. 권고는 profile/provider 이중 grouping, UI 기본은 provider 합계다.
6. usage cost를 표시할 때 actual/estimated/unknown label을 어느 수준까지 노출할지 PM 결정 필요.
7. Dashboard v1.1/v1.2 후보 중 어느 clean baseline을 integration target으로 삼을지 기존 review manifest 해소 후 결정해야 한다.

## 14. 권장 후속 작업

1. `pm`: 본 계획과 작업지시 검토, overlap lane/supersession 및 Phase 0 승인.
2. `developer`: 승인 후 isolated worktree에서 Phase 0/B0 policy + A1 schema/tests부터 수행.
3. `verifier`: privacy/authority/worktree binding 독립 검토.
4. `qa`: API/UI 및 remote state browser/fixture acceptance.
5. `pm`: canary evidence 종합 후 Raphael rollout decision 요청.

## 15. Acceptance criteria checklist

- [x] 현재 구조와 문제 정의를 실제 코드 기준으로 기록했다.
- [x] exact code/config/file discovery 결과를 포함했다.
- [x] 네 enhancement 각각 목표/비목표/architecture/schema/state model을 정의했다.
- [x] Kanban lifecycle/reconciler/monitor 및 Dashboard v1/v2 후보와 충돌을 분석했다.
- [x] 단계별 우선순위와 dependency graph를 정의했다.
- [x] 보안·개인정보·network/resource 위험과 완화를 포함했다.
- [x] rollout, feature flag, rollback을 정의했다.
- [x] 테스트와 관찰 가능성/evidence 형식을 정의했다.
- [x] PM, verifier, Raphael gate를 분리했다.
- [x] 지금 적용/나중 적용/보류 판단을 명시했다.
- [x] Orca runtime/앱/server/mobile 설치를 제외했다.
- [x] implementation/commit/push/deploy/restart/cron resume/Discord send를 수행하지 않았다.

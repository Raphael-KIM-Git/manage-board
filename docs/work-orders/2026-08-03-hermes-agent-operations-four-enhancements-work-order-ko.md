# Hermes Agent Operations 4대 개선 선별 적용 작업 지시서

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 승인된 phase만 isolated worktree에서 TDD로 구현하고, 네 개선을 big-bang 없이 독립 검토·canary·rollout한다.

**Architecture:** lifecycle/remote/provider 수집기는 각각 독립된 versioned JSON artifact를 원자적으로 생성하고 Dashboard가 additive read-only projection한다. coding task는 Hermes Kanban의 기존 project-linked worktree 기능을 사용하며 candidate hash로 developer→verifier→QA→PM 경계를 고정한다.

**Tech Stack:** Python 3 `unittest`, Hermes plugin hooks/Kanban, JSON, existing Operations Dashboard Python/vanilla JS, SSH/SCP/Tailscale, launchd/Windows Task Scheduler.

---

## 0. 이 작업지시서 사용 규칙

### 0.1 Dispatch 금지 상태

이 문서는 card 초안이다. PM gate `t_eb86d4bf`가 `APPROVE`하기 전 어떤 구현 card도 dispatch하지 않는다. 승인되더라도 아래 순서대로 한 phase씩 진행한다.

### 0.2 공통 금지 범위

모든 card에서 금지한다.

- Orca runtime/Electron/headless server/mobile runtime 설치.
- prompt, response, tool args/result, command, file content, credential/token/header 원문 수집.
- 기존 `operations/briefs/*.json`, Kanban DB, `operations/kanban/workflows.v1.json`을 lifecycle/usage collector가 수정.
- 현재 `/home/raphael/myproject` dirty main에서 구현·staging·commit.
- existing dirty/untracked 후보 삭제·이동·stash·reset/checkout.
- paused cron resume, launchd/Task Scheduler 변경, service restart, Discord send.
- commit/push/merge/deploy를 구현 card 안에서 수행.
- force worktree removal, branch delete, history rewrite.

### 0.3 공통 workspace admission

coding card 생성자는 다음을 명시한다.

```text
workspace_kind=worktree
project=<Agent Hub project id/slug after PM discovery>
workspace_path=/home/raphael/myproject/.worktrees/<task-id>
branch=<project-slug>/<task-id>
```

project 등록이 없으면 PM은 repo root를 확인한 후 explicit worktree path/branch를 설정한다. `workspace_kind=dir`로 `/home/raphael/myproject`를 지정한 coding card는 dispatch하지 않는다.

### 0.4 공통 candidate evidence

Developer handoff comment는 아래 JSON을 포함해야 한다.

```json
{
  "schema_version": 1,
  "candidate_key": "<workspace>|<base_sha>|<diff_sha256>",
  "workspace_path": "/absolute/worktree/path",
  "branch": "branch/name",
  "base_sha": "40-hex",
  "head_sha": "40-hex-or-null",
  "diff_sha256": "64-hex",
  "changed_files": ["exact/path"],
  "tests": [{"command": "exact command", "exit_code": 0, "summary": "N passed"}],
  "forbidden_scope_touched": false,
  "feature_flags": {"name": "value"},
  "evidence_dir": "/absolute/path"
}
```

Developer는 code change 후 `review-required`로 block한다. Verifier는 developer의 blocked 상태를 parent dependency로 사용하지 않고 PM-held independent card로 생성한다. candidate가 바뀌면 기존 verdict는 stale이며 새 generation이 필요하다.

### 0.5 공통 verification preflight

모든 card 시작 시 실행한다.

```bash
pwd
git rev-parse --show-toplevel
git branch --show-current
git status --short
git rev-parse HEAD
git worktree list --porcelain
```

Expected:
- cwd가 card 전용 worktree다.
- branch가 card 지정 branch다.
- 시작 상태가 clean이다.
- base SHA가 handoff에 기록된다.

clean이 아니거나 main checkout이면 수정하지 말고 PM에 block한다.

## 1. 전체 card/dependency graph

```text
WO-00 PM collision/admission gate
  -> WO-01 worktree policy tests+validator
  -> WO-02 lifecycle schema/store
      -> WO-03 lifecycle plugin adapter shadow
      -> WO-04 lifecycle consolidator/API
      -> WO-05 lifecycle UI canary
  -> WO-06 remote runtime state machine
      -> WO-07 remote/local runner canary
  -> WO-08 provider usage collector/classifier
      -> WO-09 provider Dashboard projection/UI
각 developer card -> independent verifier -> 필요 시 QA -> PM rollout decision
최종 -> WO-10 commit/push gate -> WO-11 deploy/restart gate -> WO-12 cleanup gate
```

네 기능을 하나의 branch/commit/deploy에 묶지 않는다.

---

## Card WO-00: Collision inventory와 implementation admission gate

**Assignee:** `pm`

**Objective:** 현재 dirty candidates와 active Kanban lane을 재확인하고 구현 가능한 clean baseline 및 card별 worktree를 승인한다.

**Files:**
- Read: `/home/raphael/myproject/DASHBOARD-REVIEW-MANIFEST.md`
- Read: `/home/raphael/myproject/DASHBOARD-REVIEW-MANIFEST.json`
- Read: `/home/raphael/myproject/Agent-Hub-Kanban-Lifecycle-Autocontinue-Plan-ko.md`
- Read: `/home/raphael/myproject/docs/plans/2026-08-03-hermes-agent-operations-four-enhancements-plan-ko.md`
- Read: `/home/raphael/myproject/docs/work-orders/2026-08-03-hermes-agent-operations-four-enhancements-work-order-ko.md`
- Do not modify any repository file.

**Prerequisites:** PM review gate가 본 계획을 승인한다.

**Forbidden scope:** implementation, file mutation, commit/push/deploy/restart/cron/Discord.

**Step 1: Refresh read-only inventory**

Run:
```bash
cd /home/raphael/myproject
git status --short
git branch --show-current
git rev-parse HEAD
git worktree list --porcelain
```
Expected: 현 상태가 evidence로 캡처되며 어떤 파일도 바뀌지 않는다.

**Step 2: Inspect active overlaps**

Kanban board에서 status가 ready/running/todo/blocked인 Dashboard v1.1/v1.2, lifecycle, PM monitor cards를 분류한다.

Expected: 각 shared path마다 owner candidate와 proceed/hold/supersede가 명시된다.

**Step 3: Select baseline**

- dirty main을 baseline으로 선택하지 않는다.
- clean `origin/main` 또는 PM이 승인한 immutable commit을 card별 base로 지정한다.
- 기존 dirty candidate를 보존한다.

**Step 4: Create only next card**

WO-01과 WO-02 중 승인된 하나만 먼저 생성한다. 병렬 시작은 shared-path overlap이 없음을 증명한 경우에만 허용한다.

**Acceptance criteria:**
- [ ] baseline SHA가 있다.
- [ ] card별 worktree path/branch/project가 있다.
- [ ] shared paths owner matrix가 있다.
- [ ] existing dirty/untracked file write가 0건이다.
- [ ] commit/push/deploy가 0건이다.

**Evidence handoff:** Kanban comment에 inventory timestamp, base SHA, active conflicts, approved next card, held cards, Raphael approval 필요 항목을 기록한다.

---

## Card WO-01: Coding-task worktree admission validator

**Assignee:** `developer`

**Objective:** coding task는 worktree를 요구하고 non-coding task는 강제하지 않는 순수 validator와 card-creation policy를 구현한다.

**Files:**
- Create: `operations/workspace_policy.py`
- Create: `tests/test_workspace_policy.py`
- Modify only after PM exact seam confirmation: `operations_dashboard_server.py`의 task/card creation seam 또는 별도 PM card factory
- Do not modify: `/home/raphael/.hermes/hermes-agent/hermes_cli/kanban_db.py` in this card.

**Prerequisites:** WO-00; clean worktree; core의 existing `workspace_kind/project/branch_name` support 확인.

**Forbidden scope:** worktree 자동 삭제, git command execution, Kanban DB direct write, global core enforcement, PM/Planner/Research에 worktree 강제.

**Step 1: Write failing classifier tests**

```python
import unittest
from operations.workspace_policy import classify_workspace_requirement, validate_workspace

class WorkspacePolicyTest(unittest.TestCase):
    def test_developer_code_task_requires_worktree(self):
        task = {"assignee": "developer", "title": "fix projection", "body": "modify Python and tests"}
        self.assertEqual(classify_workspace_requirement(task), "worktree_required")

    def test_planner_document_task_does_not_require_worktree(self):
        task = {"assignee": "planner", "title": "write PRD", "body": "documentation only"}
        self.assertEqual(classify_workspace_requirement(task), "not_required")

    def test_dirty_main_dir_is_rejected_for_coding(self):
        task = {"assignee": "developer", "title": "implement feature", "body": "code"}
        result = validate_workspace(task, "dir", "/home/raphael/myproject", repo_root="/home/raphael/myproject")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "coding_task_requires_worktree")
```

**Step 2: Verify RED**

Run:
```bash
python3 -m unittest tests.test_workspace_policy -v
```
Expected: FAIL because module/functions do not exist.

**Step 3: Implement minimum pure policy**

Required API:
```python
def classify_workspace_requirement(task: dict) -> str: ...
def validate_workspace(task: dict, workspace_kind: str, workspace_path: str | None, *, repo_root: str) -> dict: ...
```

Rules:
- explicit `task_kind`/`changes_code`가 있으면 free-text보다 우선한다.
- coding developer/QA applying changes/verifier applying fixes만 require.
- absolute path, `<repo>/.worktrees/` containment, task-id path binding을 검증한다.
- validator는 git/DB/file write를 하지 않는다.

**Step 4: Verify GREEN**

Run:
```bash
python3 -m unittest tests.test_workspace_policy -v
python3 -m py_compile operations/workspace_policy.py
```
Expected: all PASS.

**Step 5: Add edge cases**

Tests:
- relative path reject.
- worktree path outside repo reject.
- `scratch` coding reject.
- research/non-code dir allow.
- unknown assignee + explicit `changes_code=true` require.
- false-positive words in documentation context do not force when `task_kind=documentation`.

**Step 6: Integration only through approved seam**

PM이 exact card creation seam을 승인한 경우 report-only warning을 추가한다. 기본 mode는 `report`; `enforce`는 Raphael 별도 승인 전 금지다.

**Step 7: Full verification**

```bash
python3 -m unittest tests.test_workspace_policy
python3 -m unittest tests.test_kanban_lifecycle
python3 -m unittest tests.test_dashboard_api_contracts
python3 -m py_compile operations/workspace_policy.py operations_dashboard_server.py
git diff --check
git status --short
```

**Acceptance criteria:**
- [ ] coding/non-coding examples이 올바르게 분류된다.
- [ ] dirty main coding task가 reject된다.
- [ ] git/DB write가 없다.
- [ ] 기본 mode가 report다.
- [ ] 변경 파일이 allowlist에 한정된다.

**Evidence handoff:** 공통 candidate JSON + classifier decision matrix + exact integration seam.

---

## Card WO-02: Lifecycle schema, privacy normalizer, atomic state store

**Assignee:** `developer`

**Objective:** raw hook kwargs를 저장하지 않고 허용된 metadata만 2 KiB 이하로 정규화·dedupe·atomic write하는 domain layer를 구현한다.

**Files:**
- Create: `operations/lifecycle/__init__.py`
- Create: `operations/lifecycle/schema.py`
- Create: `operations/lifecycle/store.py`
- Create: `tests/test_lifecycle_runtime_state.py`

**Prerequisites:** WO-00; lifecycle/Kanban monitor overlap matrix 승인.

**Forbidden scope:** Hermes plugin wiring, Dashboard/server/UI 수정, Kanban DB/workflow registry write, raw args/result/error/prompt 저장.

**Step 1: Write privacy/size failing tests**

```python
import unittest
from operations.lifecycle.schema import normalize_event

class LifecycleRuntimeStateTest(unittest.TestCase):
    def test_raw_payload_is_never_serialized(self):
        event = normalize_event(
            hook="post_tool_call",
            profile="developer",
            session_id="s1",
            task_id="t_12345678",
            metadata={"tool_name": "terminal", "args": {"command": "secret"}, "result": "token", "duration_ms": 5},
            observed_at="2026-08-03T00:00:00+00:00",
        )
        rendered = str(event)
        self.assertNotIn("secret", rendered)
        self.assertNotIn("token", rendered)
        self.assertEqual(event["tool_category"], "terminal")

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_event("pre_llm_call", "evil", "s", "", {}, "2026-08-03T00:00:00+00:00")
```

**Step 2: Verify RED**

```bash
python3 -m unittest tests.test_lifecycle_runtime_state -v
```
Expected: import failure.

**Step 3: Implement schema**

Allowed output keys only:
`schema_version,event_id,profile,session_id,task_id,state,observed_at,tool_category,duration_ms,approval_wait,source_hook`.

Profile allowlist:
`default,pm,planner,developer,qa,researcher,verifier,designer`.

Tool category mapper accepts only tool name and returns:
`file,terminal,web,browser,kanban,other`.

**Step 4: Add state mapping tests**

- pre LLM/API → thinking.
- pre tool → using_tool.
- pre approval → waiting_approval.
- Kanban claimed → queued.
- Kanban blocked/completed → blocked/completed.
- post approval returns to thinking, not completed.

**Step 5: Implement atomic store**

Required API:
```python
class LifecycleStateStore:
    def append(self, event: dict) -> bool: ...
    def snapshot(self) -> dict: ...
```

Rules:
- temp file + flush/fsync + `os.replace`.
- lock wait ≤100 ms.
- max 100 events.
- duplicate event_id returns `False`.
- corrupt input fail-open; no agent exception propagation.
- permissions 0600 where supported.

**Step 6: Fault tests**

- duplicate append.
- lock timeout.
- corrupt JSON.
- oversized event.
- interrupted temp file leaves prior LKG valid.
- forbidden keys recursively supplied but absent from disk.

**Step 7: Verify**

```bash
python3 -m unittest tests.test_lifecycle_runtime_state -v
python3 -m py_compile operations/lifecycle/schema.py operations/lifecycle/store.py
git diff --check
```

**Acceptance criteria:**
- [ ] forbidden payload 0 bytes on disk.
- [ ] event ≤2 KiB.
- [ ] duplicate 0.
- [ ] lock/corrupt/write failures fail-open.
- [ ] no existing authority file modified.

**Evidence handoff:** test output, sample redacted event, max serialized bytes, forbidden-key scan result.

---

## Card WO-03: Hermes lifecycle plugin adapter — shadow mode

**Assignee:** `developer`

**Objective:** existing Hermes observer hooks를 WO-02 domain layer에 연결하되 profile-local spool만 쓰는 disabled-by-default plugin package를 만든다.

**Files:**
- Create: `operations/lifecycle/plugin/plugin.yaml`
- Create: `operations/lifecycle/plugin/__init__.py`
- Create: `tests/test_lifecycle_plugin_adapter.py`
- Read only: `/home/raphael/.hermes/hermes-agent/hermes_cli/plugins.py:135-215`
- Read only: `/home/raphael/.hermes/hermes-agent/agent/conversation_loop.py:363-388`
- Read only: `/home/raphael/.hermes/hermes-agent/model_tools.py:980-1022`
- Read only: `/home/raphael/.hermes/hermes-agent/tools/approval.py:96-167`

**Prerequisites:** WO-02 verifier PASS.

**Forbidden scope:** Hermes core edit, profile plugin install, gateway restart, default enable, raw callback kwargs serialization.

**Step 1: Write failing registration test**

Mock PluginContext가 다음 observer를 등록하는지 검증한다:
- on_session_start/end
- pre/post_llm_call
- pre/post_tool_call
- pre/post_approval_response/request
- kanban_task_claimed/blocked/completed
- api_request_error

**Step 2: Verify RED**

```bash
python3 -m unittest tests.test_lifecycle_plugin_adapter -v
```

**Step 3: Implement adapter**

```python
def register(ctx):
    """Register observer-only callbacks; every callback must swallow store errors."""
```

- `OPS_RUNTIME_LIFECYCLE_ENABLED != 1`이면 callback no-op.
- profile은 `ctx.profile_name` 및 allowlist로 결정.
- spool root는 active profile `HERMES_HOME/runtime/lifecycle/`.
- callback은 `metadata` dict를 수동 구성하고 raw kwargs를 pass-through하지 않는다.
- callback return은 항상 `None`.

**Step 4: Add fail-open tests**

- store raises → hook returns None.
- unknown profile → event drop counter, no path creation.
- malicious args/result/error contains credential-like string → file에 없음.
- profile A event가 profile B path에 없음.

**Step 5: Verify**

```bash
python3 -m unittest tests.test_lifecycle_plugin_adapter tests.test_lifecycle_runtime_state -v
python3 -m py_compile operations/lifecycle/plugin/__init__.py
git diff --check
```

**Acceptance criteria:**
- [ ] core edit 0.
- [ ] flag default off.
- [ ] observer return으로 tool/approval을 변경하지 않는다.
- [ ] profile-local spool만 사용한다.
- [ ] forbidden raw payload 0.

**Evidence handoff:** hook→state matrix, plugin manifest hash, profile path matrix, fail-open test.

**Rollout gate:** verifier PASS 후 planner profile shadow install만 별도 deployment card로 제안한다. 이 card에서 설치/재시작하지 않는다.

---

## Card WO-04: Lifecycle consolidator와 read-only API

**Assignee:** `developer`

**Objective:** profile spool을 bounded merge해 `operations/runtime/agent-state.v1.json`을 만들고 additive read-only API/projection을 제공한다.

**Files:**
- Create: `operations/runtime/.gitkeep` if directory tracking is needed
- Create: `operations/lifecycle/consolidate.py`
- Create: `tests/test_lifecycle_consolidator.py`
- Modify: `operations_dashboard_projection.py`
- Modify: `operations_dashboard_server.py`
- Modify: `tests/test_dashboard_projection.py`
- Modify: `tests/test_dashboard_api_contracts.py`

**Prerequisites:** WO-03 verifier PASS; Dashboard shared file owner cleared by PM.

**Forbidden scope:** app.js/styles UI, Kanban/workflow/brief mutation, profile spool deletion, existing `worker-status.json` replacement.

**Step 1: Write failing projection tests**

Cases:
- fresh using_tool.
- TTL exceeded → stale with `stale_from`.
- corrupt/missing/unknown version → unknown.
- blocked precedence.
- cross-profile duplicate/event conflict.

**Step 2: Verify RED**

```bash
python3 -m unittest tests.test_lifecycle_consolidator tests.test_dashboard_projection -v
```

**Step 3: Implement consolidator**

Required API:
```python
def consolidate(spool_roots: dict[str, Path], output_path: Path, *, now) -> dict: ...
def project_agent_runtime(snapshot, *, now) -> dict: ...
```

- known profiles only.
- max profile/event bounds.
- event fingerprint dedupe.
- atomic LKG output.
- no source spool deletion.
- duration/freshness/drop/conflict counters.

**Step 4: Add route**

`GET /api/runtime-status` → schema v1 read-only snapshot/projection.

`/api/overview`와 `/api/agents`에는 additive `runtime_state`; missing file이면 기존 contract가 깨지지 않는다.

**Step 5: Verify focused + regression**

```bash
python3 -m unittest tests.test_lifecycle_consolidator tests.test_dashboard_projection tests.test_dashboard_api_contracts -v
python3 -m unittest tests.test_kanban_lifecycle tests.test_operations_watchdog
python3 -m py_compile operations/lifecycle/consolidate.py operations_dashboard_projection.py operations_dashboard_server.py
git diff --check
```

**Acceptance criteria:**
- [ ] new route read-only.
- [ ] stale/unknown이 idle로 축소되지 않는다.
- [ ] prior API fields unchanged.
- [ ] workflow/brief/Kanban writes 0.
- [ ] corrupt input에서 HTTP 500이 아니다.

**Evidence handoff:** API fixture, before/after contract diff, LKG fault test, changed-file allowlist.

---

## Card WO-05: Lifecycle Dashboard UI canary

**Assignee:** `developer`

**Objective:** planner/developer runtime state를 우선 표시하는 최소 UI를 feature flag 뒤에 추가한다.

**Files:**
- Modify: `operations_dashboard/app.js`
- Modify: `operations_dashboard/styles.css`
- Modify only if required and PM-approved: `operations_dashboard/index.html`
- Modify: `tests/test_dashboard_static_contract.py`
- Create: `tests/test_lifecycle_ui_contract.py`

**Prerequisites:** WO-04 verifier PASS; Dashboard v1/v2 integration baseline 확정.

**Forbidden scope:** UI에서 state write/control, prompt/tool payload drilldown, 4-pane layout refactor, follow-up/artifact semantics 변경.

**Step 1: Write failing static tests**

- enum label mapping.
- stale/unknown explicit label.
- approval wait visible.
- no args/result/prompt/response fields rendered.
- flag off DOM unchanged.

**Step 2: RED**

```bash
python3 -m unittest tests.test_lifecycle_ui_contract tests.test_dashboard_static_contract -v
```

**Step 3: Minimal implementation**

- profile/name, state label, freshness, coarse tool category만 표시.
- `OPS_RUNTIME_PROJECTION_ENABLED=0` 또는 API unavailable이면 component를 숨기거나 unavailable 표시.
- color만으로 상태를 전달하지 않는다.
- DOM textContent 사용; raw HTML 삽입 금지.

**Step 4: GREEN/regression**

```bash
node --check operations_dashboard/app.js
python3 -m unittest tests.test_lifecycle_ui_contract tests.test_dashboard_static_contract tests.test_dashboard_api_contracts
python3 -m unittest discover -s tests -p 'test*.py'
git diff --check
```

**Step 5: Browser QA handoff**

`qa`가 1440/768/390, keyboard, stale/unknown/missing/API error를 검증한다.

**Acceptance criteria:**
- [ ] flag off regression 0.
- [ ] unknown/stale/approval state accessible.
- [ ] raw payload 노출 0.
- [ ] planner/developer canary만 승인 가능.

---

## Card WO-06: Remote worker reconnect/hibernation domain state machine

**Assignee:** `developer`

**Objective:** SSH/heartbeat/inbox/lease/result evidence를 분리해 worker runtime 상태와 bounded backoff를 순수하게 계산한다.

**Files:**
- Create: `operations/remote_runtime.py`
- Create: `tests/test_remote_runtime.py`
- Read only: `tmp_worker_runner.py`
- Read only: `hermes_local_runner.py`
- Read only: `operations/config/workers.json`

**Prerequisites:** lifecycle MVP shadow 결과 안정; PM이 remote scope 승인.

**Forbidden scope:** SSH 호출/launchd 변경/runner 수정/실제 wake/restart, provider retry와 network retry 혼합.

**Step 1: Write failing state tests**

```python
import unittest
from operations.remote_runtime import project_worker_state, next_backoff_seconds

class RemoteRuntimeTest(unittest.TestCase):
    def test_fresh_heartbeat_but_failed_probe_is_degraded(self):
        state = project_worker_state({"heartbeat_fresh": True, "probe_ok": False, "inbox_count": 0})
        self.assertEqual(state["state"], "degraded")

    def test_result_pending_precedes_new_dispatch(self):
        state = project_worker_state({"probe_ok": True, "result_unacked": True, "inbox_count": 1})
        self.assertEqual(state["state"], "result_pending")

    def test_backoff_is_bounded(self):
        self.assertEqual([next_backoff_seconds(i, jitter=0) for i in range(5)], [15, 30, 60, 120, 300])
```

**Step 2: RED**

```bash
python3 -m unittest tests.test_remote_runtime -v
```

**Step 3: Implement pure state machine**

Allowed states:
`unknown,probing,idle,hibernating,wake_pending,running,result_pending,backoff,cooldown,degraded`.

- heartbeat와 probe fields 분리.
- network/provider/local timeout namespaces 분리.
- max 5 attempts then 15m cooldown.
- official reset이 있으면 retry-at가 reset 이전이 아니도록 한다.

**Step 4: Lease/dedupe helpers**

Pure validators for:
- lease owner/expiry/source digest.
- duplicate active owner conflict.
- stale lease reclaim preconditions.
- existing result digest match vs conflict.

**Step 5: Verify**

```bash
python3 -m unittest tests.test_remote_runtime -v
python3 -m py_compile operations/remote_runtime.py
git diff --check
```

**Acceptance criteria:**
- [ ] heartbeat-only healthy 판정 0.
- [ ] result pull이 new dispatch보다 우선.
- [ ] backoff bounded.
- [ ] duplicate/conflict fail-closed.
- [ ] network side effect 0.

---

## Card WO-07: Remote/local runner canary integration

**Assignee:** `developer`

**Objective:** researcher-co 하나에서 state artifact/lease/result ack를 canary하고, 이후 approved worker로 확장할 integration을 구현한다.

**Files:**
- Modify: `operations_sync.py`
- Modify only approved sections: `tmp_worker_runner.py`
- Modify only approved sections: `hermes_local_runner.py`
- Modify: `test_operations_sync.py`
- Create: `tests/test_remote_runtime_integration.py`
- Create runtime outputs only at run time: `operations/runtime/worker-runtime.v1.json`

**Prerequisites:** WO-06 verifier PASS; MacBook launchd plist read-only discovery; fake SSH tests first.

**Forbidden scope:** `operations/config/workers.json` endpoint 변경, launchd/Task Scheduler mutation, Tailscale config, PM gateway, `ensure-agent-hub-services.sh`, all-worker big-bang.

**Step 1: Write fake integration tests**

- SSH connect timeout → network backoff.
- 429 log → provider rate-limit, not network.
- inbox empty/probe good → idle/hibernating.
- duplicate lock → one runner only.
- remote result exists/local ack missing → result_pending and pull first.
- digest mismatch → conflict, no overwrite.

**Step 2: RED**

```bash
python3 -m unittest tests.test_remote_runtime_integration -v
```

**Step 3: Implement short-lived collector**

- 기존 `operations_sync.py` run에 piggyback하거나 PM이 승인한 separate one-shot script.
- SSH ConnectTimeout ≤8s, process timeout ≤15s.
- raw log는 local state artifact에 저장하지 않는다.
- worker status schema는 versioned atomic output.
- `operations/worker-status.json` compatibility read는 유지한다.

**Step 4: Integrate lease/ack minimally**

- temp→rename result.
- hub digest verification 후 ack sidecar.
- existing envelope semantics를 바꾸지 않는다.
- canary worker는 `researcher-co` 하나.

**Step 5: Focused regression**

```bash
python3 -m unittest tests.test_remote_runtime tests.test_remote_runtime_integration test_operations_sync -v
python3 -m unittest tests.test_operations_watchdog
python3 -m py_compile operations_sync.py operations/remote_runtime.py tmp_worker_runner.py hermes_local_runner.py
git diff --check
```

**Step 6: Canary evidence only**

배포/restart는 하지 않고 QA/PM이 사용할 command와 expected state를 handoff한다.

**Acceptance criteria:**
- [ ] researcher-co only.
- [ ] no long-lived process/socket.
- [ ] bounded timeout/backoff.
- [ ] duplicate 0, overwrite conflict 0.
- [ ] Windows/WSL recovery path unchanged.

**Expansion order after approval:** researcher-co → writer-co → verify-co → analyst-co → researcher_agent → HermesResearcher.

---

## Card WO-08: Provider usage/rate-limit collector와 classifier

**Assignee:** `developer`

**Objective:** local safe evidence를 provider별 v1 snapshot으로 집계하고 unknown-first rate-limit/network/timeout 판정을 구현한다.

**Files:**
- Create: `operations/provider_usage.py`
- Create: `tests/test_provider_usage.py`
- Read only: `/home/raphael/.hermes/hermes-agent/hermes_state.py`
- Read only: `/home/raphael/.hermes/hermes-agent/agent/credits_tracker.py`
- Read only: `tmp_worker_runner.py:180-209`
- Read only: `hermes_local_runner.py:158-190`
- Runtime output: `operations/runtime/provider-usage.v1.json`

**Prerequisites:** WO-00; provider data-source/privacy matrix approved; no credential read.

**Forbidden scope:** auth.json/.env/credential files read, provider web scraping, network probe, quota estimation, raw log/error/header output.

**Step 1: Write failing classifier tests**

```python
import unittest
from operations.provider_usage import classify_failure, normalize_provider_usage

class ProviderUsageTest(unittest.TestCase):
    def test_network_timeout_is_not_rate_limit(self):
        self.assertEqual(classify_failure({"kind": "connect_timeout"})["status"], "network_or_provider_error")

    def test_http_429_is_rate_limit(self):
        self.assertEqual(classify_failure({"http_status": 429})["status"], "rate_limited")

    def test_missing_limit_is_unknown_not_zero(self):
        item = normalize_provider_usage("openai-codex", {"input_tokens": 10})
        self.assertIsNone(item["limit"]["value"])
        self.assertEqual(item["limit"]["status"], "unknown")
```

**Step 2: RED**

```bash
python3 -m unittest tests.test_provider_usage -v
```

**Step 3: Implement schema/normalizer**

Provider allowlist plus `other`; safe fields only:
- token/call/cost status aggregates.
- limit/remaining/reset when structured official source exists.
- last rate-limit/timeout timestamps.
- health/source/observed_at/errors as coarse codes.

Unknown values are null + status unknown.

**Step 4: Implement local collectors**

- Hermes session DB read-only connection.
- result envelope usage/model/timestamp.
- Nous credits must reuse validated contract or already-sanitized state; duplicate parser 금지.
- collector별 exception은 namespaced error code, no raw exception message in Dashboard artifact.

**Step 5: Privacy and malformed tests**

- credentials/header/raw error omitted.
- malformed usage ignored.
- negative token/count rejected.
- stale snapshot.
- actual/estimated/unknown cost label preserved.
- remaining=0 alone does not imply depleted.

**Step 6: Verify**

```bash
python3 -m unittest tests.test_provider_usage -v
python3 -m py_compile operations/provider_usage.py
git diff --check
```

**Acceptance criteria:**
- [ ] credential file reads 0.
- [ ] network calls 0.
- [ ] missing values unknown.
- [ ] 429/network/local timeout 분리.
- [ ] provider-specific source provenance 있음.

---

## Card WO-09: Provider usage Dashboard projection/UI

**Assignee:** `developer`

**Objective:** provider usage v1 snapshot을 additive API와 Dashboard card로 표시한다.

**Files:**
- Modify: `operations_dashboard_projection.py`
- Modify: `operations_dashboard_server.py`
- Modify: `operations_dashboard/app.js`
- Modify: `operations_dashboard/styles.css`
- Modify: `tests/test_dashboard_projection.py`
- Modify: `tests/test_dashboard_api_contracts.py`
- Modify: `tests/test_dashboard_static_contract.py`
- Create: `tests/test_provider_usage_ui_contract.py`

**Prerequisites:** WO-08 verifier PASS; Dashboard shared-path owner cleared; lifecycle UI candidate hash known.

**Forbidden scope:** provider settings/auth UI, token display, automatic provider switching/retry, v2 pane redesign.

**Step 1: Write failing API/UI tests**

- missing limit renders unknown.
- stale snapshot explicit.
- network error distinct from rate-limited.
- source and observed_at visible.
- no secret/raw error keys.
- flag off regression.

**Step 2: RED**

```bash
python3 -m unittest tests.test_provider_usage_ui_contract tests.test_dashboard_projection tests.test_dashboard_api_contracts -v
```

**Step 3: Implement additive projection/route**

Candidate route: `GET /api/provider-usage`.

- read-only.
- schema unknown/corrupt/missing → unknown response, HTTP server remains healthy.
- `/api/overview` additive summary only.

**Step 4: Minimal UI**

Card fields:
`provider, usage, limit, remaining, reset, recent rate-limit, recent timeout, freshness, source`.

- null → `알 수 없음`, not `0`.
- coarse error label only.
- textContent.
- `OPS_PROVIDER_USAGE_ENABLED=0` default.

**Step 5: Verify focused/full**

```bash
python3 -m unittest tests.test_provider_usage tests.test_provider_usage_ui_contract tests.test_dashboard_projection tests.test_dashboard_api_contracts tests.test_dashboard_static_contract -v
node --check operations_dashboard/app.js
python3 -m py_compile operations/provider_usage.py operations_dashboard_projection.py operations_dashboard_server.py
python3 -m unittest discover -s tests -p 'test*.py'
git diff --check
```

**Acceptance criteria:**
- [ ] unknown-first rendering.
- [ ] quota/network distinction.
- [ ] secrets/raw errors absent.
- [ ] existing API/UI regression 0.
- [ ] default off.

---

## Card WO-V-A/B/C/D: Independent verifier gates

**Assignee:** `verifier`

각 enhancement마다 별도 verifier card를 사용한다. 하나의 verdict로 네 기능을 승인하지 않는다.

**Inputs:** exact candidate JSON, worktree, base SHA, diff SHA, tests/evidence.

**Required review:**

1. Spec compliance: goal/non-goal/forbidden scope.
2. Privacy: prompt/response/args/result/credential/raw error absence.
3. Authority: brief/Kanban/workflow registry non-mutation.
4. Atomicity/dedupe/TTL/fail-open.
5. Candidate binding: workspace/base/diff hash 일치.
6. Test rerun: developer가 제시한 focused commands.
7. Shared-path overlap: unrelated dirty candidate 혼입 없음.

**Verdict format:**

```json
{
  "verdict": "PASS|NEEDS_CHANGES|HOLD",
  "reviewer_id": "<verifier-task-id>",
  "candidate_key": "<exact key>",
  "candidate_hash": "<diff_sha256>",
  "commands_rerun": [{"command": "...", "exit_code": 0}],
  "blockers": [],
  "warnings": [],
  "scope_verified": true,
  "privacy_verified": true,
  "authority_verified": true
}
```

PASS가 아니면 downstream QA/commit/deploy gate를 열지 않는다.

---

## Card WO-QA-A/B/C/D: QA/evidence gates

**Assignee:** `qa`

기능별로 필요할 때 별도 생성한다.

**Lifecycle QA:**
- eight-profile fixture, stale/unknown, approval wait, API failure.
- 1440/768/390, keyboard, color-independent labels.

**Worktree QA:**
- coding/non-coding classifier matrix.
- dirty main reject.
- hash drift invalidates verdict.

**Remote QA:**
- fake SSH timeout/429/result pending/duplicate lease.
- researcher-co canary observation; 다른 worker 불변.

**Provider QA:**
- unknown/zero distinction.
- rate-limit/network/local timeout distinction.
- no secret/raw error rendering.

**Evidence format:** JSON matrix with case id, input fixture, expected, observed, pass, screenshot path where applicable, candidate hash.

---

## Card WO-10: Allowlisted commit/push gate

**Assignee:** `developer`

**Objective:** Raphael이 명시적으로 승인한 단일 enhancement candidate만 allowlist commit/push한다.

**Prerequisites:** matching verifier PASS, required QA PASS, PM synthesis, Raphael explicit approval.

**Forbidden scope:** 다른 enhancement 포함, dirty main staging, `git add .`, amend/rebase/reset, deploy/restart.

**Steps:**

```bash
git status --short
git diff --name-only <base_sha>...HEAD
git diff --check
git diff --stat <base_sha>
```

PM allowlist와 exact match를 확인한 뒤 파일명을 개별 `git add <path...>`로 stage한다. commit message는 enhancement별 하나다. push는 승인된 remote/branch에만 수행한다.

**Acceptance criteria:**
- [ ] staged path = allowlist.
- [ ] candidate hash/review hash 일치.
- [ ] unrelated dirty/untracked 0 포함.
- [ ] deploy/restart 0.

---

## Card WO-11: Canary deploy/restart gate

**Assignee:** `developer`

**Objective:** Raphael 승인 후 단일 기능·단일 canary 범위로 feature flag를 켜고 health/LKG/rollback을 검증한다.

**Prerequisites:** WO-10, verifier PASS, QA PASS, PM go, Raphael explicit deploy approval.

**Forbidden scope:** four-feature simultaneous enable, paused cron resume, Discord send, all-profile/all-worker rollout.

**Canary order:**
- lifecycle: planner → developer.
- remote: researcher-co.
- provider: read-only local DB collector, no network.
- worktree policy: report → one PM-created coding card; enforce는 별도 승인.

**Health checks:**

```bash
curl -fsS --max-time 5 http://127.0.0.1:8765/api/health
curl -fsS --max-time 5 http://127.0.0.1:8765/api/runtime-status
curl -fsS --max-time 5 http://127.0.0.1:8765/api/provider-usage
```

해당 route가 배포된 phase에만 실행한다. 실패 시 flag off→이전 service artifact/commit 복귀→health 확인. evidence 삭제 금지.

---

## Card WO-12: Cleanup/GC gate

**Assignee:** `developer`

**Objective:** merge/abandon 결정이 끝난 worktree만 증거 보존 후 정리한다.

**Prerequisites:** PM terminal decision, no active worker, no uncommitted file, artifact copied, Raphael cleanup approval.

**Forbidden scope:** force remove default, branch delete without merge/abandon record, current dirty main cleanup, unrelated worktree prune.

**Preflight:**

```bash
git -C /home/raphael/myproject worktree list --porcelain
git -C <target-worktree> status --short
git -C <target-worktree> rev-parse HEAD
```

Clean 및 exact target 확인 후 승인된 하나만 remove한다. `git worktree prune`은 별도 승인 없이는 실행하지 않는다.

---

## 2. Evidence directory contract

각 implementation/review/QA phase는 다음 구조를 사용한다.

```text
operations/evidence/runtime-four-enhancements/
  <enhancement>/
    <candidate-hash-prefix>/
      manifest.json
      test-results.json
      redacted-snapshot.json
      verifier-verdict.json
      qa-matrix.json
```

`manifest.json` 필수:

```json
{
  "schema_version": 1,
  "enhancement": "lifecycle|worktree|remote|provider",
  "candidate_key": "...",
  "base_sha": "...",
  "diff_sha256": "...",
  "changed_files": [],
  "forbidden_scope_touched": false,
  "feature_flag": {"name": "...", "value": "0"},
  "created_at": "ISO-8601"
}
```

금지 evidence:
- prompt/response/tool args/result/commands containing user data.
- credential/token/header/auth/account ID.
- raw remote logs.
- absolute personal document paths not required for candidate correlation.

## 3. Dirty/untracked 보호 규칙

1. `/home/raphael/myproject` main의 현재 modified/untracked 파일은 pre-existing candidate다.
2. `git stash`, `git reset`, `git checkout --`, `git clean`, mass move/delete 금지.
3. 구현은 clean approved base의 dedicated worktree에서 재구성한다.
4. 현재 dirty tree의 파일을 source로 복사하려면 PM manifest가 exact candidate ownership을 증명해야 한다.
5. `git add .`/`git add -A` 금지; commit gate에서 exact path만 stage한다.
6. shared files(server/projection/app/styles)은 enhancement별 candidate hash가 분리돼야 한다.
7. 같은 shared path를 두 active card가 수정하려면 PM이 직렬 dependency를 만들고 후행 card가 선행 candidate를 base로 사용한다.
8. reviewer/QA는 filename/mtime/title로 candidate를 선택하지 않고 candidate key/hash로 bind한다.

## 4. Rollout decision table

| Improvement | 지금 | 나중 | 보류 조건 |
|---|---|---|---|
| Worktree policy | report mode + card admission | enforce after canary | core hard gate, auto cleanup |
| Lifecycle | schema/store/plugin shadow | API/UI after 24h | core hook 추가, raw tracing |
| Remote | pure state/fake tests | researcher-co canary 후 확장 | launchd mutation, daemon/socket |
| Provider | local safe collector | UI, official provider evidence | scraping, quota 추정, network probe |

## 5. PM final review checklist

- [ ] 네 기능이 separate candidates/cards다.
- [ ] 각 coding card가 worktree다.
- [ ] exact base/candidate hash가 있다.
- [ ] active Dashboard/lifecycle/monitor overlap이 해소됐다.
- [ ] privacy forbidden fields가 0이다.
- [ ] canonical authority mutation이 0이다.
- [ ] focused test + regression evidence가 있다.
- [ ] verifier PASS가 candidate hash와 일치한다.
- [ ] 필요한 QA PASS가 있다.
- [ ] feature flag default off/report다.
- [ ] rollback이 deletion 없이 가능하다.
- [ ] commit/push/deploy/restart/cron/Discord가 별도 gate다.
- [ ] Raphael approval이 필요한 다음 행위를 정확히 한 개만 요청한다.

## 6. 작업지시서 acceptance checklist

- [x] developer가 추측 없이 실행할 phase별 card를 제시했다.
- [x] 각 card에 assignee, exact files, prerequisites, forbidden scope가 있다.
- [x] TDD RED→GREEN과 exact verification commands가 있다.
- [x] acceptance criteria와 evidence handoff 형식이 있다.
- [x] commit/push/deploy/restart를 별도 gate로 분리했다.
- [x] dirty/untracked 보호 규칙을 명시했다.
- [x] 네 기능을 big-bang하지 않는 순차 계획이다.
- [x] verifier/QA/PM/Raphael gate가 분리됐다.
- [x] implementation은 이 문서 작성 task에서 수행하지 않았다.

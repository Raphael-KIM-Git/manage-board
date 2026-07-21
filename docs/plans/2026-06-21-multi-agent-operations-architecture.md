# Multi-Agent Operations Architecture Plan

> For Raphael님: 맥북(Claude Code + OpenClaw)과 상시 구동 Windows PC(Hermes)를 하나의 운영 체계로 묶고, 서로의 결과를 교차 검증하도록 설계한 실제 운영 문서입니다.

**Goal:**
세 개의 에이전트 실행 환경(Claude Code, OpenClaw, Hermes)을 하나의 운영 체계로 묶어서, 같은 업무를 병렬/분할 수행시키고, 결과를 상호 검증하며, 최종 판정과 기록은 중앙 허브에서 관리한다.

**Recommended Direction:**
메인 허브는 Windows PC의 Hermes로 두고, Paperclip과 Claw3D는 보조 레이어로 취급한다. 초기에는 Paperclip을 직접 운영 본체로 채택하기보다, 그 아이디어(roles, goals, heartbeats, dashboard)는 참고하고, Raphael님 환경에 맞는 별도 운영 시스템을 Hermes 중심으로 구축하는 것이 더 적합하다.

**Decision Summary:**
- 중앙 허브: Windows PC의 Hermes
- 외부 worker: MacBook의 Claude Code, OpenClaw
- 관찰 UI: 필요 시 Claw3D 추가
- 조직/회사형 orchestration 프레임: Paperclip 참고
- 1차 구축 방식: Hermes 중심 custom orchestration
- 2차 실험 방식: 필요 시 Paperclip 별도 샌드박스 도입

---

## 1. Executive Summary

현재 Raphael님이 원하는 것은 단순한 "멀티 에이전트 데모"가 아니라, 아래 기능을 갖춘 실전 운영 체계다.

1. 같은 업무를 여러 에이전트가 각각 수행할 수 있어야 한다.
2. 서로의 결과를 다른 에이전트가 검증할 수 있어야 한다.
3. 최종 판정과 실행 기록이 한곳에 모여야 한다.
4. 항상 켜져 있는 머신이 운영 허브가 되어야 한다.
5. 향후 Discord/kanban/cron/alerts까지 확장 가능해야 한다.

이 요구에는 Paperclip이나 Claw3D 단독 채택보다, Hermes를 중심 허브로 두고 필요한 개념만 흡수하는 방식이 더 적합하다.

이유는 다음과 같다.

- Claw3D는 현재 공개 문서 기준으로 visibility/read-only presence/가벼운 메시징에는 좋지만, 검증 루프의 본체로 보기에는 약하다.
- Paperclip은 AI company orchestration 철학이 좋고 OpenClaw 친화성이 강하지만, Raphael님 환경처럼 Hermes가 핵심 허브이고 Claude Code/OpenClaw/Hermes가 혼합된 구성에서는 그대로 메인 운영 엔진으로 채택하기보다 참고 후 커스텀하는 편이 유연하다.
- Hermes는 profiles, memory, cron, kanban, messaging, verification, reporting에 강해서 "운영 허브" 역할에 가장 잘 맞는다.

따라서 본 문서는 “Hermes를 PM/Verifier 중심 허브로 두는 구조”를 기본안으로 채택한다.

---

## 2. Verified External Facts Used in This Recommendation

### 2.1 Claw3D
실제 확인된 공개 정보:
- Claw3D는 OpenClaw Gateway, Hermes adapter, custom runtime provider를 지원한다.
- 로컬 Studio와 원격 Gateway를 연결하는 구조다.
- cross-machine setup 문서가 있고 Tailscale 패턴을 권장한다.
- multi-agent beta는 second office, remote presence, lightweight remote messaging 중심이다.
- beta limitation 문서상 full shared-state collaboration 목적은 아니다.

해석:
- Claw3D는 관찰/시각화/원격 존재감 표시에는 유용하다.
- 하지만 “결과 비교 → 검증 → 최종 판정 → 히스토리 관리”의 본체로는 부족하다.

### 2.2 Paperclip
실제 확인된 공개 정보:
- npm package `paperclipai` 설명: “orchestrate AI agent teams to run a business”
- 공개 README 계열 설명: org charts, budgets, goals, heartbeats, dashboard
- OpenClaw adapter 패키지가 존재한다.
- Company Wizard 생태계는 CEO/PO/Engineer 등의 조직형 운영 모델을 지향한다.

해석:
- Paperclip은 "AI 회사 운영" 철학이 강하다.
- role/goals/heartbeat/backlog 프레임은 매우 참고할 가치가 있다.
- 하지만 Raphael님 환경은 단일 Paperclip-native stack이 아니라, Hermes/Claude Code/OpenClaw 혼합 운영이다.
- 즉 Paperclip을 통째로 메인으로 삼기보다, 운영 개념을 차용해서 Hermes 중심 설계에 흡수하는 편이 안전하다.

---

## 3. Target Architecture

## 3.1 Node Roles

### A. Windows PC (Always-On Hub)
Primary role: Central Operations Hub

Services on this machine:
- HermesPM: intake, task decomposition, final reporting
- HermesVerifier: cross-agent review and result comparison
- HermesPlanner: planning/spec generation
- Hermes gateway / Discord / cron / kanban / logs
- optional: Claw3D Studio

Why this machine is the hub:
- always on
- suitable for central logs, schedules, alerts, queues
- stable place for memory, reports, and orchestration state

### B. MacBook
Primary role: External Specialist Worker Host

Services on this machine:
- Claude Code
- OpenClaw

Why this machine is not the hub:
- likely sleep / mobility / user-interactive machine
- strong for active work, weaker for 24/7 coordination

### C. Optional Future Host
- Ubuntu VM / mini PC / VPS for long-term hardening
- move OpenClaw or supporting services there if MacBook uptime becomes a bottleneck

---

## 3.2 Logical Agent Topology

Recommended logical roles:

1. HermesPM
- receives user requests
- decides execution mode
- launches verification workflow
- writes final summary

2. HermesPlanner
- writes task briefs/specs
- decides whether job should be parallel, competitive, or sequential

3. HermesVerifier
- compares outputs from Claude Code / OpenClaw / Hermes workers
- checks correctness, completeness, risk, contradictions
- requests revisions if needed

4. HermesImplementer (optional profile)
- Hermes-native execution worker
- useful when a third independent implementation is desirable

5. OpenClaw Worker
- implementation / exploration / autonomous runs on MacBook

6. Claude Code Worker
- implementation / code review / alternate approach on MacBook

---

## 4. Operating Modes

The hub should support three operating modes.

### Mode 1: Competitive Solve
Use when:
- the task is important
- multiple valid implementations may exist
- result quality matters more than cost/time

Flow:
1. HermesPM receives request.
2. HermesPlanner writes a short brief.
3. The same brief is sent to:
   - OpenClaw
   - Claude Code
   - optional HermesImplementer
4. HermesVerifier compares outputs.
5. HermesPM returns final recommendation.

Best for:
- architecture decisions
- code generation
- refactors
- research synthesis

### Mode 2: Primary + Independent Review
Use when:
- one agent is clearly better for the task
- another agent should only review/verify

Flow:
1. primary worker executes
2. second worker reviews output
3. HermesVerifier adjudicates
4. HermesPM summarizes

Best for:
- code review
- config changes
- docs generation
- deployment plans

### Mode 3: Pipeline / Division of Labor
Use when:
- planning, implementation, review, and reporting are naturally distinct

Flow:
1. HermesPlanner writes plan
2. OpenClaw or Claude Code implements
3. HermesVerifier reviews
4. HermesPM publishes final result

Best for:
- longer projects
- repeated workflows
- production changes with checkpoints

---

## 5. Recommended Communication Model

Do not try to make every agent talk to every other agent directly at first.

Recommended model:
- all coordination flows through the Windows PC hub
- the hub is the source of truth
- workers are treated as execution endpoints, not peer-to-peer coordinators

Reason:
- easier logging
- easier replay
- easier debugging
- easier security model
- lower chance of message loops or split-brain behavior

### Message Bus Pattern
Minimum viable bus:
- Discord channels/threads
- Hermes kanban tasks
- markdown reports on disk
- scheduled cron reconciler jobs

Better future bus:
- structured JSON job envelopes in a watched directory or DB
- each worker writes result metadata and artifact references

---

## 6. Automation Possibility Assessment

## 6.1 What can be automated now

Can be automated immediately with current Hermes-heavy stack:

1. Task intake triage
- incoming request classification
- execution mode selection
- priority tagging

2. Brief generation
- HermesPlanner can generate a normalized task brief

3. Scheduled review jobs
- cron-based "check remote workers / summarize status"

4. Cross-agent comparison reports
- HermesVerifier can compare two or three outputs and produce a verdict

5. Report delivery
- Discord / Telegram / local markdown / email style delivery via Hermes tooling

6. Daily digest / watchdog
- summarize what each environment did today
- detect stale worker/no output

### 6.2 What is partially automatable

1. Claude Code invocation from the hub
- possible if the hub can remotely trigger or queue work on the MacBook
- requires transport design: SSH, watched directory, API wrapper, or messaging bridge

2. OpenClaw invocation from the hub
- possible depending on how OpenClaw is currently exposed
- likely easier through gateway/task interface than deep bidirectional integration

3. artifact collection
- possible, but needs standardized result format

### 6.3 What should not be fully automated initially

1. irreversible production actions
2. automatic merge/deploy on first version of the system
3. recursive self-tasking across all agents without hub approval
4. peer-to-peer autonomous escalation loops

---

## 7. Recommended Automation Layers

## Layer 1: Manual-triggered, Hub-managed
Start here.

Characteristics:
- Raphael님 asks HermesPM
- HermesPM dispatches work
- external workers are triggered semi-manually or via lightweight wrappers
- HermesVerifier compares results
- HermesPM reports back

Why first:
- simplest
- safest
- validates the operating model before deeper automation

## Layer 2: Scheduled and repeatable workflows
After Layer 1 proves useful.

Add:
- cron recurring review jobs
- daily state sync
- stale worker alerts
- automatic request templates

## Layer 3: Structured remote execution
After transport is stable.

Add:
- remote job queue on MacBook
- worker result envelopes
- automatic handoff + review chain

## Layer 4: Full observability overlay
Optional.

Add:
- Claw3D visualization
- dashboard for status / queue / last verdict / blocked tasks
- optional Paperclip-style org view if desired

---

## 8. Paperclip vs Custom System Decision

## Option A: Adopt Paperclip as the core system

Pros:
- strong company/org metaphor
- built-in concepts like goals, heartbeats, budgets
- aligns with multi-agent organizational thinking
- OpenClaw-friendly ecosystem

Cons:
- likely introduces another core control plane
- Hermes becomes “one worker among others” instead of the natural hub
- mixed stack integration will need adaptation anyway
- may create conceptual duplication with Hermes profiles, cron, kanban, memory
- more moving parts than necessary for first real deployment

Verdict:
Not recommended as the initial core for Raphael님’s current environment.

## Option B: Use Paperclip as design inspiration, build hub around Hermes

Pros:
- matches current always-on Windows PC reality
- Hermes already strong at memory, reports, messaging, cron, kanban, orchestration
- easier to add OpenClaw and Claude Code as external workers
- lower integration risk
- easier to evolve incrementally

Cons:
- requires some custom conventions and wrappers
- not as immediately “company-like” out of the box
- dashboard/heartbeat UX may need custom work

Verdict:
Recommended primary direction.

## Option C: Hybrid
- Hermes is operational hub
- Paperclip runs in separate sandbox for org-model experiments
- later import the useful conventions into the main system

Verdict:
Very good second-phase strategy.

### Final Decision
Recommended path:
1. build the real operating system around Hermes
2. borrow Paperclip ideas: roles, goals, heartbeats, dashboard mindset
3. optionally trial Paperclip in a sandbox later
4. optionally add Claw3D as visualization after orchestration is stable

---

## 9. Why Windows PC Should Be the Hub

Windows PC is the best current hub because:

1. It is usually always on.
2. A central hub benefits more from uptime than from portability.
3. Hermes is well-suited for always-on orchestration and reporting.
4. Discord/gateway/cron/kanban are natural to centralize there.
5. MacBook should remain a specialist worker host, not the control plane.

### Caveats

1. If running through WSL, make sure service persistence is well managed.
2. Prefer a stable directory structure and durable logs.
3. If later reliability becomes critical, migrate the hub to Ubuntu bare metal / VM / mini server while keeping the logical architecture unchanged.

Verdict:
Yes, Raphael님’s Windows PC is suitable as the current central operations hub.

---

## 10. Minimal Viable System (MVS)

Phase 1 goal: create a functioning cross-validation loop without overbuilding.

### Required components

On Windows PC:
- HermesPM profile
- HermesVerifier profile
- HermesPlanner profile
- Discord or local command intake path
- local reports directory
- cron for digest/monitoring

On MacBook:
- OpenClaw running
- Claude Code available
- one controllable transport path back to hub

### Required conventions

1. Standard Task Brief format
Fields:
- task_id
- objective
- context
- constraints
- expected output format
- deadline / urgency
- reviewer checklist

2. Standard Result Envelope format
Fields:
- task_id
- worker_name
- timestamp
- summary
- artifact_paths_or_links
- confidence
- blockers
- suggested next step

3. Standard Verification Report format
Fields:
- compared_workers
- agreement points
- contradictions
- missing pieces
- recommended winner / synthesis
- risk notes

---

## 11. Concrete Automation Roadmap

### Phase 1: Manual orchestration with standardized artifacts
Duration: short

Tasks:
- define task brief template
- define result envelope template
- define verification report template
- create HermesPM / HermesVerifier / HermesPlanner profile responsibilities
- store reports under a shared folder on Windows PC

Expected outcome:
- repeatable human-in-the-loop orchestration

### Phase 2: Semi-automation
Tasks:
- HermesPM auto-generates briefs
- cron reminders for unfinished tasks
- daily summary across workers
- Discord notifications for completed reviews

Expected outcome:
- lower coordination overhead

### Phase 3: Remote worker wrappers
Tasks:
- wrapper for dispatching work to OpenClaw
- wrapper for dispatching work to Claude Code
- automatic ingestion of their result envelopes

Expected outcome:
- reduced manual copy/paste between environments

### Phase 4: Visualization and operations console
Tasks:
- optional Claw3D setup on Windows PC
- remote OpenClaw presence from MacBook
- optional Hermes adapter office
- optional lightweight dashboard for verdicts, queue, blocked items

Expected outcome:
- improved observability without changing the core operating model

### Phase 5: Paperclip sandbox experiment
Tasks:
- install Paperclip in a non-critical environment
- test org chart / heartbeat / budget concepts
- import only the concepts that prove useful

Expected outcome:
- informed decision without destabilizing main operations

---

## 12. Security and Reliability Notes

1. Do not expose raw worker control surfaces publicly unless necessary.
2. Prefer Tailscale or private networking.
3. Keep the hub as the authority for task IDs and final verdicts.
4. Treat MacBook workers as intermittently available.
5. Use human approval for destructive actions until the system earns trust.
6. Persist reports and verdicts to disk so the system is auditable.

---

## 13. Recommended Final Direction

### Immediate Recommendation
Build a custom Hermes-centered operations hub on the always-on Windows PC.

### Use Paperclip how?
Use Paperclip as reference material, not as the immediate control plane.

What to borrow from Paperclip:
- org/role thinking
- heartbeats
- goals
- dashboards
- budget awareness

What not to do yet:
- do not make Paperclip the primary production control layer on day 1
- do not force Hermes/OpenClaw/Claude Code into one foreign orchestration model too early

### Use Claw3D how?
Use Claw3D later as a visibility layer if Raphael님 wants a visual operations center.
It is additive, not foundational.

---

## 14. Final Recommendation in One Sentence

Raphael님 환경에는 “Paperclip을 그대로 메인으로 도입”하기보다, 상시 켜진 Windows PC의 Hermes를 중앙 허브로 삼아 별도 운영 시스템을 만들고, Paperclip은 설계 참고용으로 활용하며, Claw3D는 나중에 관찰 UI로 추가하는 방향이 가장 현실적이고 확장성도 좋다.

---

## 15. Next Recommended Deliverables

If proceeding, the next documents/artifacts should be:

1. `agent-role-matrix.md`
- each agent/profile role and responsibilities

2. `task-brief-template.md`
- normalized job spec format

3. `result-envelope-template.md`
- standard worker output schema

4. `verification-report-template.md`
- HermesVerifier decision format

5. `operations-runbook.md`
- startup, shutdown, failure, retry procedures

6. `transport-options-evaluation.md`
- Discord vs SSH vs Tailscale vs watched-folder job bus

These should be created before deep automation work begins.

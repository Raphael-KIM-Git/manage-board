# Agent Role Matrix

> 목적: Raphael님의 실제 멀티 에이전트 운영 환경에서 각 에이전트/프로필/실행 환경의 역할, 책임, 입력, 출력, 검증 관계를 명확히 정의한다.

## 1. System Context
- Central Hub Host: Windows PC (always-on) running Hermes orchestration in WSL Ubuntu
- Worker Host A: MacBook
- Worker Host B: Windows PC / WSL Ubuntu
- Messaging Layer: Hermes gateway / Discord (preferred), local terminal fallback
- Scheduling Layer: Hermes cron on hub
- Storage/Reports Path: `/home/raphael/myproject/docs/plans/` and future operations report directories under hub-managed storage

---

## 2. Current Deployment Assumption

### MacBook
- Claude Code available
- OpenClaw available
- best used as specialist worker host
- not the source of truth for global task state

### Windows PC
- physically always on
- best current candidate for central operations hub
- recommended to run orchestration logic in Ubuntu/WSL
- owns reports, schedules, verification, and final summaries

---

## 3. Role Matrix

| Agent / Profile | Host | Primary Role | Secondary Role | Typical Inputs | Typical Outputs | Reviews Whom | Reviewed By | Automation Level | Notes |
|---|---|---|---|---|---|---|---|---|---|
| HermesPM | Windows PC / WSL Ubuntu | Intake, decomposition, final decision, reporting | escalation, priority, route selection | user requests, prior reports, verification reports, planner briefs | final summary, assignment decision, routing choice, next action | all workers indirectly | Raphael님 | semi-auto | canonical source of truth |
| HermesPlanner | Windows PC / WSL Ubuntu | planning, scoping, brief normalization | execution-mode selection | raw request, project context, prior decisions | task brief, execution recommendation, scoped deliverables | none directly | HermesPM / HermesVerifier | high | should convert vague asks into structured work packets |
| HermesVerifier | Windows PC / WSL Ubuntu | cross-agent review, contradiction detection, synthesis | risk grading, evidence check | result envelopes, artifacts, logs, worker summaries | verification report, winner recommendation, revision request | Claude Code Worker, OpenClaw Worker, HermesImplementer | HermesPM | high | should never silently bless unverifiable claims |
| HermesImplementer | Windows PC / WSL Ubuntu | Hermes-native execution worker | fallback implementation, third opinion | task brief | result envelope, artifact references, implementation notes | optional peer | HermesVerifier | medium | use when a third independent attempt adds value |
| OpenClaw Worker | MacBook | autonomous execution, alternate implementation | exploration, long-form runs | task brief, scoped context | result envelope, artifacts, notes, blockers | optional peer | HermesVerifier | medium | best treated as specialist worker, not global coordinator |
| Claude Code Worker | MacBook | code-centric execution, alternate implementation, code review | patch refinement, structured code feedback | task brief, repository context | result envelope, code patch, implementation notes, review comments | optional peer | HermesVerifier | medium | often strongest for code precision and local implementation feedback |
| Raphael님 | Human | strategic direction, final approval for risky/destructive actions | override authority, system tuning | PM final summary, verification reports, blockers | approvals, prioritization, corrected direction | all indirectly | none | manual | final escalation authority |

---

## 4. Role Definitions

### HermesPM
Responsibilities:
- receive tasks from Raphael님
- classify task type
- choose execution mode
- assign planner/verifier flow
- maintain canonical task state
- produce final user-facing result

Should decide among:
- single-worker mode
- primary + independent review mode
- competitive multi-worker mode
- pipeline mode

Must not:
- skip verification for high-risk or high-value tasks
- claim completion without worker evidence when execution was delegated

### HermesPlanner
Responsibilities:
- translate requests into standardized briefs
- define deliverables, constraints, and evaluation criteria
- identify whether the task needs:
  - speed
  - redundancy
  - independent verification
  - specialist worker assignment

Must produce:
- task ID
- objective
- context
- constraints
- required deliverable
- verification focus

### HermesVerifier
Responsibilities:
- compare worker outputs
- detect contradictions and hidden assumptions
- check artifacts and confidence claims
- recommend winner, synthesis, or revision

Must explicitly answer:
- what is verified?
- what is only claimed?
- where do outputs conflict?
- what should PM tell Raphael님?

### HermesImplementer
Responsibilities:
- act as Hermes-native worker when:
  - only one worker is needed
  - the MacBook workers are unavailable
  - a third opinion is desired

Typical use:
- implementation fallback
- third competitive solve attempt
- lightweight internal test task

### OpenClaw Worker
Responsibilities:
- perform autonomous implementation/exploration
- return structured result envelope
- provide artifacts, not just claims

Best use cases:
- exploratory execution
- alternate implementation strategy
- independent second opinion

### Claude Code Worker
Responsibilities:
- provide implementation or structured code review
- return patch- or code-oriented output in the standard envelope

Best use cases:
- code-heavy tasks
- precision implementation
- alternative implementation path
- review of code generated elsewhere

---

## 5. Default Review Relationships

### Standard pipeline
1. HermesPM receives request
2. HermesPlanner writes task brief
3. assigned worker executes
4. HermesVerifier reviews result
5. HermesPM reports final verdict

### Competitive mode
1. HermesPlanner creates one shared brief
2. OpenClaw Worker executes
3. Claude Code Worker executes
4. optional HermesImplementer executes
5. HermesVerifier compares all results
6. HermesPM selects winner or synthesis

### Primary + review mode
1. HermesPlanner creates brief
2. primary worker executes
3. secondary worker or HermesVerifier reviews
4. HermesPM finalizes summary

---

## 6. Decision Rights

| Decision Type | Owner | Backup | Notes |
|---|---|---|---|
| Task intake and routing | HermesPM | Raphael님 | PM is default routing authority |
| Brief structure and scope | HermesPlanner | HermesPM | planner proposes, PM may tighten scope |
| Verification verdict | HermesVerifier | HermesPM | PM may override but should record why |
| Final user-facing response | HermesPM | Raphael님 | PM is reporting authority |
| Risky / destructive approval | Raphael님 | none | never auto-approve early-stage system |
| Fallback when MacBook workers unavailable | HermesPM | HermesImplementer | keep system moving without splitting authority |

---

## 7. Recommended Execution Modes by Task Type

| Task Type | Preferred Mode | Notes |
|---|---|---|
| quick factual/system check | single-worker | usually HermesImplementer or PM direct tooling |
| code implementation | primary + review | Claude Code or OpenClaw primary, verifier review |
| architecture decision | competitive | best when two independent views are valuable |
| research synthesis | competitive or pipeline | planner -> workers -> verifier -> PM |
| risky config/deploy change | primary + review + human approval | no auto-destructive step |
| long exploratory task | OpenClaw primary + verifier | use result envelope strictly |

---

## 8. Failure Handling

| Failure Case | Primary Response | Escalation |
|---|---|---|
| MacBook worker unavailable | route to alternate MacBook worker or HermesImplementer | HermesPM informs Raphael님 if capacity degraded |
| worker returned low-confidence result | send to HermesVerifier with caution flag | HermesPM decides retry or alternate worker |
| outputs conflict materially | require formal verification report | HermesPM chooses revision, synthesis, or escalation |
| no verifiable artifact | treat as partial result, not success | HermesVerifier flags and PM reports honestly |
| hub-side schedule/report failure | repair hub first | Raphael님 informed if coordination degraded |

---

## 9. Operational Notes
- All official task state should live on the hub, not on the MacBook workers.
- The hub should own task IDs and final verdict storage.
- Workers should be treated as execution endpoints.
- Competitive mode should be reserved for important/high-uncertainty tasks, not everything.
- Verification should be mandatory for high-value outputs.

---

## 10. Immediate Next Fill-Ins

### Active Profiles
- HermesPM: existing / to be hardened as hub coordinator
- HermesPlanner: existing planner profile or new dedicated profile
- HermesVerifier: recommended new dedicated verifier profile
- HermesImplementer: optional new execution profile or reuse default Hermes

### Current Host Mapping
- Windows PC host name: TBD by Raphael님
- WSL distro / Ubuntu version: current Ubuntu/WSL environment
- MacBook host name: TBD by Raphael님
- OpenClaw endpoint: TBD during transport design
- Claude Code invocation path: TBD during transport design

### Preferred Near-Term Transport
- primary coordination: Hermes on hub
- remote worker transport: TBD (likely SSH / watched-folder / messaging-assisted pattern)
- reporting destination: Discord and local markdown reports

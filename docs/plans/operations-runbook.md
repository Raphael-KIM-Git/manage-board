# Operations Runbook

> 목적: Raphael님의 멀티 에이전트 운영 시스템을 실제로 시작, 운영, 점검, 장애 대응, 검증 루프 실행까지 할 수 있게 만드는 초기 운영 절차 문서.

## 1. Scope

이 runbook은 아래 운영 구조를 전제로 한다.

- Central Hub: Windows PC running Hermes orchestration in WSL Ubuntu
- Remote Worker Host: MacBook
- Remote Workers:
  - Claude Code Worker
  - OpenClaw Worker
- Hub Roles:
  - HermesPM
  - HermesPlanner
  - HermesVerifier
  - optional HermesImplementer

Claw3D는 현재 범위에서 제외한다.

---

## 2. Operating Principles

1. The hub is the source of truth.
2. Workers execute; the hub decides.
3. High-value outputs should be verified before final reporting.
4. Destructive or irreversible actions require human approval.
5. Every delegated task should produce a result envelope.
6. Every multi-worker comparison should produce a verification report.

---

## 3. Standard Directory / Document Set

Core docs:
- operations architecture:
  - `/home/raphael/myproject/docs/plans/2026-06-21-multi-agent-operations-architecture.md`
- role matrix:
  - `/home/raphael/myproject/docs/plans/templates/agent-role-matrix.md`
- task brief template:
  - `/home/raphael/myproject/docs/plans/templates/task-brief-template.md`
- result envelope template:
  - `/home/raphael/myproject/docs/plans/templates/result-envelope-template.md`
- verification report template:
  - `/home/raphael/myproject/docs/plans/templates/verification-report-template.md`

Recommended future directories:
- `/home/raphael/myproject/operations/briefs/`
- `/home/raphael/myproject/operations/results/`
- `/home/raphael/myproject/operations/verifications/`
- `/home/raphael/myproject/operations/digests/`

---

## 4. Startup Procedure

### 4.1 Start of Day / Start of Session

Hub checklist:
1. Confirm WSL Ubuntu environment is available.
2. Confirm Hermes profiles are accessible.
3. Confirm report/document directories exist.
4. Confirm messaging path (Discord or local workflow) is available.
5. Confirm cron/scheduler status if using scheduled digests.

MacBook checklist:
1. Confirm Claude Code is available.
2. Confirm OpenClaw is available.
3. Confirm MacBook is reachable by the chosen transport path.
4. Confirm workers are not mid-failure or stale from prior runs.

### 4.2 Hub readiness questions
Before beginning serious work, answer:
- Can HermesPM receive requests?
- Can HermesPlanner produce briefs?
- Can HermesVerifier write review reports?
- Can at least one remote worker be reached?

If the answer to the last question is no:
- operate in hub-only fallback mode
- use HermesImplementer where possible
- report reduced capacity clearly

---

## 5. Core Workflows

## 5.1 Workflow A — Single-worker mode
Use when:
- low complexity
- low risk
- low value of redundancy

Steps:
1. HermesPM receives task.
2. HermesPlanner creates a task brief.
3. One worker executes.
4. Worker returns result envelope.
5. HermesPM either:
   - responds directly for low-risk work, or
   - asks HermesVerifier for a quick review if needed.

Output artifacts:
- task brief
- result envelope
- optional quick verification note

## 5.2 Workflow B — Primary + review mode
Use when:
- one worker is preferred
- independent review is still useful

Steps:
1. HermesPM receives task.
2. HermesPlanner creates task brief.
3. Primary worker executes.
4. Primary worker returns result envelope.
5. HermesVerifier or secondary reviewer examines output.
6. HermesPM returns final verdict.

Typical use cases:
- code change
- architecture recommendation
- configuration change
- documentation draft

Required artifacts:
- task brief
- primary result envelope
- verification report or quick review note

## 5.3 Workflow C — Competitive mode
Use when:
- output quality matters more than speed
- independent approaches may differ meaningfully
- architectural, implementation, or research uncertainty is high

Steps:
1. HermesPM classifies task as competitive.
2. HermesPlanner creates a single shared task brief.
3. Same brief goes to:
   - OpenClaw Worker
   - Claude Code Worker
   - optional HermesImplementer
4. Each returns a result envelope.
5. HermesVerifier compares all outputs.
6. HermesPM chooses:
   - winner
   - synthesis
   - revision request
7. HermesPM reports final result to Raphael님.

Required artifacts:
- one shared brief
- two or more result envelopes
- one formal verification report

## 5.4 Workflow D — Pipeline mode
Use when:
- planning, execution, and review are naturally distinct
- longer or more structured jobs are being performed

Steps:
1. HermesPlanner writes brief.
2. Worker executes.
3. HermesVerifier reviews.
4. HermesPM summarizes and routes next action.

---

## 6. Daily Heartbeat Procedure

Recommended cadence:
- once daily minimum
- twice daily if work volume is high

Heartbeat questions:
1. What tasks are in progress?
2. What tasks are blocked?
3. Which worker has not returned results recently?
4. Are there unresolved verification reports?
5. What should be prioritized next?

Suggested daily digest contents:
- active task count
- completed task count
- blocked tasks
- pending verifications
- worker availability summary
- recommended next top 3 actions

Recommended owner:
- generated by HermesPM or cron-triggered Hermes summary flow

---

## 7. Weekly Review Procedure

Once per week, review:
1. Which worker types produced the best results?
2. Which kinds of tasks required competitive mode?
3. Which tasks wasted time with unnecessary redundancy?
4. What repeated blockers appeared?
5. Which transport / coordination friction should be reduced?

Weekly output should answer:
- what to keep
- what to reduce
- what to automate next

---

## 8. Failure / Incident Response

## 8.1 MacBook unavailable
Symptoms:
- no response from Claude Code Worker
- no response from OpenClaw Worker
- transport path unavailable

Response:
1. mark remote capacity degraded
2. route urgent work to HermesImplementer where possible
3. avoid competitive mode until restored
4. report reduced confidence for tasks that would normally use redundancy

## 8.2 Worker returns non-verifiable success
Symptoms:
- success claimed but no artifact
- vague result with no handle/path/output

Response:
1. treat result as partial, not final
2. HermesVerifier flags missing verification evidence
3. HermesPM either requests revision or routes to alternate worker

## 8.3 Conflicting worker outputs
Symptoms:
- materially different conclusions
- incompatible implementation paths
- disagreement about observed facts

Response:
1. create formal verification report
2. identify agreement points and contradictions
3. request third opinion if needed
4. HermesPM presents either winner or synthesis

## 8.4 Hub-side issue
Symptoms:
- PM/planner/verifier flow unavailable
- report storage unavailable
- scheduled heartbeat broken

Response:
1. stop new complex multi-worker runs
2. restore hub functionality first
3. keep only minimal local/manual operation if needed
4. avoid losing canonical task state

---

## 9. Escalation Rules

Escalate to Raphael님 when:
- destructive action is requested
- worker disagreement materially affects decision quality
- no verifiable output exists for an important task
- the hub cannot maintain source-of-truth state
- remote worker availability is degraded for an extended time

Do not escalate unnecessarily for:
- low-risk formatting work
- obvious retries
- routine brief normalization

---

## 10. Quality Gates

A task should not be marked truly complete unless:
- a task brief existed or the task was trivially simple
- the worker returned a structured result
- artifacts or verifiable handles exist for success claims
- verification occurred for high-value/high-risk work
- HermesPM can explain what is verified vs merely suggested

Minimum quality gate for important tasks:
- brief
- result envelope
- verification report
- PM final summary

---

## 11. Recommended First Automation Targets

Automate first:
1. daily heartbeat digest
2. stale task reminders
3. brief generation scaffold
4. result envelope normalization
5. verification report drafting

Automate later:
1. remote worker dispatch wrappers
2. automatic result ingestion
3. worker scoring / routing heuristics
4. dashboard views

Do not automate early:
1. destructive command approval
2. merge/deploy authority
3. uncontrolled agent-to-agent recursion

---

## 12. Change Management

When changing the system:
- update role matrix if responsibilities change
- update templates if output format changes
- record transport/path changes in the runbook
- prefer one operational change at a time
- validate with a low-risk task before full adoption

---

## 13. Recommended Immediate Next Steps

1. Create dedicated HermesVerifier profile if not already present.
2. Choose the first real transport method for MacBook workers.
3. Test one competitive-mode task end-to-end.
4. Store the resulting brief, envelopes, and verification report.
5. Review where manual friction is highest.
6. Automate that friction next.

---

## 14. Runbook Summary

The intended operating model is simple:
- Raphael님 gives the task to HermesPM.
- HermesPlanner standardizes the task.
- workers execute.
- HermesVerifier compares and validates.
- HermesPM gives the final answer.
- the hub stores the truth.

That is the core system.

# Task Brief Template

> 목적: 어떤 worker(OpenClaw, Claude Code, Hermes worker)에게 전달하더라도 같은 기준으로 작업하게 만드는 표준 작업 지시서.

## 1. Task Metadata
- Task ID:
- Created At:
- Created By:
- Priority: low / medium / high / critical
- Execution Mode: single / primary+review / competitive / pipeline
- Deadline / Urgency:
- Assigned Workers:
- Reviewer:

---

## 2. Objective
한 줄 목표:

상세 목표:
- 
- 
- 

---

## 3. Background Context
이 작업이 왜 필요한가:

관련 프로젝트/시스템:

이미 알고 있는 사실:
- 
- 
- 

과거 결정/제약:
- 
- 

---

## 4. Inputs Provided
- Files:
- URLs:
- Prior reports:
- Screenshots / assets:
- Environment / host constraints:

---

## 5. Required Deliverable
반드시 제출해야 하는 것:
- summary
- detailed findings or implementation notes
- artifact paths or links
- blockers / assumptions
- confidence level

원하는 출력 형식:
- markdown report
- code patch
- review checklist
- JSON summary
- other:

---

## 6. Constraints
반드시 지켜야 할 제약:
- do not do destructive actions without approval
- do not claim success without verifiable artifact
- do not fabricate tool output

작업별 추가 제약:
- 
- 
- 

---

## 7. Evaluation Criteria
성공 기준:
- 
- 
- 

좋은 결과의 기준:
- correctness
- completeness
- evidence-backed claims
- clarity of next step

실패로 간주되는 경우:
- unverifiable success claims
- missing artifacts
- major contradictions
- ignoring constraints

---

## 8. Worker Instructions
권장 작업 방식:
1. understand objective
2. inspect available context
3. execute or analyze
4. verify result
5. return standard result envelope

특별 지시:
- 
- 

---

## 9. Verification Focus
리뷰어가 특히 볼 항목:
- factual correctness
- contradictions
- hidden risks
- missing edge cases
- implementation mismatch vs brief

---

## 10. Result Envelope Required
아래 항목을 반드시 포함해서 반환:
- task_id
- worker_name
- summary
- detailed_output
- artifact_paths_or_links
- blockers
- assumptions
- confidence
- suggested_next_step

---

## 11. Example Short Form
- Task ID: T-2026-001
- Objective: compare two deployment approaches for service X
- Workers: OpenClaw, Claude Code
- Reviewer: HermesVerifier
- Deliverable: markdown report + recommendation
- Constraints: no actual deployment, evidence only
- Success: clear pros/cons, recommended choice, explicit risks

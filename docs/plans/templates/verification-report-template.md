# Verification Report Template

> 목적: HermesVerifier가 여러 worker의 결과를 비교하고, 최종적으로 무엇을 믿고 무엇을 버릴지 구조적으로 판정하기 위한 템플릿.

## 1. Verification Metadata
- Verification ID:
- Related Task ID:
- Reviewer: HermesVerifier
- Reviewed Workers:
- Reviewed At:
- Verification Type: single-review / pairwise-compare / multi-way-synthesis

---

## 2. Review Scope
무엇을 검증하는가:
- factual correctness
- implementation quality
- completeness
- constraint compliance
- artifact validity
- risk profile

이번 검증의 특별 포인트:
- 
- 
- 

---

## 3. Inputs Reviewed
- worker output A:
- worker output B:
- worker output C:
- artifacts checked:
- external references checked:

---

## 4. Agreement Points
여러 결과가 공통으로 말하는 점:
1. 
2. 
3. 

이 공통점의 신뢰도:
- low / medium / high

---

## 5. Contradictions
서로 충돌하는 주장:
1. 
2. 
3. 

충돌 원인 추정:
- different assumptions
- incomplete evidence
- one worker hallucinated / overclaimed
- environment mismatch
- other:

---

## 6. Missing Pieces
아직 누구도 충분히 답하지 못한 부분:
- 
- 
- 

추가 검증이 필요한 항목:
- 
- 

---

## 7. Artifact Validity Check
검증 가능한 산출물 점검:
- Worker A artifacts valid? yes / partial / no
- Worker B artifacts valid? yes / partial / no
- Worker C artifacts valid? yes / partial / no

메모:
- 
- 

---

## 8. Quality Assessment by Worker
### Worker A
- Strengths:
- Weaknesses:
- Trust Level: low / medium / high

### Worker B
- Strengths:
- Weaknesses:
- Trust Level: low / medium / high

### Worker C
- Strengths:
- Weaknesses:
- Trust Level: low / medium / high

---

## 9. Verdict
판정 유형:
- choose winner
- combine best parts
- request revision
- insufficient evidence

최종 판정:

왜 이렇게 판정했는가:
- 
- 
- 

---

## 10. Recommended Output to PM
HermesPM이 사용자에게 전달할 핵심:
- best answer / best implementation path
- caveats and risks
- what was verified vs not verified
- next recommended action

짧은 전달 문안 초안:
- 
- 

---

## 11. Follow-Up Action
- none
- ask worker A to revise
- ask worker B to revise
- run third opinion
- escalate to Raphael님

세부 후속 조치:
- 
- 

---

## 12. Final Structured Verdict
```json
{
  "task_id": "",
  "reviewed_workers": [],
  "agreement_points": [],
  "contradictions": [],
  "missing_pieces": [],
  "artifact_validity": {},
  "winner": "",
  "verdict_type": "combine best parts",
  "confidence": "medium",
  "recommended_next_action": ""
}
```

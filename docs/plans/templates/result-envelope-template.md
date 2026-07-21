# Result Envelope Template

> 목적: 어떤 worker가 작업했든 동일한 형식으로 결과를 회수해서 HermesVerifier와 HermesPM이 자동 비교/요약하기 쉽게 만든다.

## 1. Metadata
- Task ID:
- Worker Name:
- Worker Type: Hermes / OpenClaw / Claude Code / Other
- Host:
- Started At:
- Finished At:
- Duration:
- Status: success / partial / blocked / failed

---

## 2. Executive Summary
한 줄 요약:

짧은 요약 (3~7문장):
- 
- 
- 

---

## 3. What Was Done
실제로 수행한 작업:
1. 
2. 
3. 

사용한 주요 도구/접근:
- 
- 

---

## 4. Main Output
핵심 결과:

상세 결과:
- 
- 
- 

---

## 5. Artifacts
검증 가능한 산출물:
- file paths:
- URLs:
- command outputs:
- IDs / references:

주의:
- success claim must be backed by at least one artifact or observable handle.

---

## 6. Assumptions
이번 결과가 전제한 가정:
- 
- 
- 

---

## 7. Blockers / Limitations
막힌 점 또는 제한:
- 
- 
- 

이 때문에 못한 것:
- 
- 

---

## 8. Confidence
- Confidence Level: low / medium / high
- Confidence Rationale:
  - 
  - 

---

## 9. Suggested Next Step
권장 다음 단계:
- 
- 
- 

---

## 10. Ready for Verification Checklist
- [ ] task_id included
- [ ] summary included
- [ ] artifacts included
- [ ] assumptions listed
- [ ] blockers listed
- [ ] confidence assigned
- [ ] next step proposed

---

## 11. JSON-Friendly Field Map
```json
{
  "task_id": "",
  "worker_name": "",
  "worker_type": "",
  "host": "",
  "status": "success",
  "started_at": "",
  "finished_at": "",
  "duration": "",
  "summary": "",
  "detailed_output": "",
  "artifact_paths_or_links": [],
  "assumptions": [],
  "blockers": [],
  "confidence": "medium",
  "suggested_next_step": ""
}
```

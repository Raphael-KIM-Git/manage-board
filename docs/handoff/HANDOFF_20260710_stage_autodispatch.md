# 맥북 Claude → Hermes 지시문: 파이프라인 단계 자동 진행 구현 요청 (2026-07-10)

## 1. 배경 — 맥북 쪽 준비 완료

`operations/instructions/macbook-agent-pipeline-setup.md` 스펙의 맥북 쪽 작업이 끝났다.

- inbox 4개 운영 중: `~/agent-hub/inbox/{researcher-co,writer-co,verify-co,researcher_agent}`
- 실행 방식: researcher-co/writer-co/verify-co는 `claude -p --agent <이름>` (모델: sonnet/opus/opus),
  researcher_agent는 openclaw
- result envelope에 스펙 필수 필드 포함: `task_id`, `worker_name`, `worker_key`, `status`,
  `completed_at`, `summary`, `artifacts`
- self-test 통과: `T-20260710-900__researcher-co.{json,md}` (허브에 이미 수집됨, 85초 소요)
- 허브 `workers.json`의 4개 worker 설정도 확인 완료 — dispatch 경로는 지금 바로 사용 가능

## 2. 요청 사항 — 허브 쪽 단계 자동 진행 (hub-pipeline-spec.md "다음 확장 포인트")

research 결과가 수집되면 사람 개입 없이 다음 단계가 이어지도록 구현해 달라:

1. **writing 자동 dispatch**: research 단계 결과가 모이면(`waiting_verification` 판정 시점),
   research 산출물(md)을 context에 포함한 writing brief를 생성해 `writer-co` inbox로 전송
2. **verification 자동 dispatch**: writing 결과 수집 시 draft 본문을 포함한 verification brief를
   `verify-co` inbox로 전송 (HermesVerifier 로컬 검증과 병행 여부는 Hermes 판단)
3. **final_write 자동 dispatch**: verification 결과 수집 시 검증 피드백을 포함한 final brief를
   `writer-co` inbox로 전송
4. 각 단계 진행 시 task JSON의 `stages[].status`와 `status`를 갱신해 대시보드에 반영

실행 주체는 기존 `operations_sync.py`(Windows 작업 스케줄러 `AgentHubResultSync`, 2분 주기) 확장을
권장한다. **서버 프로세스(`operations_dashboard_server.py`) 안에 타이머/루프를 넣지 말 것** —
블로킹 이슈 재발 방지 원칙.

## 3. 설계 시 주의할 함정 3가지 (중요)

### 3-1. 결과 파일명 충돌: writing과 final_write가 둘 다 writer-co
맥 러너는 `results/<task_id>__<worker_key>.{json,md}`로 저장하고, **같은 task_id+worker_key 결과가
이미 있으면 재처리하지 않는다** (멱등성). 따라서 writing과 final_write에 같은 task_id를 쓰면
final_write가 영원히 skip된다.

→ 권장: 단계별 파생 task_id를 brief에 넣어 dispatch할 것. 예:
- writing: `T-20260710-001-writing`
- final_write: `T-20260710-001-final`
- verification: `T-20260710-001-verify` (일관성 위해 동일 규칙 권장)

맥 러너는 brief의 `task_id`를 그대로 파일명에 쓰므로 맥 쪽 수정 없이 동작한다.
허브 수집 후 원본 task와 매핑할 때는 prefix(`T-20260710-001`) 기준으로 집계하면 된다.

### 3-2. briefs/ 디렉터리 오염
허브의 task 목록은 `briefs/T-*.json` glob 기준이다. 단계별 파생 brief JSON을 `briefs/`에
저장하면 각 단계가 별도 task로 잡혀 대시보드가 오염된다.

→ 파생 brief는 `dispatches/` 또는 새 디렉터리(예: `operations/stage-briefs/`)에 저장하고,
scp 전송만 할 것. `briefs/`에는 원본 task JSON만 유지.

### 3-3. 중복 dispatch 방지 (2분마다 재실행됨)
sync는 2분마다 돌므로 "이미 dispatch한 단계인지"를 판별할 마커가 필요하다.

→ 권장: task JSON의 `stages[].status`를 dispatch 직후 `in_progress`로 저장하고,
`planned`/`queued`인 단계만 dispatch 대상으로 삼을 것. dispatch 기록은 기존
`dispatches/`에 남기면 추적 가능.

## 4. 단계별 brief 작성 가이드

맥 러너의 프롬프트는 brief의 `title/objective/context/constraints/deliverable` 필드로 구성된다.
context 필드에 이전 단계 산출물 **본문을 직접 포함**해 줄 것 (맥 쪽은 허브 파일시스템에
접근할 수 없으므로 경로만 주면 읽지 못한다). 산출물이 길면 앞부분 요약 + 핵심 섹션 위주로.

- writing brief context: research 결과 md 본문 (researcher-co + researcher_agent 결과 모두)
- verification brief context: writing 결과 md 본문 + 원본 objective
- final brief context: writing draft + verification 지적 사항

## 5. 검증 시나리오 (구현 후 실행 권장)

1. 대시보드에서 소형 task 생성 (예: "간단 주제 1건 조사 후 1페이지 요약")
2. research dispatch → 맥북 결과 수집 확인
3. 2분 주기 sync가 writing을 자동 dispatch하는지 확인 → `T-...-writing__writer-co.md` 수집
4. verification, final_write까지 자동 진행 확인
5. task 카드의 stages가 순서대로 completed로 바뀌는지 확인
6. 같은 task로 sync가 여러 번 돌아도 중복 dispatch가 없는지 확인 (3-3 검증)

## 6. 참고

- 맥 러너 상세: 맥북 `~/agent-hub/README.md` 및 `worker_runner.py`
- 맥 쪽 API 오류(429/5xx/529)는 자동 재시도되므로 허브는 결과 도착만 기다리면 됨
- 이전 인계: `docs/handoff/HANDOFF_20260710_result_sync.md` (수집 스케줄러)
- 문의/수정 요청은 맥북 Claude에게 brief로 보내도 된다 (`claude-code` inbox 유지 중)

---
작성: 맥북 Claude Code (2026-07-10)

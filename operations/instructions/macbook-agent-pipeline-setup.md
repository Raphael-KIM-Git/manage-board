# MacBook Agent Pipeline Setup

목표: MacBook 쪽 기존 에이전트 이름을 유지한 채 Hermes 허브의 새 research/write/verify/final pipeline과 연결한다.

에이전트 이름(그대로 유지)
- Claude researcher: `researcher-co`
- Claude writer: `writer-co`
- Claude verifier: `verify-co`
- OpenClaw researcher: `researcher_agent`

허브 쪽에서 이미 기대하는 inbox 경로
- `~/agent-hub/inbox/researcher-co`
- `~/agent-hub/inbox/writer-co`
- `~/agent-hub/inbox/verify-co`
- `~/agent-hub/inbox/researcher_agent`

허브 쪽에서 결과를 수집하는 경로
- `~/agent-hub/results/`

필수 작업
1. 위 inbox 디렉터리 4개와 `processed/` 하위 디렉터리 생성
2. 각 에이전트가 자신의 inbox JSON brief를 읽고 실행하도록 runner/watcher 업데이트
3. 결과를 `~/agent-hub/results/` 에 result envelope JSON + markdown 보고서로 저장
4. 결과 JSON에는 아래 필드를 꼭 포함
   - `task_id`
   - `worker_name`
   - `worker_key`
   - `status`
   - `completed_at`
   - `summary`
   - `artifacts` (있으면)
5. `worker_key` 값은 아래를 사용
   - `researcher-co` -> `researcher-co`
   - `writer-co` -> `writer-co`
   - `verify-co` -> `verify-co`
   - `researcher_agent` -> `researcher_agent`

권장 파일명
- `results/<task_id>__researcher-co.json`
- `results/<task_id>__researcher-co.md`
- `results/<task_id>__writer-co.json`
- `results/<task_id>__writer-co.md`
- `results/<task_id>__verify-co.json`
- `results/<task_id>__verify-co.md`
- `results/<task_id>__researcher_agent.json`
- `results/<task_id>__researcher_agent.md`

권장 역할 분리
- `researcher-co`: 웹/문서 조사, 소스 정리, 인용/근거 수집
- `researcher_agent`: 병렬 대안 조사, 빠른 스캔, cross-check research
- `writer-co`: research 산출물 기반 초안 작성 + 최종본 정리
- `verify-co`: 초안/최종본의 사실성, 누락, 모순, 위험 확인

허브 기준 기대 pipeline
1. research
   - HermesResearcher
   - researcher-co
   - researcher_agent
2. writing
   - writer-co
3. verification
   - HermesVerifier
   - verify-co
4. final_write
   - writer-co

주의
- 허브는 source of truth 이므로 task 상태는 허브 JSON/task 파일 기준으로 본다.
- MacBook 쪽은 brief 실행과 result 반환에 집중한다.
- 결과가 불완전해도 무응답보다 partial result가 낫다.

MacBook Claude에게 요청할 작업
- 기존 runner/watcher가 있다면 위 4개 inbox를 감시하도록 일반화
- 에이전트별 실행 프롬프트/프로필 이름을 유지
- result envelope 형식을 허브 기대값에 맞춤
- 실행 후 샘플 brief 1개로 self-test 수행

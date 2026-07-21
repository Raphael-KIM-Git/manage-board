# Hermes 구현 요청: HermesResearcher 실제 실행 + json/md 결과 규칙 (2026-07-10)

## 배경 (Raphael 요구사항)

research 단계 에이전트 3종(HermesResearcher/researcher-co/researcher_agent)이 **모두 실제로 동작**하고,
**각각 결과를 json + md 두 파일로 남기길** 원한다.

## 현황

| 에이전트 | 실행 | 결과 파일 |
|---|---|---|
| researcher-co (맥 claude) | 동작 (T-912에서 4분40초) | `results/<task>__researcher-co.{json,md}` 이미 준수 |
| researcher_agent (맥 openclaw) | 동작 (T-912에서 2분52초) | `results/<task>__researcher_agent.{json,md}` 이미 준수 |
| HermesResearcher (PC) | **실행 메커니즘 없음** | 없음 |

HermesResearcher는 현재 `operations_dashboard_server.py`의 단계 정의(agents 배열)와 에이전트 보드 표시에만 존재한다.
workers.json에 미등록이라 dispatch 대상이 아니고, sync에도 실행 코드가 없다. `.hermes/profiles/researcher` 프로필만 있다.

## 요청

research 단계 dispatch 시점에 HermesResearcher를 PC 로컬에서 실행하고, 맥 러너와 동일한 규칙으로 결과를 남겨 달라:

1. **실행**: `operations_sync.py`의 research dispatch 경로(또는 별도 로컬 러너)에서 실행.
   WSL에 네이티브 claude 2.1.206 설치돼 있음 (`/home/raphael/.local/bin/claude`, raphael 인증 완료) —
   `claude -p --agent <에이전트>` 방식 사용 가능. `~/.claude/agents/`에 HermesResearcher.md를 만들면 된다
   (HermesPM.md 참고 — 맥북 Claude가 만들어 둠).
2. **결과 파일 (필수)**: `operations/results/<task_id>__HermesResearcher.md` (보고서 본문)
   + `operations/results/<task_id>__HermesResearcher.json` (envelope).
   envelope 필수 필드: task_id, worker_name, worker_key, status, started_at, completed_at, summary(200자), artifacts, model
   — 맥 결과 파일(T-20260710-912__researcher-co.json)과 같은 형태면 sync/대시보드가 그대로 인식한다.
3. **주의**: 서버 프로세스 안에서 동기 실행 금지(블로킹 원칙). sync 주기 또는 백그라운드 실행으로.
   LLM 실행이 2분 sync 주기보다 길 수 있으니 중복 실행 방지 마커 필요 (stages 마커 또는 results 존재 확인 — 맥 러너와 같은 멱등성 규칙 권장).
4. writing 단계 brief의 context 통합 시 HermesResearcher 결과도 research 산출물로 포함할 것.

## 참고

- 병렬화: 맥 러너는 오늘부터 워커별 병렬 실행(서로 다른 worker inbox 동시 처리)으로 전환됨.
- 관련 공지: NOTE_20260710_dispatch_home_fix.md (dispatch 경로 버그 수정), NOTE_20260710_pm_llm_chat.md (PM LLM 전환)

---
작성: 맥북 Claude Code (2026-07-10)

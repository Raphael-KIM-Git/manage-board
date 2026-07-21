# 변경 공지: PM 채팅 실제 LLM 전환 (2026-07-10, 맥북 Claude)

`operations_dashboard_server.py`와 `operations_dashboard/app.js`를 수정했다. 이 파일들을 편집하기 전에 반드시 최신본을 다시 읽을 것 (구버전으로 덮어쓰면 아래 기능이 사라진다).

## 무엇이 바뀌었나

1. **`/api/pm-brief-assist`가 실제 LLM 호출로 동작** (`pm_brief_assist_llm`)
   - `claude -p --agent HermesPM` 서브프로세스 호출 (WSL 네이티브 설치본, 응답 15~25초)
   - 기존 정규식 로직은 `pm_brief_assist_heuristic`으로 이름 변경, LLM 실패 시 폴백으로 유지
   - 응답에 `engine` 필드 추가: `hermespm-llm` | `heuristic-fallback`
   - env 오버라이드: `OPS_PM_AGENT`(기본 HermesPM), `OPS_PM_CLAUDE_BIN`(기본 claude), `OPS_PM_TIMEOUT`(기본 150초)
2. **`run_command`에 `cwd` 파라미터 추가** (기본 None — 기존 호출부 영향 없음)
3. **`app.js` `sendPmChat`**: 요청 body에 `conversation`(대화 이력 전체) 포함, 응답 대기 중 전송 버튼 비활성화
4. **신규 파일 `~/.claude/agents/HermesPM.md`** — PM 에이전트 정의 (model: sonnet, JSON-only 출력 규칙)

## 환경 변경 (WSL)

- **리눅스 네이티브 Claude Code 2.1.206 설치**: `/home/raphael/.local/bin/claude` (PATH 최우선)
  - 이유: 기존 `/mnt/c/...npm/claude`는 Windows interop 의존이라 detached 서버 프로세스에서 `UtilAcceptVsock accept4 failed`로 실패
- WSL raphael 계정 인증: Windows `.credentials.json` 복사 + onboarding 플래그 설정 완료
- 서버 재시작됨 (11:20, `setsid nohup`, OPS_DASHBOARD_HOST=0.0.0.0)

## 검증 완료

- 자연어 메시지 → LLM 초안 생성 (engine=hermespm-llm, 21.8초)
- 멀티턴 대화 맥락 유지 (QJC 챗봇/PPT 반영, 16.4초)
- LLM 초안 → `/api/tasks` 저장 → 4단계 파이프라인 brief 생성 (T-20260710-911, 검증 후 cancelled 처리)
- 폴백 경로 실동작 확인 (네이티브 설치 전 interop 오류 시 heuristic-fallback으로 정상 응답)

## 단계 자동 dispatch와의 접점

- pm-brief-assist는 brief 생성 전 단계라 auto-dispatch 로직과 충돌 없음
- 단, `claude` CLI를 sync 쪽에서도 쓸 계획이면 네이티브 설치본(`~/.local/bin/claude`)을 쓸 것 — interop 경유는 detached 프로세스에서 실패한다

---
작성: 맥북 Claude Code (2026-07-10)

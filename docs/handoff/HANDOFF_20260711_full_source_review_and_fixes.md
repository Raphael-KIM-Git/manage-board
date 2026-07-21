# Dashboard 전체 소스 리뷰 및 안정화 결과 — 2026-07-11

## 범위

Claude 병행 변경 이후 다음을 전체 검토했다.

- `operations_dashboard_server.py`
- `operations_sync.py`
- `operations_auto_dispatch.py`
- `hermes_local_runner.py`
- `operations_dashboard/index.html`
- `operations_dashboard/app.js`
- `operations_dashboard/styles.css`
- `operations_dashboard/detail.html`
- 관련 handoff 및 `.bak` 흔적

프로젝트는 Git 저장소가 아니므로 commit diff 대신 현재 소스, handoff, 백업, 파일 시각을 기준으로 확인했다.

## 이번에 수정한 오류

### 1. 실패한 research 결과가 완료로 처리되던 오류

기존 `research_stage_complete()`는 assigned worker의 결과 파일이 존재하기만 하면 `status=failed`여도 research 완료로 처리했다.

수정:
- `status == completed`인 결과만 완료 근거로 인정
- worker key를 동일한 정규화 함수로 비교

### 2. PM이 research worker를 1~2개로 축소하면 영구 대기하던 오류

기존 완료 판정은 task의 원래 3개 `assigned_workers`를 계속 기다렸다.

수정 우선순위:
1. `research.dispatched_workers`
2. `task.assigned_workers`
3. `research.agents`

따라서 PM gate가 HermesResearcher 1개만 실제 dispatch했다면 해당 worker 완료로 research를 완료할 수 있다.

### 3. Worker HTML 결과의 동일-origin script 실행 위험

수정:
- Dashboard detail modal iframe에 `sandbox=allow-downloads`
- detail.html iframe에도 동일 sandbox
- referrer policy와 iframe title 추가
- `/files/*.html` 응답에 CSP sandbox 적용
- script/connect/form/object/base 차단
- nosniff/no-referrer 헤더 추가

새 탭 raw HTML도 CSP sandbox를 받으므로 Dashboard API 접근을 차단한다.

### 4. 태블릿 폭에서 중앙 stage가 agent를 가릴 위험

수정:
- 1220px 이하에서도 중앙 안전 여백 유지
- agent tile 폭 축소
- 720px 이하에서는 2×2 기하 구조를 유지하고 board 내부 가로 스크롤 사용

## 추가한 회귀 테스트

파일:
- `/home/raphael/myproject/test_operations_sync.py`

테스트 4개:
- 실패 결과만 있으면 완료되지 않음
- gate 선택 단일 worker 완료
- 일부 완료는 partial
- 선택된 모든 worker 완료

결과:
- 4/4 PASS

## 실행 검증

- Python py_compile: PASS
- JavaScript node --check: PASS
- `/api/health`: HTTP 200
- `/api/tasks`: HTTP 200
- `/api/overview`: HTTP 200
- HTML result CSP sandbox header: 확인
- X-Content-Type-Options nosniff: 확인
- modal/detail iframe sandbox: 확인
- 독립 코드 reviewer: PASSED, blocking issue 없음

## 현재 운영 서버

- URL: `http://127.0.0.1:8765`
- session: `proc_1a0a4fa51416`
- 최신 코드로 running

## 남은 중요 과제

### P0/P1: 동적 pipeline 실행 엔진
현재 PM prompt와 지침은 동적 pipeline을 선택하도록 되어 있지만 task 생성과 sync는 여전히 고정 `research → writing → verification → final_write`를 중심으로 동작한다.

필요:
- PM 출력에 `stages[]`, dependencies, agents, completion policy
- server schema validation
- stage DAG 실행
- legacy task fallback 분리

### P1: Verification 실제 topology
- stage에는 verify-co/HermesVerifier가 표시되지만 stage brief는 verify-co 중심
- runtime rate limit fallback과 local verifier 자동 실행 미완성
- completion policy any/all/quorum의 metadata 기반 판정 필요

### P1: 변경 API 인증
현재 서버를 0.0.0.0으로 열면 task/dispatch/gate API가 인증 없이 접근 가능하다.
필요:
- bearer token 또는 authenticated reverse proxy
- Origin/Host allowlist
- JSON-only 변경 요청
- 요청 크기 제한과 감사 로그

### P1: 파일/동시성 안전성
- local runner task_id path allowlist/containment
- task JSON atomic write + file lock/DB
- concurrent task ID 생성 보호
- remote result staging/schema/size/attempt 검증

### P1/P2: Frontend 운영 신뢰성
- API 일부 실패 시 부분 렌더와 전역 stale 경고
- refresh/poll race 방지
- active stage 대표 선택 우선순위 명시
- modal focus trap/복원
- clickable result의 keyboard semantics
- prefers-reduced-motion

## 독립 리뷰 non-blocking 메모

- 빈 dispatched_workers를 명시적 skip과 미설정으로 구분할 필요가 생기면 None/[] 의미를 분리
- 같은 worker의 과거 completed와 이후 failed가 동시에 존재할 때 최신 attempt 기준 판정 필요
- 721–920px과 긴 worker 이름의 실제 screenshot regression test 권장

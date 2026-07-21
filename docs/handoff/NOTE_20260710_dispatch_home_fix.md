# 긴급 수정 공지: dispatch 원격 경로 버그 (2026-07-10 12:01, 맥북 Claude)

## 증상
7/10 01:27 이후 모든 dispatch(수동 + 단계 자동)가 "dispatched(성공)"로 기록됐지만
실제로는 맥북의 `~/agent-hub/inbox/`가 아니라 **`/Users/raphael/$HOME/agent-hub/inbox/` (리터럴 `$HOME` 디렉터리)**에 들어갔다.
맥 러너는 아무것도 받지 못했다. T-20260710-001~005, 910(writing/verify/final), 912 전부 해당.

## 원인
`operations_dashboard_server.py` `dispatch_to_worker()`:
`remote_inbox_dir.replace('~/', '$HOME/')` + `shlex.quote()` 조합.
- ssh mkdir: `mkdir -p '$HOME/...'` → 작은따옴표 안이라 변수 미확장 → 리터럴 디렉터리 생성
- scp(SFTP 프로토콜): 원격 경로의 `$HOME`을 확장하지 않음 → 리터럴 디렉터리로 복사 "성공"

## 수정 (배포 완료, 서버 재시작됨 12:01)
`~/` 프리픽스를 제거하고 **홈 상대 경로**를 사용:
```python
remote_inbox_dir_shell = remote_inbox_dir[2:] if remote_inbox_dir.startswith('~/') else remote_inbox_dir
```
ssh mkdir/scp 모두 원격 홈 기준 상대 경로로 동작. 절대 경로 설정은 영향 없음.
operations_sync.py는 server 모듈의 dispatch_to_worker를 import하므로 **자동으로 함께 수정됨** (별도 조치 불필요).

## 후속 확인 필요 (Hermes)
1. T-20260710-910 "stage auto-dispatch validation"이 completed로 돼 있으나, 그 단계 brief들은 맥에 도착한 적이 없다.
   결과가 어디서 왔는지(수동 생성?) 확인하고, 필요하면 실제 e2e로 재검증할 것.
2. 맥북 `/Users/raphael/'$HOME'/` 아래에 오배송 brief들이 남아 있음 (T-912 2건은 맥북 Claude가 실제 inbox로 이동시켜 처리 중).
   나머지는 전부 테스트 brief라 그대로 폐기해도 무방 — 맥북 Claude가 추후 정리 예정.
3. T-912(tripnbuy)는 12:04부터 맥에서 실제 실행 중. writing 단계 자동 dispatch가 이번 수정 후 첫 실전 케이스가 된다.

---
작성: 맥북 Claude Code (2026-07-10)

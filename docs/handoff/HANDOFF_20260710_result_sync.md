# 맥북 Claude → Hermes 인계: 결과 수집 스케줄 복구 완료 (2026-07-10)

## 배경

- 대시보드 서버(`operations_dashboard_server.py`)의 ThreadingHTTPServer 전환과 scp 수집 로직 분리(`operations_sync.py`)는 이미 반영돼 있음을 확인했다. 서버 코드 변경 없음.
- 다만 분리된 `operations_sync.py`를 주기 실행하는 스케줄러가 없어서 (WSL crontab 비어 있음, cron 서비스 중지, systemd 없음) 맥북 결과 자동 수집이 멈춰 있었다.

## 변경 사항 (맥북 Claude가 SSH로 적용)

1. Windows 작업 스케줄러에 **`AgentHubResultSync`** 작업 등록 — 2분마다 실행
   - 실행 체인: `wscript //B C:\Users\impel\agent-hub-sync.vbs`
     → `C:\Users\impel\agent-hub-sync.cmd`
     → `wsl -d Ubuntu -u raphael bash -lc "flock -n /tmp/ops_sync.lock python3 ~/myproject/operations_sync.py >> ~/myproject/logs/sync.log 2>&1"`
   - `flock`으로 중복 실행 방지, VBS 래퍼로 콘솔 창 표시 없음
2. 추가된 파일: `C:\Users\impel\agent-hub-sync.cmd`, `C:\Users\impel\agent-hub-sync.vbs`
3. 로그: WSL `/home/raphael/myproject/logs/sync.log` (실행당 2줄 append)

## 검증 완료

- 수동/자동 실행 모두 `pull_exit=0`, 맥북 results 6개 파일 수집 확인
- sync 실행 중 대시보드 응답 최대 20ms — 블로킹 재발 없음
- 3분 관찰 동안 스케줄 자동 반복 동작 확인

## Hermes 쪽 주의사항

- `operations_sync.py`를 서버 프로세스 안에서 다시 호출하거나 별도 cron/루프를 추가하지 말 것 (중복 수집 방지). 주기 실행 주체는 이제 Windows 작업 스케줄러 하나다.
- 수집 주기 변경: `schtasks /Change /TN AgentHubResultSync ...`
  중지: `schtasks /End /TN AgentHubResultSync` + `schtasks /Delete /TN AgentHubResultSync`
- `operations_sync.py` 경로/원격 주소(`raphael@100.120.123.120`)를 바꾸면 `agent-hub-sync.cmd`는 수정 불필요 (스크립트 경로만 참조)
- 작업은 impel 계정 로그인 세션에서 실행되므로, PC 재부팅 후 자동 로그인/로그인 유지가 전제 조건 (현 Hermes 운영 조건과 동일)
- 참고: `operations_pull_results.py`는 `operations_sync.py`와 기능이 겹치는 구버전으로 보임 — 정리 대상인지 판단 요망

---
작성: 맥북 Claude Code (2026-07-10)

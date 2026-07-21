# Remote Worker Setup (MacBook)

목적:
- Windows PC 허브가 생성한 brief JSON을 MacBook 쪽 worker가 받아 처리할 수 있게 준비한다.

## 1. 최소 필요 정보
Hub에서 실제 dispatch를 수행하려면 아래가 필요하다.
- MacBook SSH host
- MacBook SSH user
- MacBook에서 brief를 받을 inbox 디렉터리

이 값은 다음 파일에 넣는다:
- `/home/raphael/myproject/operations/config/workers.json`

## 2. 추천 inbox 디렉터리
- Claude Code Worker: `~/agent-hub/inbox/claude-code`
- OpenClaw Worker: `~/agent-hub/inbox/openclaw`

## 3. 추천 원격 구조
- `~/agent-hub/inbox/claude-code/`
- `~/agent-hub/inbox/openclaw/`
- `~/agent-hub/results/`
- `~/agent-hub/logs/`

## 4. 향후 연결 흐름
1. hub가 brief JSON을 scp로 MacBook inbox에 복사
2. optional dispatch command가 remote wrapper를 실행
3. wrapper가 brief를 읽고 worker 실행
4. 결과를 표준 envelope로 저장
5. hub가 나중에 결과를 회수

## 5. 지금 상태
- hub dispatch 구현 완료
- worker SSH 정보 미입력 상태
- 따라서 현재 dispatch는 `needs_config` / `dispatch_blocked`로 정확히 기록됨

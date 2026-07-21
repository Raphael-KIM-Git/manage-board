# MacBook Tailscale + Worker Checklist

## 1. Tailscale
- [x] Tailscale 설치/로그인 완료로 보임 (Windows host에서 peer 확인)
- [x] tailnet에 MacBook이 보임
- [x] 현재 확인된 MacBook Tailscale 이름: `Raphael의 MacBook Pro`
- [x] 현재 확인된 MacBook Tailscale IP: `100.120.123.120`

## 2. SSH
- [ ] macOS 설정에서 Remote Login(원격 로그인) 활성화
- [ ] MacBook 사용자명 확인
- [ ] 집 PC 또는 외부 노트북에서 `ssh <user>@100.120.123.120` 접속 가능한지 확인
- [ ] 참고: 현재 Windows/WSL 허브에서 `100.120.123.120:22` 접속 테스트 결과 `Connection refused` 이므로 SSH 서비스는 아직 열려 있지 않음

## 3. Worker inbox 준비(권장)
- [ ] `~/agent-hub/inbox/claude-code`
- [ ] `~/agent-hub/inbox/openclaw`
- [ ] `~/agent-hub/results`
- [ ] `~/agent-hub/logs`

## 4. Hermes hub에 전달할 정보
- Claude Code Worker.host
- Claude Code Worker.user
- OpenClaw Worker.host
- OpenClaw Worker.user

## 5. 연결 후 바로 할 일
- [ ] `operations/config/workers.json` 업데이트
- [ ] dashboard에서 Dispatch 버튼 테스트
- [ ] auto-dispatch 테스트
- [ ] remote runner 연결 고도화

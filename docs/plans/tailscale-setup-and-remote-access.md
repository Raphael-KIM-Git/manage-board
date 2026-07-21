# Tailscale Setup and Remote Access Plan

> 목적: 집 Windows PC(WSL Ubuntu)에서 Hermes 운영 허브/대시보드를 계속 돌리고, 외부 노트북 및 MacBook에서 안전하게 접속할 수 있게 한다.

## 1. Recommended Direction

가장 추천하는 방향:
- 집 Windows PC는 항상 켜진 운영 허브로 유지
- WSL Ubuntu에서 Hermes + operations dashboard 실행
- 외부 노트북, MacBook은 Tailscale으로 같은 private network에 연결
- 대시보드는 공개 인터넷이 아니라 Tailscale 내부에서만 접속

핵심 장점:
- 현재 운영 구조를 거의 안 바꿔도 됨
- operations/ 데이터와 dispatch 로직을 그대로 사용 가능
- 공개 포트 개방 없이 외부 접속 가능

---

## 2. Current Status Verified

이 세션에서 확인한 사실:
- WSL Ubuntu 환경에는 아직 `tailscale`, `tailscaled`가 설치되어 있지 않음
- sudo 설치는 가능하지만 비밀번호 입력이 필요해서 자동 완료는 못 함
- 현재 dashboard health는 정상:
  - `http://127.0.0.1:8765/api/health`

---

## 3. Setup on the Home PC (WSL Ubuntu)

### 3.1 Install Tailscale in WSL Ubuntu
아래 명령은 Raphael님이 직접 실행해야 함 (sudo password 필요):

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

설치 확인:
```bash
tailscale version
```

### 3.2 Start/login Tailscale
```bash
sudo tailscaled >/tmp/tailscaled.log 2>&1 &
sudo tailscale up
```

`tailscale up`를 실행하면 브라우저 인증 URL이 나올 수 있음.
그 링크를 열어서 Raphael님 계정으로 로그인/승인.

연결 확인:
```bash
tailscale ip -4
tailscale status
```

### 3.3 Run dashboard for remote access
현재 dashboard는 localhost(127.0.0.1) health 확인만 검증됨.
외부 노트북에서 접근하려면 보통 모든 인터페이스에서 듣게 실행하는 게 안전함.

권장 실행:
```bash
OPS_DASHBOARD_HOST=0.0.0.0 OPS_DASHBOARD_PORT=8765 python3 /home/raphael/myproject/operations_dashboard_server.py
```

이미 Hermes managed background process로 돌리고 싶으면, 현재 세션에서 같은 환경변수로 재기동하면 됨.

### 3.4 Test from another device on Tailscale
외부 노트북에서:
```text
http://<home-pc-tailscale-ip>:8765
```

또는 MagicDNS를 쓴다면:
```text
http://<device-name>:8765
```

---

## 4. Setup on the External Laptop

1. Tailscale 설치
2. 같은 계정으로 로그인
3. home PC가 보이는지 확인
4. 브라우저에서 `http://<home-pc-tailscale-ip>:8765` 접속

권장 확인 순서:
- Tailscale 앱에서 home PC 노드가 online인지 확인
- 브라우저로 dashboard 열기
- 필요하면 SSH/원격 터미널도 연결

---

## 5. Setup on the MacBook

MacBook은 역할이 2개임:
1. 외부에서 dashboard를 보는 client
2. Claude Code / OpenClaw worker host

### 5.1 Basic Tailscale setup on MacBook
- Tailscale 설치
- 같은 계정으로 로그인
- tailnet에 MacBook 추가
- home PC 노드가 보이는지 확인

### 5.2 Recommended worker-related follow-up on MacBook
나중에 dispatch를 실제로 붙이려면 필요:
- MacBook의 SSH host 확인
- MacBook의 SSH user 확인
- ssh 접속 허용/확인
- inbox 디렉터리 생성

권장 디렉터리:
- `~/agent-hub/inbox/claude-code`
- `~/agent-hub/inbox/openclaw`
- `~/agent-hub/results`
- `~/agent-hub/logs`

권장 생성 명령:
```bash
mkdir -p ~/agent-hub/inbox/claude-code ~/agent-hub/inbox/openclaw ~/agent-hub/results ~/agent-hub/logs
```

### 5.3 Update worker config on the hub later
다음 파일에 MacBook SSH 정보 입력 필요:
- `/home/raphael/myproject/operations/config/workers.json`

최소 필요 필드:
- `host`
- `user`
- 필요 시 `port`

---

## 6. Safety / Exposure Notes

중요:
- 현재 dashboard에는 로그인/토큰 보호가 없음
- 따라서 공개 인터넷에 직접 노출하는 건 비추천
- Tailscale 내부에서만 접속하는 구조가 적절

즉:
- Tailscale = 추천
- 포트포워딩으로 인터넷 공개 = 현재 단계에선 비추천

---

## 7. About Running Another Hermes Session in Parallel

가능은 함. 다만 조건이 있음.

안전한 경우:
- 서로 다른 task를 다룸
- 같은 파일을 동시에 수정하지 않음
- 같은 background process를 동시에 재시작하지 않음
- dashboard/operations 문서를 한쪽에서 수정 중이면 다른 쪽은 읽기 위주

주의 필요한 경우:
- 같은 `operations_dashboard_server.py` 파일 동시 수정
- 같은 `operations/config/workers.json` 동시 수정
- 같은 managed background process를 양쪽에서 kill/restart
- 같은 brief/result/verifications 파일을 동시에 patch/write

실전 권장:
- 한 세션은 운영/문서/대시보드 담당
- 다른 세션은 별도 분석/코드작업 담당
- 현재 이 dashboard/dispatch/Tailscale 작업은 한 세션에서 계속 이어가는 편이 안전

---

## 8. Next Best Steps

1. Raphael님이 WSL Ubuntu에서 Tailscale 설치 (`curl ... | sh`)
2. `sudo tailscale up` 인증 완료
3. dashboard를 `OPS_DASHBOARD_HOST=0.0.0.0`로 재실행
4. 외부 노트북에서 접속 테스트
5. MacBook에도 Tailscale 설치
6. MacBook SSH 정보로 `workers.json` 업데이트
7. 실제 dispatch 재검증

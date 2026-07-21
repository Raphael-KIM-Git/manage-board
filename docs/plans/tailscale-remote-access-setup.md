# Tailscale Remote Access Setup

목적:
- 집 Windows PC를 항상 켜 둔 운영 허브로 사용
- 외부 노트북과 MacBook에서 안전하게 접속
- 운영 대시보드와 향후 SSH/worker dispatch를 같은 private network 위에서 운영

## 현재 상태
- Windows 호스트에 Tailscale 설치 완료
- Windows Tailscale 서비스 자동 시작 / Running 확인
- Windows 호스트 Tailscale 로그인 완료
- 현재 Windows host Tailscale 주소 확인됨: `100.113.23.118`
- 현재 Windows host 이름 확인됨: `home-work-rapl`
- 대시보드 서버는 `0.0.0.0:8765` 로 재기동 완료
- 현재 managed process session_id: `proc_684e871ae878`

## Raphael님이 지금 PC에서 해야 할 일
1. Windows에서 아래 로그인 URL 열기
   - `https://login.tailscale.com/a/17d4b8301247e`
2. Raphael님 계정으로 Tailscale 로그인
3. 로그인 후 Windows PC가 tailnet에 붙었는지 확인
4. 가능하면 기기 이름을 알아보기 쉽게 유지
   - 예: `raphael-home-pc`

## 외부 노트북에서 해야 할 일
1. Tailscale 설치
2. 같은 Tailscale 계정으로 로그인
3. 집 PC가 장치 목록에 보이는지 확인
4. 브라우저에서 아래 형태로 접속 테스트
   - `http://<집PC의 tailscale IP>:8765`
   - 또는 MagicDNS 사용 시 `http://<집PC이름>:8765`

## MacBook에서 해야 할 일
1. MacBook은 이미 같은 tailnet에 참가한 것으로 확인됨
   - 이름: `Raphael의 MacBook Pro`
   - IP: `100.120.123.120`
2. 나중에 worker dispatch 용으로 SSH 사용 예정이므로 아래 확인 필요
   - MacBook 사용자 계정명
   - `Remote Login` 활성화
   - `ssh <user>@100.120.123.120` 접속 가능 여부
3. 향후 `operations/config/workers.json` 에 입력할 값 준비
   - Claude Code Worker.host = `100.120.123.120` (반영 완료)
   - Claude Code Worker.user = MacBook 사용자명 (아직 필요)
   - OpenClaw Worker.host = `100.120.123.120` (반영 완료)
   - OpenClaw Worker.user = MacBook 사용자명 (아직 필요)
4. 현재 관측 상태
   - MacBook peer는 online
   - 하지만 `100.120.123.120:22` 는 현재 `Connection refused`
   - 즉 SSH 서비스가 아직 열려 있지 않거나 Remote Login이 꺼져 있음

## 중요한 이유
현재 dispatch가 막히는 유일한 이유는 worker SSH 정보 부재다.
Tailscale이 붙으면 MacBook을 공용 인터넷 노출 없이 안정적으로 주소 지정할 수 있다.

## 대시보드 상태
- URL (local test): `http://127.0.0.1:8765`
- 원격 접속용: `http://<집PC tailscale 주소>:8765`
- 현재는 인증 없는 내부 서비스이므로 Tailscale 내부에서만 사용 권장

## 다음 단계
1. Windows host Tailscale 로그인 완료
2. 노트북에서 대시보드 접속 확인
3. MacBook Tailscale + SSH 확인
4. `workers.json` 에 MacBook host/user 입력
5. 첫 실제 dispatch 검증

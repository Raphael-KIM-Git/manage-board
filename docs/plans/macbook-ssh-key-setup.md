# MacBook SSH Key Setup for Hermes Hub

목적:
- WSL Hermes 허브가 MacBook (`raphael@100.120.123.120`) 에 비밀번호 없이 SSH 접속할 수 있게 설정
- 이후 dashboard dispatch / auto-dispatch 가 실제로 작동하도록 만들기

## 현재 상태
- Tailscale 연결 완료
- MacBook SSH 포트(22) 열림 및 접속 시도 가능
- `workers.json` 반영 완료:
  - host = `100.120.123.120`
  - user = `raphael`
- 현재 blocker:
  - Hermes 허브의 공개키가 MacBook `authorized_keys`에 아직 없음

## Hermes 허브 공개키
아래 공개키를 MacBook의 `~/.ssh/authorized_keys` 에 추가하면 됨.

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKT6L7lWO/TQ4HmMl5At9NzD52HFJEbxTrpfCQtDaTvu raphael-hermes-hub
```

## MacBook에서 해야 할 일
터미널에서 아래 순서 실행:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKT6L7lWO/TQ4HmMl5At9NzD52HFJEbxTrpfCQtDaTvu raphael-hermes-hub' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

## 확인 명령
MacBook에서 원격 로그인 설정이 켜져 있다면, 허브에서 아래 명령이 성공해야 함:

```bash
ssh raphael@100.120.123.120 'whoami && uname -a'
```

성공 시 기대값:
- `whoami` -> `raphael`
- 이어서 macOS 커널 정보 출력

## 이후 바로 할 일
키 등록 완료 후 Raphael님이 알려주면, 허브에서 다음을 진행:
1. SSH 접속 재검증
2. Claude Code Worker dispatch 재검증
3. MacBook inbox 디렉터리 생성
4. OpenClaw Worker 동일 경로 검증

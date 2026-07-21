# Transport Options Evaluation

> 목적: Windows PC 허브(Hermes)와 MacBook worker(OpenClaw, Claude Code) 사이에서 작업을 주고받는 방식을 비교하고, Raphael님의 현재 환경에 맞는 우선순위를 정한다.

## 1. Requirements

필요한 기능:
- hub에서 MacBook worker로 작업 전달 가능
- worker 결과를 다시 hub로 회수 가능
- 가능한 한 단순하고 디버깅 가능해야 함
- 항상 켜진 Windows PC 허브에 잘 맞아야 함
- 초기에는 사람 개입이 조금 있어도 괜찮지만, 나중에 자동화로 발전 가능해야 함

---

## 2. Candidate Options

### Option A — SSH-based remote execution

How it works:
- Windows PC의 WSL Ubuntu에서 MacBook으로 SSH 접속
- Claude Code/OpenClaw wrapper 명령 실행
- 결과를 파일 또는 stdout으로 회수

Pros:
- 가장 직관적
- Linux/WSL와 잘 맞음
- 디버깅 쉬움
- 스크립트화 쉬움
- 나중에 cron과 연결 쉬움

Cons:
- MacBook이 깨어 있어야 함
- SSH key / 접근 경로 관리 필요
- interactive CLI는 wrapper 설계가 필요함

Best for:
- 초기 실전 운영
- semi-automation
- reproducible scripts

Verdict:
가장 추천되는 1순위.

### Option B — Watched-folder job bus

How it works:
- hub가 shared/synced folder에 brief 파일 생성
- MacBook 측 watcher가 파일 감지 후 worker 실행
- 결과 envelope를 다른 폴더에 저장
- hub가 그 결과를 읽음

Pros:
- 단순한 구조
- 결과가 파일로 남아 audit에 좋음
- OpenClaw/Claude Code wrapper와 결합 쉬움

Cons:
- shared folder / sync 경로가 필요함
- latency가 있을 수 있음
- 파일 충돌/중복 처리 룰 필요

Best for:
- human-in-the-loop + light automation
- 보고서 중심 흐름

Verdict:
2순위 추천. SSH와 함께 쓰면 좋음.

### Option C — Discord / messaging queue style

How it works:
- hub가 Discord나 메시징 채널로 작업 전달
- worker가 해당 채널/봇을 통해 결과 반환

Pros:
- 원격 접근 편함
- 사람도 흐름을 보기 쉬움
- 알림에 강함

Cons:
- structured artifact handling이 약함
- 장문 결과/파일 처리 규칙 필요
- worker execution transport로는 덜 안정적

Best for:
- notifications
- approvals
- summaries
- lightweight coordination

Verdict:
메인 transport보다는 보조 알림 채널로 추천.

### Option D — OpenClaw/native gateway-centric routing

How it works:
- OpenClaw 쪽 gateway나 기존 연결 구조를 활용해 job routing

Pros:
- OpenClaw와 자연스럽게 연결될 가능성
- 기존 gateway surface 재활용 가능

Cons:
- Claude Code까지 같은 모델로 묶기 어려움
- mixed-stack 전체 transport로는 덜 통일적
- hub의 단일 제어 모델이 약해질 수 있음

Best for:
- OpenClaw-only 최적화 상황

Verdict:
현재 Raphael님 mixed-stack 기준으로는 1차 메인 transport로 비추천.

---

## 3. Recommended Path

### Phase 1
Primary transport:
- SSH-based remote execution

Secondary companion pattern:
- watched-folder/job-artifact directory

Notification layer:
- Discord summaries / alerts

### Why this combination
- SSH가 실행 제어를 단순하게 해줌
- watched-folder 방식이 결과 보존과 audit에 좋음
- Discord는 사람에게 보이기 좋은 보고 채널 역할에 적합함

---

## 4. Recommendation Summary

Recommended now:
1. SSH for dispatch and control
2. files/folders for briefs and result envelopes
3. Discord for notifications and summaries

Not recommended as the first main transport:
- Paperclip-native control plane
- OpenClaw-only routing model
- messaging-only orchestration

---

## 5. Next Implementation Artifacts

To implement this, create next:
- worker wrapper spec for Claude Code
- worker wrapper spec for OpenClaw
- directory conventions for briefs/results/verifications
- naming convention for task IDs and result files

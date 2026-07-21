# Agent Stage 중앙 Orb 시안 검토 요청

## 시안 파일

`/home/raphael/myproject/docs/design/agent-stage-central-orb-concept.png`

원본 생성 이미지:
`/home/raphael/.hermes/cache/images/openai_codex_gpt-image-2-medium_20260711_085301_426fa672.png`

## 요청 방향

Dashboard의 agent stage를 기존 가로형 4단계 카드/트랙에서 중앙 진행 stage 중심의 구조로 변경한다.

- 현재 진행 중인 stage를 화면 중앙의 큰 원형 orb로 표시
- Research / Writing / Verification Support / Finalization 4개 영역이 상하좌우로 중앙을 감쌈
- 중앙 원형은 주변 영역의 안쪽 경계 위로 겹쳐 올라옴
- 중앙 원형에 현재 단계, 진행률, 상태를 표시
- 주변 stage에는 해당 단계의 agent, 완료/진행/대기/차단 상태, 핵심 결과를 표시
- 연결선은 각 주변 stage에서 중앙 진행 stage로 모임
- 아래에는 activity timeline과 결과물 영역을 보조 정보로 배치

## PM 검토 포인트

- 현재 업무에서 가장 중요한 단계가 첫눈에 보이는가?
- stage 전환과 다음 action을 쉽게 판단할 수 있는가?
- 주변 4개 영역이 중앙 진행 상태를 보조하고 있는가?
- research/writing/verification/finalization이 고정 pipeline이 아닌 PM 선택 pipeline에도 대응 가능한가?

## Designer 검토 포인트

- 중앙 orb가 실제로 주변 4개 stage보다 시각적 우선순위를 갖는가?
- 모바일/좁은 화면에서도 중앙 구조가 무너지지 않는가?
- 상태 색상만으로 의미를 전달하지 않고 label/icon/text를 함께 제공하는가?
- agent 정보가 너무 무거운 카드로 보이지 않고 stage 흐름을 방해하지 않는가?

## 현재 전송 상태

Hermes status 확인 결과 Discord가 현재 `not configured`라서 Discord 채널로 직접 업로드하지 못했다. Discord 연동이 활성화되면 이 시안 파일을 `HermesDesigner` 또는 `HermesPM` 검토 채널에 공유해야 한다.

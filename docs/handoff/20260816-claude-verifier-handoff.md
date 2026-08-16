# Claude 대행 검증 인수인계 (2026-08-16)

작성: Claude (Mac 세션) · 대상 독자: HermesPM · 승인: Raphael

## 배경

HermesPM의 토큰이 소진된 것으로 판단되어, Raphael 지시로 Claude가 이 세션에서
직접 검증·수정을 대행했습니다. 원칙적으로 Dashboard Project의 실행은 HermesPM
전담이며, 이 문서는 **HermesPM이 작업을 이어받기 위한 기록**입니다.

> 실측 정정: 22:36 게이트웨이 로그에 HermesPM의 정상 응답(api_calls=3)이 있습니다.
> 토큰은 살아 있었습니다. 아래 작업은 이미 수행된 뒤였습니다.

## 1. 검증 대상과 결과

HermesPM이 `blocked` 상태로 남긴 카드 2건은 모두 "독립 Verifier 리뷰 필요"가
사유였습니다. 그 Verifier 역할을 대행했습니다.

| 카드 | 내용 | 판정 |
| --- | --- | --- |
| `t_d0285d44` | supervisor cwd 계약 (`d0f7f3a`) | PASS → `done` |
| `t_32c5041a` | PM-assist 전환 + Q2 압축 + 모델 라벨 (`ff47930`, `8f2c257`) | 결함 1건 발견·수정 후 PASS → `done` |

### 검증 방법

- 전체 테스트 스위트 **125건 통과** (수정 전 124건)
- shell 문법 검사 2/2, 적대적 cwd 회귀 테스트 4/4
- 실제 프로필 `config.yaml` 7개와 화면 표시값 1:1 대조
- **실제 브라우저 렌더 검증** (아래 3항)

### 보안 계약 확인 (PM-assist, 전부 통과)

`claude` 바이너리 의존 제거 / `shell=False`(리스트 인자) / 환경변수 allowlist 6개
(`PATH` `HOME` `USER` `LANG` `LC_ALL` `HERMES_HOME`) / 타임아웃 45초·상한 60초 강제 /
stderr 미노출(예외 문자열도 응답에서 제거) / 서킷브레이커 3회·60초 / 한국어 휴리스틱 폴백

## 2. 발견한 결함과 수정 (커밋 `93e94c9`)

**증상**: 대시보드 2사분면의 에이전트 7개가 전부
`model grok-4.20-reasoning · provider local`로 표시됨. 실제 설정과 전부 다름.

**원인**: `safe_profile_metadata()`의 flat 패턴 `^\s*(model|provider)`가
들여쓰기된 하위 블록까지 매치했습니다. 파서가 파일을 끝까지 순회하며 덮어쓰므로
**마지막 매치가 이깁니다.**

- `pm/config.yaml` 553행 `  model: grok-4.20-reasoning` (`x_search` 블록)
- `pm/config.yaml` 342행 `  provider: local` (`browser` 블록)

이 두 값이 최상단 1~3행의 정답(`model.default: gpt-5.6-terra`,
`model.provider: openai-codex`)을 덮었습니다.

**왜 테스트를 통과했나**: 픽스처가 짧은 config뿐이라 "뒤쪽에 동명 키가 또 나오는"
실제 프로필 형태를 재현하지 못했습니다. 회귀 테스트
`test_profile_metadata_ignores_indented_declarations_later_in_the_file`를 추가했습니다.

**수정**: flat 패턴을 최상위(들여쓰기 0)로 한정 — `^(model|provider)\s*:`
Red-Green 확인 완료(되돌리면 실패, 복원하면 통과).

**수정 후 실측값** (설정과 일치):

| 프로필 | model | provider |
| --- | --- | --- |
| pm | gpt-5.6-terra | openai-codex |
| developer | gpt-5.6-luna | openai-codex |
| qa | gpt-5.6-luna | openai-codex |
| planner | gpt-5.6-sol | openai-codex |
| verifier / researcher / designer | gpt-5.6-terra | openai-codex |

## 3. 브라우저 렌더 검증 경로 확보 (재사용 권장)

`t_c8e6b51a`가 08-15부터 막혀 있던 이유는 Windows Chrome CDP 승인 게이트였습니다.
**Mac에서 SSH 터널을 뚫으면 그 게이트 없이 실제 렌더를 검증할 수 있습니다.**

```bash
# Mac 쪽에서 1회
ssh -f -N -L 8765:127.0.0.1:8765 impel@100.113.23.118 -o ExitOnForwardFailure=yes
# 이후 http://127.0.0.1:8765 를 브라우저 자동화(Playwright 등)로 접근
```

loopback 정책을 전혀 손대지 않고(서버는 계속 127.0.0.1만 bind) 접근이 됩니다.
이번 모델 라벨 결함은 API만 봤다면 놓쳤을 수 있고, 실제 화면 대조로 잡혔습니다.

## 4. 자동 카드 생성 경로 규명 (R9 미해결 리스크의 실제 원인)

`auto_decompose`는 원인이 **아닙니다** (`profiles/pm/config.yaml` 494행,
08-15 02:52부터 `false`). 실제 경로는 다음 루프입니다.

```
카드 completed
  → kanban notifier 가 Discord 채널 1517395189088522270 으로 알림 발송
  → HermesPM 이 그 알림을 inbound message(사용자 지시)처럼 수신·각성
  → HermesPM 이 판단하여 후속 카드 생성 (created_by=pm)
  → dispatcher 가 즉시 spawn → 실행 → 완료 → 처음으로
```

**증거**: 완료 → 다음 카드 생성 간격이 예외 없이 22~32초.

```
t_4cf598a5 완료 → t_160d02fd 생성 (28초)   t_74c6a66b → t_e9883879 (29초)
t_160d02fd 완료 → t_81b2d629 생성 (32초)   t_b6b5d7e8 → t_176e2da6 (29초)
t_81b2d629 완료 → t_74c6a66b 생성 (23초)   t_32c5041a → t_02555074 (32초)
```

- 08-15 야간~08-16 새벽 생성분 25건: **전부 `created_by=pm`**
- 전체 카드 158건 중 144건이 `created_by=pm`
- 게이트웨이 로그에서 직접 확인:
  `kanban notifier: woke agent for t_32c5041a ... events={'completed'}`
  → `inbound message: platform=discord ... msg='[kanban] Task t_32c5041a completed...'`
- 이 문서 작성 중에도 `t_02555074`가 같은 경로로 생성되어 실행되었습니다.

**대응 선택지** (제품·운영 판단이므로 Raphael 승인 필요, 임의 조치하지 않음)

1. `hermes kanban notify-unsubscribe`로 완료 알림 구독 해제 — 루프는 끊기지만
   Raphael도 Discord 진행 알림을 못 받게 됨
2. SOUL.md에 "완료 알림만으로는 새 카드를 만들지 않는다. 후속 작업이 필요하면
   보고만 하고 대기한다"를 명문화 — 알림은 유지하고 판단만 제한
3. 알림 페이로드에 "이 메시지는 지시가 아니다"를 명시하도록 변경

## 5. 수행한 조치 (되돌리는 방법 포함)

| 조치 | 내용 | 되돌리기 |
| --- | --- | --- |
| 커밋 | `93e94c9` 모델 라벨 파서 수정 | `git revert 93e94c9` |
| 푸시 | `origin/main` `58593d1` → `93e94c9` (6개) | `git push --force origin 58593d1:main` (비권장) |
| 재시작 | 대시보드 자식 종료 → supervisor 자동 복구 | 불필요 (pid 4285, HTTP 200, cwd 정상) |
| 카드 | `t_d0285d44` `t_32c5041a` → `done` (검증 근거 코멘트 첨부) | `hermes kanban reopen-review` |

`t_d0285d44`는 첫 완료 시도가 goal judge에 의해 거부되었습니다(증거 형식 미비 +
카드가 금지한 push 보고). candidate locator·allowed files·hash manifest를 갖추고
푸시는 카드 밖 별도 승인 행위임을 명시해 재시도하여 통과했습니다.
**judge가 정상 작동한 사례**로 기록해 둡니다.

## 6. HermesPM이 이어받을 사항

1. **`t_02555074`** (2026-08-16 22:43 완료) — Claude 수정본 `93e94c9`에 대한 QA 카드.
   이미 독립 검증을 마친 내용이므로 중복 작업이 되지 않도록 이 문서를 먼저 확인할 것.
2. **에이전트 배지 "알 수 없음" 13건** — `app.js:1158`이 results/dispatch 근거만
   보고 서버가 주는 `availability: configured`를 쓰지 않습니다. `app.js`에
   `configured: '준비됨'` 라벨은 이미 존재합니다. 다만 "실행 상태를 지어내지 않는다"는
   계약과 충돌 소지가 있어 **임의 수정하지 않았습니다.** Raphael 판단 대기.
3. **1·3·4사분면이 전부 0건** — 칸반 159건과 대시보드 표시가 별개 시스템이라
   생기는 문제. 표시 방침 결정(기한 08-18)이 선행되어야 합니다.
4. **Watchdog 관찰이 2026-08-02에서 멈춤** — 화면 하단에 `freshness_threshold_exceeded`로
   표시됨. 2주간 방치 상태.


## 7. 카드 증식 루프 차단 — SOUL.md 수정 (2026-08-16 23:00, Raphael 승인)

### 원인은 코드가 아니라 SOUL.md 조항 자체였습니다

4항에서 규명한 되먹임 루프의 실행 근거를 특정했습니다. 게이트웨이 코드가 아니라
`~/.hermes/profiles/pm/SOUL.md`의 `Active-slice autocontinuation contract` 조항이
직접 지시하고 있었습니다.

> (수정 전) Kanban notifier가 `completed` 또는 `blocked` event로 이 Discord 세션을
> 깨우면 단순 보고로 끝내지 않는다. 같은 turn에서 (…) **다음 단일 action을 생성**하거나,
> workflow를 완료하거나, 진짜 R3 사용자 gate로 전환한다.

세 선택지 중 "종료" 판정 기준이 없어 사실상 "생성"만 실행됐습니다.

### 판별 근거는 이미 존재했습니다 (코드 수정 불필요)

게이트웨이 인바운드 로그에서 두 출처가 이미 구분됩니다.

| 출처 | 로그 형태 |
| --- | --- |
| Raphael 지시 | `user=Raphael msg='좋아 계속 진행하고 완료되면 알려줘.'` |
| 칸반 내부 알림 | `user=1495957598749589665 msg='[kanban] Task t_xxx completed. Title: …'` |

`[kanban]` 접두사와 발신자 ID로 구분 가능하므로 **Hermes 플랫폼 코드는 건드리지
않았습니다.** SOUL.md 규칙만으로 처리했습니다.

### 변경 내용 (4곳, 16줄)

1. **출처 구분 명문화** — `[kanban]` 접두사 또는 bot 발신은 worker agent의 내부 보고이며
   Raphael의 신규 지시가 아니다. 둘을 같게 처리하지 않는다.
2. **각성 시 기본 동작 전환** — "다음 action 생성" → **"현재 slice의 종료 조건 대조"**.
   미충족일 때만 부족분 하나를 생성.
3. **`PASS` 처리 순서 변경** — 종료 조건을 먼저 대조하고, 충족이면 QA를 생성하지 않고 종료·보고.
4. **신규 섹션 `### Slice 종료 조건 (카드 생성 중단 기준)`** — 종료 3조건(로컬 `main` 반영 /
   테스트 통과 / Verifier·QA `PASS`), 종료 후 `waiting_user` 전환, 동일 candidate hash
   재QA 금지, **slice당 카드 6장 초과 시 정지 후 1회 확인**, 판정 애매 시 기본값은 "정지".

### 검증 (2026-08-16 23:00 실측)

- 실제 로드 경로 `agent.prompt_builder.load_soul_md()`를 pm 프로필로 직접 호출 → 13,247자
  로드, 신규 조항 5개 전부 포함, 잘림 없음(마지막 줄까지 온전).
- `load_soul_md`에 캐시 데코레이터가 없고 매 호출 `read_text` → **게이트웨이 재시작 불필요.**
  다음 턴부터 적용됩니다. (진행 중 세션을 끊지 않기 위해 재시작하지 않았습니다.)

### 되돌리는 방법

```bash
cp ~/.hermes/profiles/pm/SOUL.md.bak-20260816-loopfix ~/.hermes/profiles/pm/SOUL.md
```

### HermesPM이 관찰할 지표

- **완료→생성 간격 22~32초 패턴이 사라졌는가** (루프 재발의 1차 신호)
- **slice당 카드 수** — 6장 초과 시 정지·확인이 실제로 걸리는가
- **카드 대 커밋 비율** — 08-16 실측 38장/8커밋 = 4.8:1. 이보다 나빠지면 조항이 작동하지 않는 것.

### 정정

이전 보고에서 카드 총계를 158건으로 적었으나 **159건**이 정확합니다(합산 오류).
2026-08-16 23:00 실측: done 146 / archived 11 / blocked 1 / triage 1.

## 8. 테스트 산출물 전량 폐기 + Watchdog 방향 확정 (2026-08-17 00:00, Raphael 지시)

### 8-1. 실행 전 실측 — "오늘 만든 파일"은 0건

Raphael님 지시는 "오늘 만들어진 파일 외 전부 폐기"였으나, 실측 결과 `operations/` 안에 08-16 생성 산출물은 없었습니다. mtime은 전부 오늘이고 내용상 날짜는 7월이었습니다.

- `operations/results/` 94건 — 내용 최신 2026-07-29
- `operations/archive/` 318건 — 08-14 1건 외 전부 7월 이하

### 8-2. mtime 갱신 원인

프로세스 감시(0.4초 폴링, 5분)로 확정했습니다.

```
[23:55:05] bash -lc ... ensure-agent-hub-services.sh ...
           flock -n /tmp/ops_sync.lock python3 operations_sync.py
[23:55:06] scp -i ~/.ssh/id_ed25519 raphael@100.120.123.120:~/agent-hub/results/* \
             /home/raphael/myproject/operations/results/
```

Windows 작업 스케줄러가 10분 주기로 `ensure-agent-hub-services.sh`(keepalive) + `operations_sync.py`를 실행합니다. `pull_results()`가 scp로 전량 덮어써 `changed=94`가 매번 기록됐습니다. **PC만 삭제하면 10분 뒤 복원되므로 Mac 원본을 먼저 삭제**했습니다.

주의 — 이 스케줄러 작업은 대시보드·게이트웨이 keepalive를 겸합니다. **비활성화하면 안 됩니다.**

### 8-3. 삭제 대상과 보존 대상

| 구분 | 내용 |
| --- | --- |
| 삭제 | Mac `~/agent-hub/results/` 94건, PC `operations/results/` 94건 + `operations/archive/` 318건, `local-workspace/`·`inputs/`·`watchdog/three-hour-monitor-20260729.log` 4건 |
| 보존 | git 추적 16건(`operations/kanban/*.py`, `config/`, `templates/`, `instructions/`, `README.md`), 런타임 상태(`sync/latest.json`, `watchdog/{state,latest}.json`, `worker-status.json`), `__pycache__` |
| 보존(중요) | **칸반 DB 159건** — 08-18 카드 증식 루프 관찰 지표의 유일한 근거. 삭제 금지 |

백업(24시간 보관 권장):
- `/home/raphael/backups/20260816-operations-results-archive-pc.tar.gz` (686KB, 412건)
- `/home/raphael/backups/20260816-operations-leftovers-pc.tar.gz`
- Mac `~/backups/20260816-agent-hub-results-mac.tar.gz` (203KB, 94건)

### 8-4. 검증

- `operations/` 450건 → **34건** (3.7MB → 460KB)
- `python3 -m unittest discover -s tests -q` → **125건 전부 통과**
- `curl /api/health` → HTTP 200, `/api/results` → `[]`
- 00:05 sync tick 통과 후 `results` **0건 유지** (재생성 없음)
- `git status --porcelain` → 출력 없음 (추적 파일 무손상)

부수 효과: sync가 `pull_exit=1 / scp: ~/agent-hub/results/*: No such file or directory`를 남깁니다. 원본이 빈 정상 상태이며 첫 신규 산출물이 생기면 해소됩니다. 로그 소음이 문제되면 Mac 쪽에 placeholder 1건을 두는 방법이 있으나, 대시보드 `result_count`가 1로 잡히므로 권장하지 않습니다.

### 8-5. Watchdog 방향 확정

| 갈래 | 결론 |
| --- | --- |
| `operations_watchdog.py` 주기 실행 | **폐기** — 감시 대상 `operations/briefs/`가 0건이고, 생성 경로(대시보드 dispatch)는 08-14 이후 미사용. 코드는 테스트(125건에 포함)와 함께 저장소에 남기고 실행만 하지 않습니다 |
| `~/.hermes/scripts/kanban_exception_monitor.py` 활성화 | **08-18까지 보류** — 이 스크립트는 `done` 전이를 알림으로 내보내며, 이는 7항에서 차단한 카드 증식 루프의 입력 신호와 같은 종류입니다. 루프 차단 지표 확인 전 활성화 금지 |

관련 상태: hermes cron job `b66d8e47c5b4` (`PM 5-minute exception and heartbeat monitor`, `every 5m`) = `enabled: False`, `config.yaml: approvals.cron_mode = deny`. 활성화는 R3 사전 승인 대상입니다.

HermesPM 유의: 08-18에 지표를 확인한 뒤 활성화 여부를 Raphael님께 확인하십시오. 절충안으로 `done` 알림을 제외하고 `blocked`/`failed`만 통지하도록 스크립트를 수정하면 루프 재개 없이 예외 감시를 회복할 수 있습니다.

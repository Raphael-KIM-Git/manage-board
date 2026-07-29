# Agent Hub Dashboard 진행 가시화 PRD

- 문서 상태: 개발·검증 handoff용 v1
- 제품 범위: Agent Hub Dashboard-only v1
- 기준 저장소: `/home/raphael/myproject`
- 대표 사례: `T-20260729-001` 삼성펀드 홈페이지 운영 헬스체크 및 UI/UX 개선안 도출
- 핵심 원칙: **전송, 실행, 결과 도착, 검증 완료를 서로 다른 사실로 표시한다.**

## 기획 요약

첫 화면에서 사용자가 “지금 어느 단계인가, 누가 결과를 냈는가, 무엇이 아직 확인되지 않았는가, PM이 다음에 무엇을 해야 하는가”를 10초 안에 판단할 수 있도록 진행 정보 구조를 보강한다. raw task·dispatch·result·verification 파일을 canonical source로 유지하고, 읽기 전용 `dashboard_projection`만 additive하게 확장한다.

v1 권고안은 2개 개발 slice다.

1. **Slice A — 기존 API만으로 안전한 표시 개선:** 단계 상태, 에이전트별 전송 상태, 도착한 결과 파일, 검증 부재, 다음 PM 조치를 첫 화면 카드와 상세 화면에 분리 표시한다.
2. **Slice B — 최소 projection 확장:** 에이전트별 결과 도착과 산출물·검증 성숙도를 서버에서 보수적으로 정규화해 UI의 파일명 추론과 중복 계산을 제거한다.

---

## 1. 문제 / 목표 / 비목표

### 1.1 문제

현재 Dashboard는 진행 요약, stage timeline, dispatch 문자열, worker result 파일을 제공한다. 그러나 정보가 서로 다른 위치와 의미 체계로 표시되어 다음 오판 위험이 있다.

- `dispatched`가 “전송 성공”인지 “에이전트 실행 완료”인지 바로 구분하기 어렵다.
- 결과 파일이 있어도 어떤 에이전트의 결과가 도착했는지, 다른 에이전트는 아직 대기인지 첫 화면에서 알기 어렵다.
- `task.status=dispatched`와 `stages[].status`가 서로 다른 수준의 상태인데 하나의 진행 문구처럼 읽힐 수 있다.
- `.md`와 `.json` sidecar가 동일 실행의 한 결과 묶음인지, 서로 다른 산출물인지 구분되지 않는다.
- 검색 스니펫 기반 조사와 직접 HTTP/원문 확인이 같은 “결과 도착”으로 보일 수 있다.
- 검증 파일이 없는데도 결과가 도착했다는 이유만으로 “검토 가능” 또는 “완료”로 오해할 수 있다.
- 차단·미확인·근거 한계와 PM 다음 조치가 첫 화면 카드에 충분히 드러나지 않는다.

### 1.2 목표

1. 첫 화면에서 현재 단계, 단계별 상태, 에이전트별 전송/결과 상태, 산출물·검증 성숙도, 근거 한계, 다음 PM 조치를 한 카드 안에서 우선순위대로 파악하게 한다.
2. task detail에서 표시 상태마다 raw source, 확인된 사실, 미확인 한계, 다음 조치를 추적할 수 있게 한다.
3. 전송 성공을 실행 성공이나 결과 완료로 승격하지 않는다.
4. 일부 결과 도착을 단계 또는 전체 업무 완료로 승격하지 않는다.
5. 검색 스니펫·간접 정황을 직접 검증 완료로 표현하지 않는다.
6. projection은 read-only/additive로 유지하고 기존 raw write 경로를 바꾸지 않는다.

### 1.3 비목표

- Discord를 운영 권한 또는 보조 승인 채널로 추가
- 외부 사이트 수정, 콘텐츠 제작, 배포
- 운영 write API 신규 설계 또는 기존 gate/live-note/final-review write 계약 변경
- raw task·dispatch·result persistence schema 대개편
- 자유 텍스트·live note에서 실행, 완료, 승인 상태 추론
- 실제 실행 로그가 없는데 실행 시작·종료 시각 생성
- 에이전트 성능 점수화 또는 자동 PM 승인
- result 본문을 LLM으로 자동 판독해 검증 등급을 결정

---

## 2. 사용자 의사결정과 성공 기준

### 2.1 핵심 사용자

- 1차 사용자: Raphael — 여러 에이전트 작업의 실제 진행과 다음 개입 시점을 판단
- 2차 사용자: HermesPM — 결과 도착, 검증 필요, 차단 해소, 다음 단계 진행 여부 판단
- 실행 사용자: developer·reviewer — 상태 계약에 맞춰 구현하고 오표시를 검증

### 2.2 첫 화면에서 답해야 할 질문

우선순위 순서로 다음 질문에 답해야 한다.

1. **지금 어디인가?** 현재 단계와 전체 단계 분포는 무엇인가?
2. **누가 무엇을 했는가?** 각 에이전트는 미전송, 전송 확인, 결과 도착, 실패/차단 중 무엇인가?
3. **무엇을 믿을 수 있는가?** 결과는 없음, 일부 도착, 검토 가능, 검증 완료, 모호함 중 무엇인가?
4. **무엇이 부족한가?** 미도착 결과, 미실행 검증, 상충 근거, 직접 실측 부재가 무엇인가?
5. **다음에 무엇을 해야 하는가?** PM의 단일 우선 조치는 무엇인가?

### 2.3 대표 사용자 Job Story

- 여러 에이전트에 조사를 보낸 뒤 Dashboard를 열었을 때, 나는 전송 여부와 실제 결과 도착 여부를 분리해서 보고 싶다. 그래야 아직 기다릴지 다음 단계로 진행할지 판단할 수 있다.
- 결과 파일 일부가 도착했을 때, 나는 완료된 에이전트와 미도착 에이전트를 보고 싶다. 그래야 일부 결과를 전체 완료로 오판하지 않는다.
- 검증 전 조사 결과를 볼 때, 나는 직접 확인·간접 정황·미검증 한계를 보고 싶다. 그래야 보고서의 단정을 통제할 수 있다.
- 작업이 막혔을 때, 나는 차단 근거와 PM의 다음 한 가지 조치를 보고 싶다. 그래야 상세 화면을 헤매지 않고 개입할 수 있다.

### 2.4 성공 기준

#### 정량 기준

- 대표 fixture 5종에서 첫 화면만 보고 현재 단계, 결과 도착 에이전트, 검증 여부, PM 다음 조치를 테스트 참여자의 90% 이상이 정확히 식별한다.
- `dispatch_confirmed`만 존재하는 fixture가 `result_received`, 단계 `completed`, 검증 `completed`로 표시되는 오탐 0건.
- 일부 에이전트 결과만 존재하는 fixture가 전체 단계 완료로 표시되는 오탐 0건.
- unknown/missing/null raw 값이 긍정 상태로 승격되는 오탐 0건.
- 기존 Dashboard API·projection·static contract 회귀 테스트 100% 통과.

#### 정성 기준

- 모든 긍정 상태에 raw 근거 경로가 정의되어 있다.
- 근거가 부족하면 모호함/확인 불가로 내려간다.
- 첫 화면은 요약과 다음 조치에 집중하고, raw 경로·파일·시간·상세 한계는 task detail에서 확인한다.
- 색상만으로 상태를 구분하지 않고 텍스트·아이콘을 함께 사용한다.

---

## 3. 현행 데이터·표시 갭

### 3.1 현재 API에서 확인된 데이터

`operations_dashboard_server.py::build_task_view()`는 다음을 제공한다.

- `status`
- `stages`
- `pipeline.current_stage`, `completed_stages`, `stage_count`, `status_counts`
- `dispatches`: worker별 최신 dispatch raw status
- `result_files`: task ID prefix가 일치하는 결과 파일 목록
- `verification_files`
- `pm_live_notes`
- `pm_final_review`
- `dashboard_projection` schema v1

현재 projection은 다음을 제공한다.

- `work_group`, `pipeline_shape`, `decision_queue_item`
- `artifact_summary`, `verification_summary`
- `authority_summary`, `audit_rows`, `data_quality`

### 3.2 현재 UI 표시

`operations_dashboard/app.js`는 다음을 표시한다.

- 카드: 업무 상태, 단계 진행 수, 파이프라인, 산출물 요약, 신뢰 요약, 권한 상태
- 확장 영역: stage chips, assigned workers, 최신 결과/검증 파일, dispatch 문자열, 에이전트별 결과 파일
- 상세: Outcome, Stage timeline, live note, Artifact Review, Authority/Audit

### 3.3 갭 분석

| 갭 | 현재 동작 | 사용자 위험 | 요구 방향 |
|---|---|---|---|
| task와 stage 상태 혼합 | task `dispatched`, stage `writing=in_progress`를 별도 위치에 표시 | 업무가 단순 전송 상태인지 실제 작성 중인지 혼동 | 첫 화면 주상태는 stage 기반, task raw status는 보조 근거로 표시 |
| dispatch 의미 과대 해석 | `worker=dispatched` 문자열 | 실행 또는 결과 완료처럼 읽힘 | “전송 확인 · 결과 대기”로 명시 |
| 결과와 에이전트 연결 취약 | 파일명 `__worker` 파싱 | 비표준 이름·sidecar에서 누락/중복 | Slice A는 보수적 파싱+모호함, Slice B는 projection 정규화 |
| 결과 묶음 중복 | `.md`와 `.json`을 각각 artifact로 계산 | 실제보다 산출물이 많아 보이고 `ambiguous` 발생 | 에이전트 실행 단위 result bundle 정의 |
| 일부/전체 도착 미구분 | result 파일 유무 중심 | 일부 도착을 단계 완료로 오판 | 기대 에이전트 대비 `received/expected` 표시 |
| 검증 성숙도 부족 | verification 파일 유무만 `not_run/available_unstructured` | 검증 완료와 파일 존재 혼동 | 검토 가능과 검증 완료 분리, 완료는 명시적 verdict/binding 필요 |
| 품질 근거 부족 | `data_quality`는 schema 품질 중심 | 조사 방법의 한계를 파악하기 어려움 | 구조화 근거가 없으면 “품질 미분류/직접 검증 확인 불가” |
| PM 다음 조치 부재 | decision queue는 hold/final/reviewable 중심 | 진행 중 미도착·검증 대기 상황에서 무엇을 할지 불명확 | 모든 active task에 보수적 next action 계산 |
| live note 오해 가능 | 상세에서 “지시 대기” | 지시가 실행 또는 승인되었다고 오해 | “비결정 맥락 · 반영 여부 미확인” 유지 |

### 3.4 대표 사례의 현재 raw 사실

이 문서 작성 시점의 `T-20260729-001` raw/API 사실은 다음과 같다.

- task raw status: `dispatched`
- stage: `research=completed`, `writing=in_progress`, `verification=planned`, `final_write=skipped`
- pipeline: current `writing`, 완료 1/4, skipped 1
- 최신 dispatch raw: HermesResearcher, researcher-co, researcher_agent, writer-co 모두 `dispatched`
- 결과 metadata: HermesResearcher, researcher-co, researcher_agent 각각 `status=completed` JSON 존재
- 결과 파일: 세 에이전트의 `.md`와 `.json` 6개 존재
- verification 파일: 0개
- writing 결과: 아직 없음
- PM live note: 리서치 재실행 기준 지시 1건, `consumed=null`
- 현 projection: `work_group=in_progress`, `artifact_summary=ambiguous`, `verification_summary=not_run`

따라서 사용자 표시의 안전한 결론은 다음과 같다.

> **작성 진행 중 · 리서치 3/3 결과 도착 · 작성 결과 대기 · 검증 미실행**

`task.status=dispatched`만 보고 “리서치 전송됨”으로 축약하거나, 결과 파일 6개를 보고 “전체 작업 완료”로 표시해서는 안 된다.

---

## 4. 상태/근거 모델 및 UX 원칙

### 4.1 공통 판정 원칙

1. **raw 우선:** raw task, stage, dispatch, result metadata, verification, final review가 canonical source다.
2. **명시적 근거만 승격:** 더 강한 상태로 갈수록 더 강한 raw 근거가 필요하다.
3. **부분 결과 보존:** 하나라도 미도착이면 전체 도착으로 표시하지 않는다.
4. **독립 축 유지:** 단계, 에이전트, 산출물/검증을 하나의 status로 합치지 않는다.
5. **모호함 우선:** 충돌, 누락, 비표준 값, 연결 불가가 있으면 `unknown/ambiguous`로 표시한다.
6. **자유 텍스트 비추론:** `pm_live_notes`, summary, report 본문에서 완료·승인·실행 상태를 추론하지 않는다.
7. **시간 비생성:** raw timestamp가 없으면 “시간 확인 불가”로 표시한다.
8. **과거와 현재 분리:** 최신 상태와 audit history를 섞지 않는다.

### 4.2 단계 상태 모델

| 정규 상태 | 사용자 문구 | 허용 raw 근거 | 미확인 한계 | 기본 PM 다음 조치 |
|---|---|---|---|---|
| `planned` | 예정 | `stages[i].status`가 `planned` 또는 `queued` | 실제 시작 여부 알 수 없음 | 선행 단계 결과를 기다림 |
| `in_progress` | 진행 중 | `in_progress`; hold가 아닌 현재 stage | 진행률·실행 시작 시각은 별도 근거 없으면 모름 | 현재 단계 에이전트 결과 확인 |
| `completed` | 단계 완료 | stage raw `completed` | 개별 결과 품질·최종 승인과는 별개 | 다음 단계 준비/검증 |
| `skipped` | PM 판단으로 생략 | `skipped` 또는 `skipped=true` | 생략 사유가 없으면 이유 확인 불가 | 의존성에 영향 없는지 확인 |
| `blocked` | 진행 차단 | `blocked`, `entry_hold`, `gate_hold`, task active hold | 해소 여부·담당자가 없을 수 있음 | 차단 근거와 scope 확인 |
| `unknown` | 단계 상태 확인 불가 | 누락/null/허용 밖 값/충돌 | 실제 상태 전체 | raw 상태 점검 |

#### 단계 완료 계산 규칙

- `completed_stages`는 **오직 raw `completed` 수**로 표시한다.
- `skipped`는 진행 트랙에서 구분 표시하되 “완료 N/M” 분자에 넣지 않는다.
- 기존 UI의 fallback처럼 `completed || skipped`를 동일 done 수로 계산하지 않는다.
- 전체 업무 완료는 모든 필수 stage 완료, 허용된 skip, task raw 완료 정책을 모두 만족할 때만 별도 판단한다.

### 4.3 에이전트 상태 모델

| 정규 상태 | 사용자 문구 | 허용 raw 근거 | 금지 추론 | 기본 PM 다음 조치 |
|---|---|---|---|---|
| `not_dispatched` | 미전송 | stage agent 목록에는 있으나 해당 task/stage의 dispatch record 없음 | assigned 목록만으로 전송됨 처리 | 전송 필요 여부 확인 |
| `dispatch_confirmed` | 전송 확인 · 결과 대기 | 최신 dispatch raw status가 `dispatched`/전달 성공 계열이고 연결된 completed result metadata 없음 | 실행 중·성공·완료로 승격 | 결과 도착 대기 또는 재전송 판단 |
| `result_received` | 결과 도착 | worker와 task가 명시적으로 일치하는 result metadata/file 존재; 가능하면 metadata `status=completed` | 결과 품질·검증 완료·stage 완료 추론 | 결과 근거/한계 검토 |
| `failed_or_blocked` | 실패 또는 차단 | dispatch 실패/차단 또는 result metadata `status=failed/blocked`, 명시적 error | 다른 worker 성공으로 덮어쓰기 | 오류 확인·재전송/대체 판단 |
| `unknown` | 상태 확인 불가 | worker 연결 불가, status 허용 밖, dispatch/result 충돌, 파일명만 있고 안전한 연결 불가 | 긍정 상태로 fallback | raw 파일/계약 점검 |

#### 에이전트 판정 우선순위

1. 동일 실행을 가리키는 명시적 실패/차단 근거
2. worker/task가 명시적으로 일치하는 result metadata
3. dispatch 전달 확인
4. dispatch record 없음
5. 충돌 또는 연결 불가 시 unknown

실패 후 재실행 성공처럼 여러 시도가 있는 경우 `attempt_id`/correlation이 없으면 최신성만으로 성공을 확정하지 않고 상세에 “시도 연결 확인 불가”를 표시한다.

### 4.4 산출물·검증 성숙도 모델

요구된 5개 상태는 다음처럼 정규화한다.

| 정규 상태 | 사용자 문구 | 허용 raw 근거 | 미확인 한계 | 기본 PM 다음 조치 |
|---|---|---|---|---|
| `none` | 아직 결과 없음 | expected worker 대비 연결 가능한 result 0, verification 0 | 외부 경로에 미수집 파일이 있는지는 모름 | 결과 대기 |
| `partial_received` | 결과 일부 도착 | expected worker 중 일부만 result_received 또는 현재 stage 산출물 미도착 | 품질·완결성 미확인 | 미도착 에이전트/현재 단계 결과 확인 |
| `reviewable` | 검토 가능 · 미검증 | 현재 stage 또는 단계 게이트가 요구하는 결과 bundle이 식별되고 열람 가능하나 검증 완료 근거 없음 | 사실 정확성·승인 여부 미확인 | 산출물 검토/검증 시작 |
| `verified` | 검증 완료 | verification 결과가 대상 artifact id/version에 명시적으로 연결되고 허용 verdict가 존재 | 최종 PM 승인과는 별개일 수 있음 | 최종 검토 또는 다음 단계 진행 |
| `ambiguous` | 결과 범위 확인 필요 | 여러 후보, worker/stage 연결 불가, 상충 status, binding 없음 | 어떤 결과가 정본인지 모름 | 대상 파일·버전·worker 연결 확인 |

#### 검증 완료의 최소 조건

다음 조건을 모두 만족해야 `verified`다.

- verification metadata 또는 구조화 raw에 `status/verdict`가 명시됨
- 검증 대상 `artifact_id`, `result_artifact_id`, `artifact_version` 또는 동등한 binding이 있음
- binding이 실제 식별된 artifact bundle과 일치함
- active hold 또는 명시적 실패와 충돌하지 않음

검증 파일이 존재하기만 하면 `reviewable` 또는 “검증 근거 도착”까지만 허용한다.

### 4.5 근거 품질 표시

#### v1 분류

- `direct`: raw URL/응답/원문/실행 결과로 직접 확인됐다고 **구조화 필드에 명시된 경우**
- `indirect`: 검색 스니펫·간접 정황이라고 구조화 필드에 명시된 경우
- `unverified`: 미검증/추가 실측 필요라고 구조화 필드에 명시된 경우
- `unclassified`: 구조화 품질 정보가 없어 분류할 수 없음
- `conflicting`: 동일 claim 또는 scope에 직접 충돌하는 근거가 있음

#### 중요한 제한

현재 result metadata에는 보고서의 조사 방법과 claim별 evidence level이 구조화되어 있지 않다. Slice A에서는 본문을 파싱하지 않고 다음처럼 표시한다.

> “결과 도착 · 근거 품질은 파일에서 확인” 또는 “근거 품질 미분류”

Slice B에서도 result 본문 자유 텍스트를 자동 분류하지 않는다. 향후 worker가 구조화 `evidence_summary`를 기록할 때만 카드에 직접/간접/미검증 수치를 표시한다.

### 4.6 다음 PM 조치 결정 규칙

우선순위가 가장 높은 1개만 카드 CTA로 표시하고, 나머지는 상세에서 보조 목록으로 보여준다.

1. active hold/failed → `차단 근거 확인`
2. unknown/ambiguous → `raw 상태 확인`
3. 현재 stage expected agent 중 미전송 → `전송 상태 확인`
4. dispatch_confirmed 결과 대기 → `결과 도착 확인`
5. partial_received → `미도착 결과 확인`
6. reviewable + verification not run → `검증 시작/확인`
7. verified + final review 없음 → `최종 검토`
8. 현재 stage in_progress이고 위 조건 없음 → `진행 상세 보기`
9. done → `결과 보기`

CTA는 실제 write를 암시하지 않는다. Slice A의 CTA는 task detail로 이동하는 읽기 전용 동작이다.

### 4.7 UX 원칙

- 상태명 뒤에 의미를 붙인다: `전송됨` 대신 `전송 확인 · 결과 대기`.
- 색상+아이콘+텍스트를 함께 사용한다.
- 첫 화면에는 핵심 수치와 예외만 표시한다. raw path, 파일 크기, 모든 시각, audit는 상세로 보낸다.
- “완료”, “검증 완료”, “승인”은 서로 대체하지 않는다.
- positive copy보다 제한 copy를 우선한다: `결과 2/3 도착 · 1명 대기`.
- unknown을 빈칸으로 숨기지 않는다.
- `pm_live_notes`는 “비결정 맥락 · 반영 여부 미확인”으로만 표시한다.
- 검색 스니펫 기반 결과에는 `직접 검증 완료` 문구를 사용하지 않는다.

---

## 5. 화면별 요구사항

### 5.1 첫 화면 정보 구조

상단에서 하단 순서는 다음을 유지·보강한다.

1. Mission Control 요약
2. 판단 필요/다음 PM 조치
3. 진행 중 업무 보드
4. 검토 가능한 산출물
5. 최근 raw audit
6. 접힌 보조 에이전트 맥락

#### Mission Control 추가/수정

- `진행 중`: 현재 stage가 planned/in_progress인 active task 수
- `결과 대기`: 현재 stage에서 dispatch_confirmed이고 result 미도착인 task 수
- `일부 도착`: artifact maturity가 partial_received인 task 수
- `검토 가능`: reviewable인 task 수
- `막힘`: blocked/failed task 수
- `확인 불가`: unknown/ambiguous task 수

기존 summary schema를 변경하지 않는 Slice A에서는 프런트에서 task 배열로 계산한다. Slice B에서는 projection summary에 additive count를 제공한다.

### 5.2 진행 중 업무 카드

카드의 고정 순서는 다음과 같다.

1. **Outcome:** 제목, 업무 목표
2. **현재 위치:** `작성 진행 중 · 완료 1/4 · 생략 1`
3. **에이전트 진행:** `리서치 결과 3/3 도착` / `작성 writer-co 전송 확인 · 결과 대기`
4. **산출물·검증:** `리서치 결과 도착 · 작성 결과 없음 · 검증 미실행`
5. **근거/한계:** 최대 2개 경고 — `근거 품질 미분류`, `최종 산출물 연결 없음`
6. **다음 PM 조치:** 단일 CTA — `작성 결과 확인`

#### 카드 표시 규칙

- stage 전체 목록은 축약 rail로 보여준다: 완료/현재/예정/생략/차단.
- 현재 stage와 완료 수를 raw task status보다 시각적으로 우선한다.
- task raw status는 보조 행 `raw task: dispatched`로만 확장 영역에 둔다.
- 에이전트는 현재 stage와 직전 stage를 우선 표시한다.
- 결과 수는 raw 파일 수가 아니라 worker별 result bundle 수로 표시한다. Slice A에서 안전한 bundle 계산이 불가능하면 파일 수 대신 worker 이름만 표시하고 “파일 묶음 확인 필요”를 붙인다.
- 카드에 dispatch raw 문자열 전체를 노출하지 않는다.
- 카드에 gate 승인 컨트롤, live note 입력, 재전송 버튼을 두지 않는다.

### 5.3 카드 대표 문구 — `T-20260729-001`

현재 raw 기준 권장 카드 copy:

- 제목: `삼성펀드 홈페이지 운영 헬스체크 및 UI/UX 개선안 도출`
- 현재 위치: `작성 진행 중 · 완료 1/4 · 생략 1`
- 직전 단계: `리서치 완료 · 3개 에이전트 결과 도착`
- 현재 에이전트: `writer-co · 전송 확인 · 결과 대기`
- 산출물·검증: `리서치 결과 도착 · 작성 결과 없음 · 검증 미실행`
- 근거 한계: `조사 방법이 혼재함 · 직접 검증 여부는 결과별 확인 필요`
- 다음 PM 조치: `작성 결과 도착 확인`

사용 금지 copy:

- `전체 리서치 직접 검증 완료`
- `에이전트 실행 성공` — dispatch만 근거일 때
- `결과 6개 완료` — `.md/.json` sidecar 중복일 때
- `작업 완료` — writing/verification이 남아 있을 때
- `검증 완료` — verification 파일/명시적 verdict·binding이 없을 때

### 5.4 Task detail 정보 구조

고정 순서는 다음과 같다.

1. **Outcome** — 목표, task raw status, update time
2. **Progress overview** — 현재 stage, 완료/예정/생략/차단 수, 다음 PM 조치
3. **Stage timeline** — 각 stage 상태, 의존성, 기대 agent, 단계 산출물 성숙도
4. **Agent execution** — stage별 worker 상태표
5. **Artifacts** — result bundle, 파일, stage/worker 연결, 도착 근거
6. **Evidence quality & limits** — direct/indirect/unverified/unclassified/conflicting
7. **Verification** — 검증 파일, 대상 binding, verdict, 미실행/모호함
8. **Authority/Audit** — gate/final raw 근거
9. **Live note context** — 비결정 맥락, 반영 여부 미확인

#### Stage timeline 행

각 행에 다음을 표시한다.

- 단계명과 정규 상태
- raw status
- expected agents 수 / result_received 수
- 단계 산출물 상태
- 차단/생략 이유가 raw에 있을 때 이유
- depends_on

#### Agent execution 표

| 필드 | 설명 |
|---|---|
| Agent | raw `stages[].agents` 또는 `assigned_workers` |
| Stage | 연결된 stage id |
| 전달 | dispatch raw 상태와 dispatch record 링크/시각 |
| 결과 | result metadata status와 result bundle 링크 |
| 한계 | attempt 연결 없음, 근거 품질 미분류, 결과 형식 불명확 등 |
| 다음 조치 | 대기, 오류 확인, 결과 검토 |

#### Artifacts 표시

- `.md` 보고서와 `.json` metadata를 한 result bundle 안에 묶는다.
- bundle 제목 예: `HermesResearcher · research · 결과 도착`.
- 파일명, raw path, modified time은 상세에서만 표시한다.
- 현재 stage 산출물과 이전 stage 참고 결과를 구분한다.
- artifact 정본이 없으면 `최종 산출물 아님` 또는 `대상 범위 확인 필요`로 표시한다.

#### Evidence quality 표시 — 삼성펀드 사례

현재 구조화 계약만으로는 결과 본문을 자동 판정하지 않는다. 상세에서 결과 파일을 열었을 때 사용자가 확인할 수 있도록 다음 copy를 사용한다.

- HermesResearcher: `결과 도착 · 정적 HTTP/원문 분석 보고서 · 브라우저 렌더링 미실행(파일에서 확인)`
- researcher-co: `결과 도착 · 검색 스니펫 기반 · 직접 페이지 렌더링 미실행(파일에서 확인)`
- researcher_agent: `결과 도착 · 조사 방법/한계는 파일에서 확인`

위 문구를 자동 생성하려면 Slice B의 `evidence_summary`가 필요하다. 그 전에는 본문 파싱 없이 `근거 품질 미분류 · 파일에서 확인`으로 표시한다.

### 5.5 빈값·오류·충돌 상태

- stages 없음: `진행 단계 확인 불가`
- stage status 허용 밖: `알 수 없는 단계 상태 (raw: …)`
- expected agents 없음: `에이전트 계획 확인 불가`
- dispatch 없음 + result 있음: result는 표시하되 `전송 이력 복구 불가`
- dispatch 성공 + result failed: `실패 또는 차단` 우선, 두 raw 근거 병기
- 동일 worker 결과 후보 여러 개 + attempt/binding 없음: `결과 범위 확인 필요`
- verification 파일 있으나 binding 없음: `검증 근거 도착 · 대상 연결 확인 불가`
- live note에 “완료/승인” 포함: 어떤 상태도 변경하지 않음

---

## 6. API / projection 계약안

### 6.1 비교

| 안 | 내용 | 장점 | 한계/위험 | 판단 |
|---|---|---|---|---|
| A. API 변경 없음 | 기존 `stages`, `dispatches`, `result_files`, `verification_files`, projection v1을 프런트에서 조합 | 빠르고 raw write 무변경 | 파일명 파싱 중복, sidecar 중복, attempt/stage 연결 취약, 프런트 규칙 비대화 | Slice A에 한정 |
| B. 최소 additive projection 확장 | 서버에서 정규 stage/agent/artifact/next action을 계산해 `dashboard_projection.progress` 추가 | 단일 규칙, 테스트 용이, UI 단순화, fail-safe 일관성 | correlation 없는 과거 데이터는 여전히 ambiguous | **권고** |
| C. persistence 대개편 | raw dispatch/result schema에 attempt/stage/artifact identity 강제 | 장기적으로 가장 정확 | 범위·마이그레이션·운영 위험 큼 | v1 비목표 |

### 6.2 권고 계약

기존 `dashboard_projection.schema_version=1` 필드는 유지한다. additive `progress` 객체에 별도 `schema_version=1`을 둔다. 기존 소비자는 영향받지 않는다.

```json
{
  "dashboard_projection": {
    "schema_version": 1,
    "progress": {
      "schema_version": 1,
      "current_stage_id": "writing",
      "stage_counts": {
        "planned": 1,
        "in_progress": 1,
        "completed": 1,
        "skipped": 1,
        "blocked": 0,
        "unknown": 0
      },
      "stages": [
        {
          "stage_id": "research",
          "label": "Research",
          "state": "completed",
          "raw_state": "completed",
          "expected_agent_count": 3,
          "result_received_count": 3,
          "artifact_state": "reviewable",
          "evidence_refs": [
            "task.stages[0].status",
            "result:T-20260729-001:HermesResearcher",
            "result:T-20260729-001:researcher-co",
            "result:T-20260729-001:researcher_agent"
          ],
          "limitations": ["verification_not_run"]
        }
      ],
      "agents": [
        {
          "stage_id": "writing",
          "agent_id": "writer-co",
          "state": "dispatch_confirmed",
          "dispatch": {
            "raw_state": "dispatched",
            "attempted_at": "2026-07-29T12:53:29",
            "evidence_ref": "dispatch:..."
          },
          "result": null,
          "limitations": ["execution_not_proven", "result_not_received"]
        }
      ],
      "artifact_maturity": {
        "state": "partial_received",
        "scope": "task",
        "received_agents": 3,
        "expected_agents": 4,
        "verification_state": "not_run",
        "limitations": ["current_stage_result_missing"]
      },
      "evidence_quality": {
        "state": "unclassified",
        "direct": null,
        "indirect": null,
        "unverified": null,
        "conflicts": []
      },
      "next_pm_action": {
        "kind": "wait_for_result",
        "label": "작성 결과 도착 확인",
        "scope": "stage:writing",
        "reason_code": "dispatch_confirmed_result_missing",
        "target": "task_detail"
      },
      "data_quality": []
    }
  }
}
```

### 6.3 result bundle 최소 규칙

서버 projection 계산 시 다음 순서로 result를 묶는다.

1. `.json` result metadata의 `task_id`, `worker/worker_name`, `report_file`, `status`를 우선 사용한다.
2. `report_file`이 실제 `result_files[].name`과 일치하면 metadata+report를 한 bundle로 연결한다.
3. stage는 명시적 `stage_id`가 있으면 사용한다. 없으면 다음의 안전한 규칙만 허용한다.
   - 파일명 task 부분에 `-writing`, `-verify`, `-verification`, `-final`이 명시된 경우 해당 stage 후보
   - 접미 stage가 없는 result는 `research` agent와 worker가 정확히 일치할 때만 research에 연결
4. 연결이 둘 이상 가능하거나 worker가 stage agents에 없으면 `ambiguous`.
5. `.md` 존재만으로 metadata `completed`를 만들지 않는다.

### 6.4 장기적으로 raw producer에 권장하는 선택 필드

이번 slice에서 persistence migration을 요구하지 않으며, 새 result/dispatch producer가 점진적으로 기록할 수 있는 optional 필드다.

```json
{
  "attempt_id": "opaque-id",
  "stage_id": "research",
  "artifact_id": "opaque-id",
  "artifact_version": "v1",
  "evidence_summary": {
    "method": "direct_http_static",
    "direct_count": 12,
    "indirect_count": 3,
    "unverified_count": 7,
    "limitations": ["browser_rendering_not_run"]
  }
}
```

주의: optional 필드가 없으면 기존 데이터는 계속 동작해야 하며, projection은 모호함을 보존한다.

### 6.5 파일 후보

#### Slice A

- `operations_dashboard/app.js`
- `operations_dashboard/styles.css`
- `tests/test_dashboard_static_contract.py`
- 필요 시 `operations_dashboard/index.html` — Mission Control label/hook 변경이 필요할 때만

#### Slice B

- `operations_dashboard_projection.py`
- `operations_dashboard_server.py` — raw file metadata를 projection input에 추가하는 최소 변경만
- `operations_dashboard/app.js`
- `tests/test_dashboard_projection.py`
- `tests/test_dashboard_api_contracts.py`
- `tests/test_dashboard_static_contract.py`

변경 금지:

- raw brief/dispatch/result/verification write 로직
- gate/live-note/final-review endpoint 계약
- 기존 raw operations 파일

---

## 7. 구현 slice 및 acceptance criteria

### Slice A — 기존 API 기반 진행 카드·상세 가시화

#### 범위

- current stage 중심 카드 copy
- completed와 skipped 분리 계산
- 에이전트별 `미전송 / 전송 확인·결과 대기 / 결과 도착 / 실패·차단 / 확인 불가` 표시
- result metadata `.json`과 report 파일의 보수적 client-side bundle 연결
- 다음 PM 조치 단일 CTA
- task detail에 Agent execution, Evidence limits 블록 추가

#### Acceptance criteria

- [ ] 카드가 task raw `dispatched`보다 `writing=in_progress`를 우선해 `작성 진행 중`으로 표시한다.
- [ ] 완료 단계 수는 `completed`만 포함하고 `skipped`는 별도 수치로 표시한다.
- [ ] dispatch raw `dispatched`만 있는 writer-co를 `전송 확인 · 결과 대기`로 표시한다.
- [ ] 연결 가능한 completed result metadata가 있는 리서치 3개 agent를 각각 `결과 도착`으로 표시한다.
- [ ] `.md`와 `.json` sidecar를 6개 독립 결과 완료로 표시하지 않는다.
- [ ] verification 파일이 없는 사례를 `검증 미실행`으로 표시한다.
- [ ] 일부 결과만 있는 fixture를 `결과 일부 도착`으로 표시한다.
- [ ] unknown/연결 불가 fixture를 `상태 확인 불가` 또는 `결과 범위 확인 필요`로 표시한다.
- [ ] PM next action은 카드당 1개이며 task detail을 연다.
- [ ] live note의 문구가 어떤 실행/완료/승인 상태도 바꾸지 않는다.
- [ ] 검색 스니펫 결과가 직접 검증 완료로 표시되지 않는다.

#### Non-goals

- projection schema 변경
- write endpoint 변경
- worker producer 변경
- result 본문 자동 파싱
- 실제 재전송/검증 실행 버튼 추가

### Slice B — additive progress projection

#### 범위

- `dashboard_projection.progress` 생성
- stage/agent/result bundle/artifact maturity/next PM action 서버 정규화
- UI가 progress projection을 우선 사용하고 없으면 Slice A fallback 사용
- API와 projection contract test 추가

#### Acceptance criteria

- [ ] 기존 projection top-level schema와 필드가 유지된다.
- [ ] `progress.schema_version=1`이 additive하게 제공된다.
- [ ] input task와 raw 파일 객체를 mutate하지 않는다.
- [ ] missing/null/unknown이 서로 구분되고 긍정 상태로 승격되지 않는다.
- [ ] task/stage/worker가 정확히 연결된 result metadata만 `result_received`가 된다.
- [ ] dispatch 성공만으로 result_received가 되지 않는다.
- [ ] result 일부 도착만으로 stage completed가 되지 않는다.
- [ ] verification artifact의 대상 binding이 없으면 verified가 되지 않는다.
- [ ] active hold/failed는 next PM action 우선순위에서 가장 앞선다.
- [ ] projection 부재 시 UI는 fail-safe fallback copy를 표시한다.
- [ ] 기존 API/write/static/projection 테스트가 모두 통과한다.

#### Non-goals

- 과거 raw 파일 migration
- attempt correlation 자동 복원
- 자유 텍스트 claim 추출
- final approval 정책 변경
- 새로운 write action

---

## 8. 테스트 / 검증 계획

### 8.1 단위 테스트 fixture

1. **전송만 성공**
   - stage in_progress, dispatch=dispatched, result 없음
   - 기대: dispatch_confirmed, 결과 대기, 검증 미실행
2. **일부 결과 도착**
   - expected agents 3, result metadata 1
   - 기대: 1/3 결과 도착, partial_received, stage 미완료 유지
3. **전체 agent 결과 도착·검증 전**
   - expected agents 3, 연결 가능한 result 3, stage raw in_progress
   - 기대: 각 result_received, artifact reviewable 가능, stage는 in_progress 유지
4. **실패와 dispatch 충돌**
   - dispatch=dispatched, result metadata=failed
   - 기대: failed_or_blocked, 오류 확인 CTA
5. **비표준 worker/file**
   - result 파일은 있으나 worker/stage 연결 불가
   - 기대: unknown/ambiguous
6. **sidecar 묶음**
   - 같은 worker의 metadata JSON + report MD
   - 기대: bundle 1개
7. **검증 파일만 존재·binding 없음**
   - 기대: 검증 근거 도착, 대상 연결 확인 불가, verified 아님
8. **검증 verdict+binding 일치**
   - 기대: verified
9. **live note에 완료/승인 문구**
   - 기대: 상태 무변경
10. **missing/null/future status**
    - 기대: 모두 fail-safe, raw 값 보존

### 8.2 대표 사례 contract test

`T-20260729-001`를 축약한 fixture에서 다음을 검증한다.

- current stage `writing`
- stage counts: completed 1, in_progress 1, planned 1, skipped 1
- research agents 3명 result_received
- writer-co dispatch_confirmed, result 없음
- task artifact maturity partial_received 또는 scope별 `research=reviewable`, `writing=none`
- verification not_run
- next PM action `작성 결과 도착 확인`
- “직접 검증 완료”, “전체 완료”, “결과 6개 완료” 문구 부재

### 8.3 정적 UI contract

- 카드 정보 순서가 Outcome → Progress → Agent → Artifact/Verification → Limits → Next action 순서인지 검사
- card primary action은 1개인지 검사
- task detail에 Agent execution, Evidence quality & limits 섹션 hook 존재
- 색 외에 텍스트 상태가 존재
- raw gate controls와 live note input은 task detail에만 존재
- Discord/channel/sync/deep-link 문구가 Dashboard-only surface에 없음

### 8.4 수동 브라우저 QA

뷰포트: 1440px, 1024px, 390px.

- 첫 화면 10초 판독: 현재 stage, 결과 도착 수, 검증 여부, 다음 조치
- 긴 한국어 제목/worker 이름/한계 문구 overflow
- 카드에서 상세로 focus 이동, Escape 닫기, focus 복귀
- 키보드만으로 카드 CTA와 result 파일 열기
- status 아이콘/텍스트가 색상 없이도 구분되는지
- 15초 refresh 후 펼침/상세 맥락이 치명적으로 깨지지 않는지
- projection 누락/부분 응답에서 JS 오류 없이 fallback 표시

### 8.5 회귀 검증 명령

```bash
python3 -m unittest \
  tests.test_dashboard_projection \
  tests.test_dashboard_api_contracts \
  tests.test_dashboard_static_contract
```

저장소의 전체 테스트 명령이 별도로 정의되어 있으면 developer가 추가 실행한다. 테스트 수와 결과는 후속 카드 handoff에 실제 실행값으로 기록한다.

### 8.6 출시 게이트

다음 중 하나라도 발생하면 출시 보류다.

- dispatch만으로 실행/결과 완료 표시
- 일부 결과로 stage/task 완료 표시
- 검증 binding 없이 검증 완료 표시
- unknown/missing을 숨김 또는 긍정 상태로 fallback
- existing write API 회귀
- 대표 사례에서 검색 스니펫 기반 결과를 직접 검증 완료로 표현

---

## 9. 가정 · 리스크 · 미결 질문

### 9.1 가정

- **가정 A1:** `stages[].agents`는 해당 stage에서 기대하는 agent 목록으로 사용할 수 있다.
- **가정 A2:** result `.json`의 `task_id`, `worker_name/worker`, `status`, `report_file`은 report bundle 연결에 raw 근거로 사용할 수 있다.
- **가정 A3:** task detail로 이동하는 읽기 전용 CTA만으로 Slice A의 다음 PM 조치 요구를 충족한다.
- **가정 A4:** 기존 API 응답에 result JSON metadata 자체는 포함되지 않으므로, Slice A client-side 연결에는 현재 `result_files` 이름 규칙을 제한적으로 사용하거나 서버가 metadata를 읽는 Slice B가 필요하다.
- **가정 A5:** “검토 가능”은 “검증 완료”나 “PM 승인”을 의미하지 않는다.

### 9.2 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| 파일명 규칙으로 잘못된 worker/stage 연결 | 잘못된 result_received | 일치 조건을 좁히고 불확실하면 ambiguous; Slice B로 이동 |
| task status와 stage status 불일치 | 현재 위치 오판 | stage 우선, task raw는 보조 표시, 충돌 경고 |
| 과거 result에 stage_id/attempt_id 없음 | 재실행·최신 결과 연결 모호 | 자동 확정하지 않고 ambiguity 표시 |
| evidence 품질이 본문에만 존재 | 카드에서 품질 과장/누락 | 본문 파싱 금지, unclassified 표시, optional 구조화 필드 권고 |
| completed stage인데 expected agent 결과 일부 없음 | raw 상태와 산출물 불일치 | 단계 raw 완료는 보존하되 `결과 일부/근거 불일치` 경고 |
| 카드 정보 과밀 | 첫 화면 판독 저하 | 현재/직전 stage만, 경고 최대 2개, 단일 CTA |
| 기존 tests가 문자열 구조에 강결합 | 작은 UI 변경에도 회귀 | 기존 contract 의도 유지, 새 hook 중심 테스트 추가 |

### 9.3 미결 질문

1. `completion_policy=any`는 agent 결과 성숙도에서 expected denominator를 1로 볼지, 전체 agent를 보여주되 stage completion gate만 any로 볼지? **권고:** agent 상태는 전원 표시하고, stage 완료 정책만 별도 표시한다.
2. `task.status=dispatched`와 `writing=in_progress`가 장기간 불일치할 때 data quality 경고로 볼 것인가? **권고:** 현재 위치는 stage 기준, raw task status 보조, 모순이 아닌 granularity 차이로 취급한다.
3. result `.json` metadata를 API `result_files` 항목에 inline할 수 있는가, 아니면 projection builder에서만 읽을 것인가? **권고:** raw file 목록은 그대로 두고 projection에서 필요한 안전한 필드만 정규화한다.
4. `reviewable` 판정에 stage raw `completed`가 필수인가? **권고:** 열람 가능한 결과 bundle만 있으면 reviewable일 수 있으나 stage 상태와 별개로 표시한다.
5. PM next action이 향후 실제 write action으로 발전할 것인가? **권고:** v1은 detail navigation만 제공하고 write action은 별도 기획한다.
6. evidence_summary optional contract를 worker producer 후속 범위에 포함할 것인가? **권고:** 이번 구현 후 reviewer 결과를 보고 별도 developer 카드로 분리한다.

---

## 10. 개발자 / 검증자 후속 카드 권고

### 10.1 Developer 카드 — Slice A

**제목:** `DEV-PROGRESS-1: Dashboard 진행·에이전트 결과 가시화 Slice A`

**담당:** `developer`

**입력:** 이 PRD 전체, 특히 4·5·7·8장

**작업:** 기존 API를 사용해 카드와 task detail의 stage/agent/artifact/verification/next action 표시를 구현하고 tests를 보강한다.

**필수 handoff:** 변경 파일, 실제 테스트 명령/통과 수, `T-20260729-001` 렌더링 캡처 또는 재현 설명, 남은 모호함.

### 10.2 Reviewer 카드 — Slice A acceptance review

**제목:** `REVIEW-PROGRESS-1: 진행 가시화 오표시·회귀 검증`

**담당:** `reviewer`

**의존:** Developer Slice A 완료

**작업:** PRD AC와 fixture를 기준으로 dispatch/result/completion/verification 오표시, Dashboard-only 제약, 접근성, 기존 write contract 회귀를 검증한다.

**출시 차단 조건:** 8.6의 출시 게이트 위반.

### 10.3 Developer 카드 — Slice B

**제목:** `DEV-PROGRESS-2: additive progress projection 계약 구현`

**담당:** `developer`

**의존:** Slice A reviewer 결과 및 남은 ambiguity 확인

**작업:** `dashboard_projection.progress`를 additive하게 구현하고 UI를 projection-first/fallback-safe로 전환한다.

**필수 handoff:** projection fixture matrix, raw non-mutation 증거, API backward compatibility, 전체 관련 테스트 결과.

### 10.4 PM 후속

**담당:** `pm`

- Slice A reviewer 결과를 보고 Slice B 진입 여부 결정
- evidence_summary producer 계약을 별도 backlog로 승인/보류
- 완료 후 첫 화면 10초 판독 성공 기준을 실제 운영 사례로 확인

---

## 수용 기준 최종 체크리스트

- [x] 문제, 목표, 비목표를 정의했다.
- [x] 사용자 의사결정과 정량·정성 성공 기준을 정의했다.
- [x] 현행 API·projection·UI와 표시 갭을 코드 기준으로 정리했다.
- [x] 단계 6종 상태 모델을 raw 근거·문구·한계·PM 조치와 연결했다.
- [x] 에이전트 5종 상태 모델을 정의하고 dispatch와 result를 분리했다.
- [x] 산출물·검증 5종 성숙도 모델을 정의했다.
- [x] 첫 화면, 카드, task detail 요구사항을 정의했다.
- [x] `T-20260729-001`의 전송과 결과 도착을 구분한 예시를 포함했다.
- [x] 검색 스니펫 기반 결과를 직접 검증 완료로 표현하지 않는 원칙을 포함했다.
- [x] API 변경 없는 안과 최소 additive projection 확장안을 비교하고 권고안을 제시했다.
- [x] 파일 후보, 데이터 계약, 2개 안전 slice, AC, 테스트, non-goal을 구체화했다.
- [x] 가정, 리스크, 미결 질문을 라벨링했다.
- [x] developer, reviewer, pm 후속 카드를 권고했다.

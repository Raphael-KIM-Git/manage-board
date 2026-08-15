# Agent Hub Dashboard v1.1 — 최종 결과물 영역·전면 Artifact Viewer PRD

- 문서 상태: 개발·검증 handoff용
- 제품 범위: Agent Hub Dashboard-only v1.1
- 기준 저장소: `/home/raphael/myproject`
- 대표 사례: `T-20260729-001`
- 선행 문서: `Agent-Hub-Dashboard-v1.1-progress-and-followup-PRD-ko.md`
- 핵심 원칙: **최종 결과물은 강한 raw binding으로만 확정하고, 모든 artifact viewer는 현재 detail modal보다 앞선 최상위 전면 레이어에서 연다.**

## 기획 요약

현재 task detail은 결과 파일과 검증 파일을 한 영역에 나열한다. 사용자는 여러 결과 중 무엇이 최종 전달본인지 빠르게 알기 어렵다. 또한 `detailModal`과 `taskDetailModal`이 같은 z-index를 사용하고 DOM에서 task detail이 뒤에 있어, task detail 안에서 결과를 열면 viewer가 그 뒤에 가려질 수 있다.

v1.1은 task detail 최상단에 읽기 전용 `Final Deliverable` 영역을 신설한다. 이 영역은 파일명, 수정 시각, 자유 텍스트만으로 최종본을 추정하지 않는다. raw task/stage, exact result envelope, artifact identity/version, verification binding, PM final review binding을 단계적으로 평가한다. 근거가 부족하면 일반 Artifacts 중 하나를 승격하지 않고 `최종 결과물 확인 불가`를 명시한다.

동시에 기존 결과 viewer를 top-layer 전면 viewer로 정리한다. artifact 진입점이 overview, task detail, verification 중 어디든 동일한 viewer coordinator를 사용하며, viewer는 task detail보다 높은 stack에 렌더링된다. Escape는 최상위 viewer만 닫고, 닫은 뒤에는 클릭한 artifact로 포커스를 되돌린다.

권고 구현 순서는 다음과 같다.

1. Slice 0 — 현행 contract와 fixture 고정
2. Slice 1 — additive `final_deliverable` projection
3. Slice 2 — task detail 상단 Final Deliverable UI
4. Slice 3 — 전면 viewer stack/focus/keyboard 통합
5. Slice 4 — 브라우저·접근성·회귀 검증 후 독립 배포

---

## 1. 문제 / 사용자 시나리오 / 목표 / 비목표

### 1.1 문제

1. `artifact_summary.items`는 task 관련 결과 파일을 모두 노출한다. 여러 stage와 attempt의 파일이 섞일 수 있어 최종 전달본을 빠르게 식별하기 어렵다.
2. 현재 `artifact_summary.state`는 결과 파일이 둘 이상이면 `ambiguous`가 된다. 이 상태는 “파일이 여러 개”라는 사실만 설명하고 “최종본 근거가 있는가”를 별도 모델링하지 않는다.
3. task detail의 `Artifact Review`는 일반 Artifacts, Acceptance criteria, Verification, Target scope, review binding을 한 패널에 배치한다. 최종 전달본이 별도 우선순위로 드러나지 않는다.
4. `T-20260729-001`은 `final_write=skipped`, writing과 verification은 completed, PM final review는 `meets`다. 그러나 PM review에 artifact id/version binding이 없고 writing result에는 HTML 후보가 둘 이상이다. 임의로 최신 파일을 최종본으로 표시하면 false positive다.
5. `detailModal`과 `taskDetailModal`은 모두 `.modal-shell { z-index: 60 }`을 사용한다. DOM에서 `taskDetailModal`이 `detailModal` 뒤에 있으므로 같은 stacking context에서 task detail이 viewer보다 앞에 그려질 수 있다.
6. 현재 Escape handler는 brief, detail, task detail을 한 번에 모두 닫는다. nested viewer에서 Escape 한 번으로 부모 task detail까지 닫히며, 계층적 닫기와 return focus를 보장하지 않는다.
7. 현재 `openDetail()`은 artifact trigger를 저장하지 않고, `closeDetail()`도 포커스를 복원하지 않는다.
8. body scroll lock은 brief modal의 `setModalOpen()`에만 연결되어 있다. task detail 또는 artifact viewer 단독 표시 중 배경 스크롤을 일관되게 잠그지 않는다.

### 1.2 사용자 시나리오

#### 시나리오 A — 명시적 final_write 결과 확인

- 사용자가 완료 task를 연다.
- raw `final_write` stage가 completed다.
- exact active final_write result envelope가 명시적 artifact identity를 제공한다.
- task detail 최상단에 `Final Deliverable · 확인됨`이 표시된다.
- 사용자는 대표 파일을 클릭하고 전면 viewer에서 읽는다.
- Escape를 누르면 viewer만 닫히고 task detail은 유지되며 클릭한 버튼으로 포커스가 돌아온다.

#### 시나리오 B — final_write가 생략된 정상 파이프라인

- `final_write=skipped`이고 writing 또는 research가 deliverable stage다.
- deliverable stage가 completed이고 exact active result envelope가 있다.
- verification과 PM final review가 동일 artifact/version에 명시적으로 binding되어 있다.
- Final Deliverable 영역은 `final_write 생략 · writing 산출물을 최종 전달본으로 확인`과 근거를 함께 표시한다.

#### 시나리오 C — 대표 사례 `T-20260729-001`

확인된 raw 사실:

- task status: `completed`
- writing: `completed`, active derived task `T-20260729-001-writing-r1`
- verification: `completed`, derived task `T-20260729-001-verify`
- final_write: `skipped`
- active writing result envelope: completed, `report_file=T-20260729-001-writing-r1__writer-co.md`
- writing HTML 후보: `...130629.html`, `...165206.html`
- verify-co result envelope: completed
- PM final review: `verdict=meets`
- PM final review의 artifact id/version binding: 없음
- writing envelope의 명시적 `artifact_id`/`artifact_version`: 없음

안전한 UI 예시:

> **Final Deliverable — 최종 결과물 확인 불가**
> 최종 작성 단계는 생략되었고 writing·verification·PM final review 기록은 있습니다. 그러나 PM final review와 검증 결과가 특정 HTML artifact/version에 연결되지 않았으며 active writing 결과에도 HTML 후보가 여러 개입니다. 일반 Artifacts에서 후보와 raw 근거를 확인할 수 있지만 어느 파일도 최종본으로 승격하지 않습니다.

보조 메타데이터:

- 후보 deliverable stage: Writing
- stage status: 완료
- final_write: 생략
- active attempt: `T-20260729-001-writing-r1`
- artifact version: 확인 불가
- verification: 결과 도착 / artifact binding 확인 불가
- PM final review: meets / artifact binding 확인 불가
- reason code: `binding_insufficient`

이 사례에서 `165206.html`을 수정 시각이나 파일명 숫자로 골라 `최종본`이라 표시하면 안 된다.

#### 시나리오 D — 근거 충돌

- PM review는 artifact version v2를 가리키지만 verification은 v1을 가리킨다.
- UI는 `근거 충돌 · 최종 결과물 확인 불가`를 표시한다.
- 두 binding을 raw evidence로 보여주되 어느 파일도 기본 선택하지 않는다.

#### 시나리오 E — 작은 화면

- 사용자가 390px 폭에서 artifact를 연다.
- viewer는 viewport 전체를 사용하고 헤더와 닫기 버튼을 안정적으로 노출한다.
- 콘텐츠만 내부 스크롤하며 배경 task detail은 스크롤되지 않는다.
- 브라우저 확대 200%에서도 닫기, 다운로드, 새 탭 동작이 가려지지 않는다.

### 1.3 목표

1. task detail을 연 뒤 5초 안에 최종 결과물 확인 여부, 근거 stage, version, 검증/PM review 상태를 판단하게 한다.
2. 근거가 충분한 경우에만 최종 artifact를 별도 영역에서 열 수 있게 한다.
3. 근거가 부족하거나 충돌하면 false-positive final 표시 0건을 유지한다.
4. artifact 진입점과 무관하게 viewer를 현재 모든 modal보다 앞선 전면 레이어로 연다.
5. Escape, backdrop, 닫기 버튼, focus trap, return focus, scroll lock을 계층적으로 일관되게 처리한다.
6. 기존 result/verification/detail API와 읽기 전용 Dashboard 동작을 유지한다.

### 1.4 성공 지표

- fixture 기반 final classification 오탐 0건
- unbound/ambiguous fixture에서 임의 final artifact 선택 0건
- final_write skipped fixture에서 binding 충족 시 confirmed, 미충족 시 unavailable 판정 100%
- 모든 artifact trigger가 동일 top-layer viewer를 사용 100%
- viewer open 시 task detail보다 높은 computed stack 확인 100%
- Escape 1회당 topmost layer 1개만 닫힘 100%
- viewer close 후 return focus 성공 100%
- 390/768/1440px, Chromium/Firefox/WebKit 목표 브라우저에서 핵심 flow 통과
- 기존 projection/server/static test 회귀 0건

### 1.5 비목표

- Dashboard에서 final artifact를 지정·수정·승인하는 write control
- 파일명, suffix, mtime, HTML 제목, 자유 텍스트를 이용한 최종본 자동 추정
- 기존 raw task/stage/result envelope/PM review를 Dashboard가 수정하는 기능
- result 파일 저장 구조의 전면 개편
- 임의의 외부 URL 또는 로컬 경로 열기
- HTML artifact 내부 스크립트 실행 권한 확대
- artifact diff, annotation, inline approval, comment 기능
- 과거 task의 누락된 artifact/version binding 자동 복구
- PM final review `meets`를 artifact binding 없이 final approval로 승격

---

## 2. 사용자와 가치

### 2.1 주요 사용자

- Raphael: 여러 agent 결과 중 실제 전달본을 빠르게 열고 근거를 확인한다.
- HermesPM: final review가 어떤 artifact/version에 적용됐는지 감사 가능하게 확인한다.
- Developer/Verifier/QA: projection 판정과 modal stack을 동일 contract로 구현·검증한다.

### 2.2 사용자 가치

- 최종 결과를 찾기 위해 여러 파일을 순서대로 열 필요가 줄어든다.
- 확실하지 않은 파일이 최종본처럼 보이는 위험을 줄인다.
- viewer가 부모 modal 뒤로 숨거나 Escape로 전체 맥락이 사라지는 문제를 제거한다.
- final_write 생략 파이프라인도 같은 원칙으로 설명한다.

---

## 3. Final Artifact 판정·근거·모호성 상태 모델

### 3.1 용어

- **Artifact file:** Dashboard가 읽기 전용으로 열 수 있는 개별 파일.
- **Result bundle:** exact result envelope와 그 envelope가 연결한 report/artifact 파일 묶음.
- **Deliverable stage:** 최종 사용자 산출물을 생산한 stage. verification은 deliverable stage가 아니다.
- **Final Deliverable:** canonical evidence로 특정 artifact identity 또는 version이 최종 전달본임을 확인한 결과.
- **Candidate:** deliverable stage에 귀속되지만 최종 binding이 충분하지 않은 artifact. Final Deliverable로 표시하지 않는다.
- **Binding:** verification 또는 PM final review가 artifact id/version/report file을 명시적으로 참조하는 관계.

### 3.2 독립 상태 축

Final Deliverable projection은 다음 축을 합쳐 단일 문자열로 축약하지 않는다.

1. task raw status
2. final_write raw status/skipped
3. deliverable stage id/raw status/active derived task id
4. active result envelope status
5. artifact identity
6. artifact version
7. verification stage/result/binding
8. PM final review verdict/binding
9. conflict/data quality

### 3.3 최종 판정 상태

| state | 의미 | 대표 표시 | 클릭 가능 여부 |
|---|---|---|---|
| `confirmed` | 최종 artifact identity가 강한 근거로 확정됨 | 최종 결과물 · 확인됨 | 대표 artifact 클릭 가능 |
| `candidate_unconfirmed` | deliverable stage와 후보는 확인되나 final binding이 부족 | 최종 결과물 확인 불가 · 후보 근거 있음 | Final 영역에서 대표 클릭 금지, 일반 Artifacts에서 후보 열람 가능 |
| `ambiguous` | 둘 이상의 artifact/binding이 동일 우선순위로 충돌 | 최종 결과물 확인 불가 · 후보 여러 개 | 일반 Artifacts만 가능 |
| `conflict` | verification과 PM review 또는 active attempt가 서로 다른 artifact를 지시 | 최종 결과물 확인 불가 · 근거 충돌 | 일반 Artifacts만 가능 |
| `unavailable` | deliverable stage/result/artifact 근거가 없음 | 최종 결과물 확인 불가 | 없음 |
| `unknown` | malformed/미지원 raw 값으로 판정 불가 | 최종 결과물 확인 불가 · raw 확인 필요 | 안전한 일반 파일만 가능 |

`candidate_unconfirmed`, `ambiguous`, `conflict`, `unavailable`, `unknown`은 모두 사용자 heading을 `최종 결과물 확인 불가`로 통일하고, reason code와 설명을 분리한다.

### 3.4 reason code

- `final_write_result_missing`
- `deliverable_stage_not_completed`
- `active_attempt_unresolved`
- `artifact_identity_missing`
- `artifact_version_missing`
- `binding_insufficient`
- `multiple_equal_candidates`
- `verification_binding_mismatch`
- `pm_review_binding_mismatch`
- `verification_pm_binding_conflict`
- `malformed_evidence`
- `unsupported_stage_shape`

reason code는 API 안정성용 영문 enum이고 UI는 한국어 copy map을 사용한다.

### 3.5 판정 우선순위

#### Rule A — final_write completed 우선

다음을 모두 만족하면 `confirmed`다.

1. raw final_write stage가 존재한다.
2. `status=completed`이고 `skipped`가 true가 아니다.
3. active final_write derived task id를 exact match하는 completed result envelope가 있다.
4. envelope가 특정 artifact identity를 직접 제공한다.
5. 해당 artifact가 현재 allowlisted result file 목록에 실제 존재한다.
6. 동일 우선순위의 다른 active completed envelope가 다른 artifact를 가리키지 않는다.

artifact identity 우선순위:

1. envelope `artifact_id` 또는 `result_artifact_id`
2. envelope `artifact_version`/`result_version`과 유일하게 매칭되는 artifact
3. envelope `report_file` 자체가 사용자가 열 수 있는 deliverable이고 파일이 존재하는 경우

`artifacts[]`가 여러 파일이면 명시적 primary/final role 또는 binding 없이 하나를 고르지 않는다.

#### Rule B — final_write skipped fallback

다음을 모두 만족할 때만 `confirmed`다.

1. final_write raw가 명시적으로 skipped다.
2. deliverable stage가 writing 또는 research로 raw pipeline shape에서 결정된다.
3. deliverable stage raw가 completed다.
4. active derived task id와 exact match하는 completed result envelope가 있다.
5. 특정 artifact identity/version이 존재한다.
6. verification evidence가 같은 artifact identity/version에 binding되어 있다.
7. PM final review가 `meets` 또는 `partial`이고 같은 artifact identity/version에 binding되어 있다.
8. active hold 또는 서로 다른 binding 충돌이 없다.

위 조건 중 1~5는 만족하지만 6~7이 없으면 `candidate_unconfirmed`다. 후보가 여러 개이면 `ambiguous`, binding 대상이 서로 다르면 `conflict`다.

#### Rule C — final_write stage 자체가 없는 파이프라인

- raw `pipeline_shape`가 final_write를 사용하지 않는 shape임이 명시된 경우 Rule B를 적용한다.
- pipeline shape가 missing/null/unknown이면 writing/research 중 하나를 임의 선택하지 않는다.
- 완료 stage가 하나뿐이어도 파일명 추정으로 final을 만들지 않는다.

### 3.6 deliverable stage 결정

projection은 기존 `operations_sync.deliverable_stage_id()`의 방향을 참고하되 fallback `research`를 무조건 반환하는 동작을 그대로 사용하지 않는다.

권고 contract:

1. completed, non-skipped final_write
2. final_write가 명시적으로 skipped일 때 completed, active writing
3. writing이 pipeline shape상 명시적으로 skipped/미사용일 때 completed, active research
4. 그 외 `null + reason`

`verification`은 최종 산출물을 생산하는 stage가 아니라 평가 근거이므로 deliverable stage가 될 수 없다.

### 3.7 artifact identity와 version

- `name`은 열람 경로 식별자일 수 있으나 version은 아니다.
- version은 explicit metadata의 `artifact_version` 또는 `result_version`만 사용한다.
- mtime, 파일명 timestamp, suffix `r1`, 배열 순서, “latest”는 version을 증명하지 않는다.
- version이 없어도 Rule A에서 artifact identity가 유일하면 `confirmed`가 가능하지만 UI에는 `버전 확인 불가`를 표시한다.
- Rule B는 verification/PM review와의 동일 대상 확인을 위해 identity 또는 version binding이 필요하다.

### 3.8 검증과 PM review

- verification stage completed는 검증 단계 완료만 뜻한다.
- verify result envelope completed는 검증 결과 도착만 뜻한다.
- artifact id/version과 verdict가 있어야 final artifact에 대한 verification binding으로 사용한다.
- PM final review `meets/partial`은 review record가 긍정적임을 뜻한다.
- artifact binding이 없으면 `review_recorded_unbound`이며 최종 artifact를 확정하지 않는다.
- `not_meets`, active hold, binding mismatch는 final confirmed를 차단한다.

### 3.9 판정 의사코드

```text
if malformed canonical evidence:
  unknown
else if completed non-skipped final_write exists:
  resolve exact active final_write bundle
  resolve explicit artifact identity
  if zero -> unavailable/candidate_unconfirmed
  if multiple or conflict -> ambiguous/conflict
  else -> confirmed
else if final_write explicitly skipped or pipeline explicitly has no final_write:
  resolve completed active deliverable stage
  resolve exact active bundle and artifact identity
  if missing -> unavailable
  if multiple -> ambiguous
  compare verification binding and PM final review binding
  if both bind same artifact and review is meets/partial and no hold -> confirmed
  if bindings conflict -> conflict
  else -> candidate_unconfirmed(binding_insufficient)
else:
  unavailable or unknown
```

---

## 4. Task Detail 상단 Final Deliverable 영역

### 4.1 정보 구조

`renderTaskDetail()`의 순서는 다음과 같이 변경한다.

1. modal header
2. **Final Deliverable**
3. Outcome
4. Progress overview
5. Stage timeline
6. Agent execution
7. Artifacts
8. Verification
9. Sync / Watchdog evidence
10. Evidence quality & limits
11. Authority / Audit
12. 허용된 detail-only 후속 요청 영역

Final Deliverable은 body의 첫 section이어야 하며 일반 Artifacts보다 항상 앞선다.

### 4.2 confirmed 상태 구성

- kicker: `FINAL DELIVERABLE`
- 제목: artifact display name
- 상태 badge: `확인됨`
- 기본 CTA: `최종 결과물 열기`
- 보조 action: 다운로드, 새 탭은 viewer 내부에서 제공
- 근거 요약:
  - source stage
  - stage status
  - active attempt/derived task id
  - artifact id
  - version 또는 `확인 불가`
  - verification state/binding
  - PM final review verdict/binding
- 설명: final_write 직접 결과인지 skipped fallback인지 명시

### 4.3 확인 불가 상태 구성

- kicker: `FINAL DELIVERABLE`
- 제목: `최종 결과물 확인 불가`
- 상태 badge: `근거 부족`, `후보 여러 개`, `근거 충돌`, `확인 불가` 중 하나
- primary CTA 없음
- 이유 한 문장
- 근거 요약 필드
- `일반 Artifacts에서 후보 확인` 안내
- 후보 개수만 표시하고 첫 파일을 기본 선택하지 않음

### 4.4 UI copy 규칙

좋은 문구:

- `최종 작성 결과와 artifact 연결이 확인되었습니다.`
- `최종 작성은 생략되었으며 writing 산출물이 검증·PM review와 동일 artifact로 연결되었습니다.`
- `writing 결과는 있으나 검증과 PM review가 특정 artifact에 연결되지 않았습니다.`
- `후보가 여러 개여서 최종 결과물을 확인할 수 없습니다.`

금지 문구:

- `가장 최신 최종본`
- `마지막 파일`
- `최종 승인 완료` — binding 없이 사용 금지
- `검증 완료` — verification stage completed만으로 사용 금지
- `최종본으로 보임`

### 4.5 시각 우선순위

- confirmed: 강조 border와 아이콘을 사용할 수 있으나 성공색만으로 의미를 전달하지 않는다.
- unavailable/ambiguous/conflict: 경고색과 텍스트/아이콘을 함께 사용한다.
- 일반 Artifacts 패널보다 시각적 우선순위는 높지만 Outcome 제목을 압도하는 과도한 hero 크기는 피한다.
- 긴 파일명과 id는 줄바꿈 가능해야 한다.

### 4.6 읽기 전용 제약

Final Deliverable 영역에서 금지:

- 최종본 지정
- 승인/override
- 재전송
- gate 변경
- stage 상태 변경
- artifact 삭제·이동·rename
- review 수정

---

## 5. 일반 Artifacts / Verification 영역과의 관계

### 5.1 분리 원칙

- Final Deliverable: 최종 전달본 판정 결과와 근거
- Artifacts: task에 안전하게 귀속된 일반 결과 및 후보
- Verification: 검증 결과, verdict, target binding

세 영역은 같은 파일을 참조할 수 있으나 의미는 다르다.

### 5.2 중복 표시

- confirmed artifact는 Final Deliverable에 대표 표시한다.
- 동일 파일이 일반 Artifacts에도 존재할 수 있다. 이때 `최종 전달본` badge를 붙일 수 있다.
- 중복을 제거해 일반 근거를 숨기지 않는다.
- unconfirmed 후보에는 `후보` badge를 붙일 수 있으나 `최종` badge는 금지한다.

### 5.3 일반 Artifacts ordering

1. confirmed final artifact
2. 동일 active deliverable bundle의 관련 파일
3. active 다른 stage bundle
4. historical attempt
5. unlinked/ambiguous evidence

단, ordering은 표시 편의일 뿐 판정 근거가 아니다. historical과 unlinked는 별도 label을 가져야 한다.

### 5.4 Verification 표시

각 verification item은 가능한 경우 다음을 표시한다.

- verdict/status
- 대상 artifact id/version
- target match: matched/unbound/mismatch
- source envelope
- stage raw status

verification 파일이 `operations/results`에 존재하는 현재 구조도 지원한다. 디렉터리만으로 verification 여부를 판단하지 않는다.

### 5.5 대표 사례 표시

`T-20260729-001`:

- Final Deliverable: 확인 불가 / binding insufficient
- Artifacts: active writing report와 HTML 후보를 일반 결과로 표시
- Verification: verify-co 결과 도착, 특정 HTML binding 확인 불가
- PM review: meets record 있음, artifact binding 확인 불가

---

## 6. Viewer modal 전면 / stack / focus / keyboard UX

### 6.1 핵심 원칙

Artifact viewer는 nested child modal처럼 보이더라도 DOM과 z-index 기준으로 항상 현재 최상위 interaction layer다. task detail을 숨기거나 닫지 않고 그 앞에 렌더링한다.

### 6.2 권고 구조

- `briefModal`: base modal layer
- `taskDetailModal`: task detail layer
- `artifactViewerModal`: top viewer layer
- 모든 modal은 `document.body` 직계 자식 또는 전용 portal root 아래 위치
- z-index token을 이름으로 분리

예시 token:

- `--z-modal-base: 1000`
- `--z-modal-task-detail: 1100`
- `--z-modal-artifact-viewer: 1200`
- `--z-toast: 1300`

단순히 DOM 순서에 의존하지 않는다. artifact viewer backdrop도 task detail panel보다 앞에 있어야 한다.

### 6.3 viewer open

모든 진입점은 `openArtifactViewer({dir, name, trigger, context})` 하나를 사용한다.

- trigger를 return focus 대상으로 저장
- 현재 열린 layer stack을 확인
- artifact URL을 allowlisted dir/name으로 생성
- title/kicker/download/new-tab 설정
- HTML은 sandboxed iframe, text/json은 안전한 text rendering
- viewer를 top layer로 표시
- body scroll lock reference count 증가
- 초기 포커스를 viewer 닫기 버튼으로 이동
- task detail은 시각적으로 뒤에 유지하되 `aria-hidden` 또는 `inert`로 interaction 차단

### 6.4 viewer close

- iframe `src` 또는 body 내용을 제거해 재생/로드를 중단
- viewer를 hidden 처리
- body scroll lock reference count 감소
- 부모 task detail이 남아 있으면 그 modal의 inert/aria 상태 복구
- 저장된 trigger가 DOM에 연결되어 있고 focus 가능하면 focus 복원
- trigger가 사라졌으면 부모 modal의 닫기 버튼 또는 heading에 fallback focus

### 6.5 Escape

Escape handler는 topmost open layer 하나만 닫는다.

우선순위:

1. artifact viewer
2. task detail
3. brief modal
4. 기타 detail

규칙:

- artifact viewer가 열려 있으면 Escape는 viewer만 닫는다.
- 같은 이벤트가 부모 close handler로 전파되어 task detail까지 닫히지 않게 한다.
- IME composition 중 Escape를 임의 submit/cancel로 처리하지 않는다.
- iframe에 focus가 있을 때도 가능한 범위에서 parent listener가 Escape를 처리한다. cross-origin iframe은 직접 key capture를 보장할 수 없으므로 항상 보이는 닫기 버튼을 제공한다.

### 6.6 focus trap

- Tab/Shift+Tab은 topmost modal 내부 focusable element 사이를 순환한다.
- 뒤의 task detail/brief/page는 `inert` 처리한다.
- `aria-modal=true`, 고유 `aria-labelledby`, 필요 시 `aria-describedby`를 사용한다.
- iframe은 하나의 focusable stop으로 취급한다.
- modal close 후 return focus를 보장한다.
- 자동 새로고침으로 trigger가 교체되는 동안 viewer가 열려 있다면, stable artifact key 기반 fallback focus를 사용한다.

### 6.7 backdrop

- viewer backdrop 클릭은 viewer만 닫는다.
- backdrop pointer event가 부모 task detail backdrop에 전달되지 않는다.
- panel 내부 클릭은 닫기로 처리하지 않는다.
- accidental close가 데이터 손실을 만들지는 않지만 일관된 stack semantics를 유지한다.

### 6.8 scroll lock

- `body.modal-open` 단일 boolean 대신 열린 modal 수 또는 top-layer 상태로 계산한다.
- task detail 단독, viewer 단독, task detail+viewer 모두 body background를 잠근다.
- viewer panel/body만 스크롤한다.
- close 순서에 따라 아직 부모 modal이 열려 있으면 scroll lock을 제거하지 않는다.
- scrollbar 보정으로 layout shift를 최소화한다.

### 6.9 작은 viewport

- 767px 이하: viewer width/height `100dvw/100dvh`에 가까운 전면 layout
- safe-area inset 반영
- header action은 wrap 또는 sticky header
- 콘텐츠 영역 `min-height: 0`, `overflow: auto`
- iframe 최소 높이를 고정 pixel로 두지 않고 가용 공간을 채움
- 파일명은 wrap, action target은 최소 44×44 CSS px
- landscape mobile에서도 닫기 버튼이 viewport 밖으로 밀리지 않음

### 6.10 iframe 보안

현행 `sandbox="allow-downloads"`, `referrerpolicy="no-referrer"`를 기본 유지한다.

- `allow-scripts`, `allow-same-origin`, `allow-forms`, `allow-popups`는 요구 근거와 보안 검토 없이 추가 금지
- 서버는 allowlisted `results/verifications/digests`와 basename validation을 유지
- HTML 내부 링크 동작은 sandbox 정책에 따름
- 로드 실패 시 blank frame 대신 오류 메시지와 다운로드/새 탭 대안을 제공

---

## 7. API / Projection 계약과 Raw Evidence Mapping

### 7.1 호환 원칙

- 기존 `/api/tasks`, `/api/results`, `/api/verifications`, `/files/...`, `/detail.html`을 유지한다.
- 기존 필드 의미를 변경하지 않는다.
- `/api/tasks` 각 task의 `dashboard_projection`에 additive field를 추가한다.
- 구버전 UI는 새 field를 무시해도 동작해야 한다.
- 새 UI는 field가 없으면 클라이언트에서 final을 긍정 추정하지 않고 `확인 불가` fallback을 표시한다.

### 7.2 제안 projection

```json
{
  "schema_version": 2,
  "final_deliverable": {
    "state": "confirmed|candidate_unconfirmed|ambiguous|conflict|unavailable|unknown",
    "reason_code": "binding_insufficient",
    "label": "최종 결과물 확인 불가",
    "source_mode": "final_write|skipped_final_write_fallback|no_final_write_pipeline|unresolved",
    "deliverable_stage": {
      "id": "writing",
      "raw_status": "completed",
      "derived_task_id": "T-20260729-001-writing-r1"
    },
    "artifact": null,
    "candidates": [
      {
        "name": "example.html",
        "dir": "results",
        "artifact_id": null,
        "version": null,
        "bundle_key": "writing::writer-co",
        "classification": "candidate"
      }
    ],
    "verification": {
      "state": "result_received_unbound",
      "artifact_id": null,
      "version": null,
      "matched": false
    },
    "pm_final_review": {
      "state": "review_recorded_unbound",
      "verdict": "meets",
      "artifact_id": null,
      "version": null,
      "matched": false
    },
    "evidence": [],
    "limitations": []
  }
}
```

### 7.3 artifact object

confirmed일 때만 `artifact`를 채운다.

필드:

- `name`: allowlisted 파일명
- `dir`: `results|verifications` 등 허용 enum. final deliverable은 원칙적으로 results
- `artifact_id`: explicit id 또는 null
- `version`: explicit version 또는 null
- `media_type`: `html|markdown|json|text|unknown`
- `bundle_key`
- `source_envelope`
- `openable`: server allowlist와 파일 존재 확인 결과

path 전체 문자열은 클라이언트 신뢰 근거로 사용하지 않는다.

### 7.4 evidence row

각 evidence row:

- `source_type`: task_raw/stage_raw/result_envelope/verification_envelope/pm_final_review
- `source_id`
- `field`
- `raw_value`
- `scope`
- `binding_target`
- `confidence`: direct/ambiguous/unavailable
- `observed_at` 또는 canonical `at`

UI 기본 화면에는 요약만 표시하고 disclosure에서 raw evidence를 본다.

### 7.5 raw evidence mapping

| Projection | Canonical raw | 긍정 판정 조건 | 금지 대체 근거 |
|---|---|---|---|
| deliverable stage | task.stages + pipeline_shape | explicit stage id/status/skipped | 파일명 suffix만 사용 |
| active attempt | stage.derived_task_id | exact envelope task_id match | prefix/mtime |
| result received | result envelope | expected worker + completed + report 존재 | report 파일 존재만 |
| artifact identity | envelope id/version/report binding | allowlisted file exact match | artifacts 배열 첫 항목 |
| verification | verification/result envelope | verdict/status + artifact binding | verification stage completed만 |
| PM review | task.pm_final_review | verdict + artifact id/version binding | comment 자유 텍스트 |
| version | artifact_version/result_version | explicit value | 파일명 timestamp/mtime/r1 |
| openable | server file inventory | allowlisted dir + exact name exists | raw absolute path |

### 7.6 server safe metadata 확장

현재 `result_metadata()` safe set은 `artifact_id`, `artifact_version`, `result_artifact_id`, `result_version`을 포함한다. 다음을 additive 검토한다.

- primary artifact identity를 raw envelope가 제공하는 경우 해당 필드 유지
- `artifacts[]` 전체 path를 그대로 노출하지 않음
- 필요 시 정규화된 `artifact_refs[]`를 server가 basename + allowlisted existence로 생성
- role이 명시된 경우에만 `role=primary|supporting` 노출
- raw에 role이 없으면 server가 primary를 추정하지 않음

### 7.7 대표 사례 기대 projection

`T-20260729-001` 기대값:

- state: `ambiguous`
- label: `최종 결과물 확인 불가`
- source_mode: `skipped_final_write_fallback`
- deliverable_stage.id: `writing`
- raw_status: `completed`
- derived_task_id: `T-20260729-001-writing-r1`
- artifact: null
- verification.state: `result_received_unbound`
- pm_final_review.state: `review_recorded_unbound`
- reason_code: `multiple_equal_candidates`
- limitations: `binding_insufficient` 포함

projection test는 어느 HTML 파일도 `artifact`로 선택되지 않았음을 명시적으로 검증한다.

---

## 8. 구현 Slice / 파일 후보 / Release Plan

### 8.1 Slice 0 — 기준선·fixture 고정

목적: 현재 working tree의 다른 변경과 섞이지 않게 final-viewer 범위를 고정한다.

작업:

- `T-20260729-001` fixture 또는 최소 재현 fixture 작성
- current same-z-index/DOM-order 증거 test 고정
- 기존 API response snapshot 또는 contract test 보강
- 다른 미검증 sync/watchdog 변경과 diff 분리

완료 조건:

- 현행 false-positive 방지 test와 viewer-behind 재현 test가 먼저 실패
- 기존 승인 기능 범위를 침범하지 않음

### 8.2 Slice 1 — Projection

파일 후보:

- `operations_dashboard_projection.py`
- `operations_dashboard_server.py`
- `tests/test_dashboard_projection.py`
- 필요 시 server contract test

작업:

- pure function `project_final_deliverable()` 추가
- `project_task()`에 additive `final_deliverable`
- exact active envelope와 binding 판정
- missing/null/unknown/conflict fixture
- `T-20260729-001` skipped 사례

완료 조건:

- Rule A/Rule B/state/reason code test 통과
- 기존 projection 필드 회귀 없음

### 8.3 Slice 2 — Final Deliverable UI

파일 후보:

- `operations_dashboard/app.js`
- `operations_dashboard/styles.css`
- `tests/test_dashboard_static_contract.py`

작업:

- `renderFinalDeliverable(task, projection)` 추가
- task detail 첫 section으로 배치
- confirmed/unavailable/ambiguous/conflict copy
- 일반 Artifacts/Verification과 관계 표시
- 카드에는 write control을 추가하지 않음

완료 조건:

- task detail section order contract 통과
- confirmed가 아닌 경우 primary open CTA 없음
- 대표 fixture에 `최종 결과물 확인 불가` 표시

### 8.4 Slice 3 — Viewer stack coordinator

파일 후보:

- `operations_dashboard/index.html`
- `operations_dashboard/app.js`
- `operations_dashboard/styles.css`
- 필요 시 `operations_dashboard/detail.html`
- interaction/browser QA script

작업:

- `artifactViewerModal` 또는 기존 detailModal의 명확한 top-layer 승격
- 모든 artifact click을 `openArtifactViewer()`로 통합
- modal stack/topmost Escape
- focus trap/return focus/inert
- reference-counted scroll lock
- mobile full-screen layout

완료 조건:

- task detail에서 artifact open 시 viewer가 computed z-index와 hit test 기준 앞에 있음
- Escape 첫 회는 viewer만, 둘째 회는 task detail을 닫음
- focus restoration 성공

### 8.5 Slice 4 — QA와 배포

- projection unit test
- static DOM contract
- browser interaction matrix
- accessibility keyboard/screen-reader smoke
- security sandbox regression
- rollback rehearsal

배포 단위는 projection/UI/viewer를 순차적으로 켤 수 있게 한다. additive projection은 UI보다 먼저 배포 가능하다.

### 8.6 Rollback

- UI rollback 시 새 projection은 남아도 구버전 UI가 무시한다.
- viewer stack 문제가 있으면 Final Deliverable 영역의 CTA를 비활성화하고 기존 새 탭/다운로드 대안을 유지한다.
- projection 문제가 있으면 클라이언트가 final을 추정하지 않고 `확인 불가`로 내린다.
- rollback이 raw task/result/PM review를 수정해서는 안 된다.

---

## 9. Acceptance Criteria

### 9.1 Final 판정

- [ ] AC-F01 final_write completed + exact active envelope + unique explicit artifact identity이면 `confirmed`다.
- [ ] AC-F02 final_write completed라도 active envelope를 exact match하지 못하면 confirmed가 아니다.
- [ ] AC-F03 final_write skipped이면 completed deliverable stage, exact active result, verification binding, PM review binding을 모두 검사한다.
- [ ] AC-F04 skipped fallback에서 verification 또는 PM review가 unbound이면 `최종 결과물 확인 불가`다.
- [ ] AC-F05 둘 이상의 동등 후보가 있으면 배열 첫 항목, mtime, 파일명으로 선택하지 않는다.
- [ ] AC-F06 verification과 PM review가 다른 artifact/version을 가리키면 `conflict`다.
- [ ] AC-F07 active hold 또는 PM review `not_meets`는 confirmed를 차단한다.
- [ ] AC-F08 missing/null/unknown raw 값은 fail-safe 상태로 내려간다.
- [ ] AC-F09 version이 없으면 `버전 확인 불가`를 표시하고 version을 생성하지 않는다.
- [ ] AC-F10 verification stage completed만으로 `검증됨`을 표시하지 않는다.

### 9.2 대표 사례

- [ ] AC-R01 `T-20260729-001`에서 final_write skipped, writing completed, verification completed, PM review meets를 각각 표시한다.
- [ ] AC-R02 PM review와 verification의 artifact binding 부재를 표시한다.
- [ ] AC-R03 `...130629.html` 또는 `...165206.html` 어느 것도 임의 final로 선택하지 않는다.
- [ ] AC-R04 task detail 상단에 `최종 결과물 확인 불가`와 reason을 표시한다.
- [ ] AC-R05 일반 Artifacts에서는 writing/verification 후보를 읽기 전용으로 열 수 있다.

### 9.3 Task detail UI

- [ ] AC-U01 Final Deliverable section은 task detail body의 첫 section이다.
- [ ] AC-U02 confirmed 상태는 근거 stage/version/status/verification/PM review를 별도 필드로 표시한다.
- [ ] AC-U03 unconfirmed 상태는 final CTA를 노출하지 않는다.
- [ ] AC-U04 일반 Artifacts와 Verification은 Final Deliverable 아래에서 독립 유지된다.
- [ ] AC-U05 카드에는 final 지정, 승인, 재전송 등 write control이 없다.
- [ ] AC-U06 긴 파일명/id는 320px CSS viewport에서도 잘리지 않고 wrap된다.

### 9.4 Viewer stack와 접근성

- [ ] AC-V01 overview, Final Deliverable, 일반 Artifacts, Verification의 모든 클릭은 같은 viewer coordinator를 사용한다.
- [ ] AC-V02 task detail에서 artifact 클릭 시 viewer panel/backdrop은 task detail보다 앞에 렌더링된다.
- [ ] AC-V03 viewer가 열린 동안 뒤의 task detail은 pointer/keyboard interaction이 불가능하다.
- [ ] AC-V04 Escape 1회는 topmost viewer만 닫고 task detail을 유지한다.
- [ ] AC-V05 Escape를 다시 누르면 task detail이 닫힌다.
- [ ] AC-V06 viewer 닫기 버튼과 backdrop도 viewer만 닫는다.
- [ ] AC-V07 viewer close 후 원래 artifact trigger로 포커스가 복원된다.
- [ ] AC-V08 trigger가 사라진 경우 부모 modal의 안전한 fallback으로 포커스가 이동한다.
- [ ] AC-V09 Tab/Shift+Tab은 topmost modal 내부에서 순환한다.
- [ ] AC-V10 task detail 단독 및 task detail+viewer 모두 body background scroll이 잠긴다.
- [ ] AC-V11 viewer를 닫아도 task detail이 남아 있으면 scroll lock이 유지된다.
- [ ] AC-V12 390×844에서 viewer header, 닫기, 본문 스크롤이 정상 동작한다.
- [ ] AC-V13 HTML iframe은 기존 sandbox/referrer policy를 약화하지 않는다.
- [ ] AC-V14 파일 load 실패 시 오류와 다운로드/새 탭 대안을 제공한다.

### 9.5 API / 회귀

- [ ] AC-A01 기존 endpoint와 기존 response field를 제거·재정의하지 않는다.
- [ ] AC-A02 새 `final_deliverable`은 additive다.
- [ ] AC-A03 projection 누락 시 새 UI는 final을 추정하지 않는다.
- [ ] AC-A04 raw absolute path를 client route로 직접 신뢰하지 않는다.
- [ ] AC-A05 기존 projection/server/static unit test가 통과한다.
- [ ] AC-A06 기존 result/verification/detail viewer 진입점이 모두 동작한다.
- [ ] AC-A07 Dashboard 동작으로 canonical card/task/stage/review 파일이 변경되지 않는다.

---

## 10. 브라우저 / 접근성 / 회귀 QA 매트릭스

| ID | 영역 | 환경 | 절차 | 기대 결과 | 증거 |
|---|---|---|---|---|---|
| QA-01 | confirmed final | Chromium 1440 | Rule A fixture detail 열기 | 상단 final, 근거, CTA 표시 | screenshot + projection JSON |
| QA-02 | skipped fallback | Chromium 1440 | binding 완전 fixture | writing final confirmed | screenshot + unit test |
| QA-03 | 대표 사례 | Chromium 1440 | T-20260729-001 detail | 확인 불가, 두 HTML 미선택 | screenshot + DOM text |
| QA-04 | ambiguity | Firefox 1440 | 동등 후보 2개 fixture | ambiguous, CTA 없음 | screenshot |
| QA-05 | conflict | WebKit 1440 | verify v1/review v2 | conflict copy | screenshot |
| QA-06 | stack | Chromium 1440 | task detail→artifact | viewer가 hit-test상 top | computed style + screenshot |
| QA-07 | Escape | Chromium 1440 | task detail→viewer→Esc→Esc | viewer만, 이후 task detail | interaction trace |
| QA-08 | return focus | Firefox 1440 | artifact 클릭→닫기 | trigger focus 복원 | activeElement 기록 |
| QA-09 | focus trap | Chromium keyboard | Tab/Shift+Tab 반복 | viewer 밖 이동 없음 | focus trace |
| QA-10 | backdrop | Chromium | viewer backdrop 클릭 | viewer만 닫힘 | state trace |
| QA-11 | scroll lock | Chromium | detail+viewer open/close | 부모가 열려 있으면 lock 유지 | body class/style 기록 |
| QA-12 | mobile | Chromium 390×844 | HTML viewer 열기 | full-screen, header/action 보임 | screenshot |
| QA-13 | tablet | Chromium 768×1024 | 긴 파일명 viewer | wrap, overflow 없음 | screenshot |
| QA-14 | zoom | Chromium 200% | viewer action 사용 | close/download 접근 가능 | screenshot |
| QA-15 | screen reader | NVDA+Chromium | dialog title 탐색 | viewer title/description 발표 | 수동 기록 |
| QA-16 | reduced motion | Chromium | prefers-reduced-motion | 필수 동작에 animation 의존 없음 | devtools 기록 |
| QA-17 | iframe sandbox | Chromium | script/form 포함 fixture | script/form 권한 확대 없음 | console/network 기록 |
| QA-18 | load error | Chromium | 삭제된 fixture name | 오류+대체 action | screenshot |
| QA-19 | API compatibility | Python tests | 기존 tests 실행 | all pass | test log |
| QA-20 | read-only | filesystem diff | viewer flow 전후 비교 | canonical operations 변경 없음 | hash/diff |
| QA-21 | auto refresh | Chromium | viewer 열린 채 refresh tick | viewer/return focus 안정 | interaction trace |
| QA-22 | duplicate ids | static/a11y | 전체 DOM 검사 | dialog label id 유일 | axe/static test |
| QA-23 | deep entry | Chromium | overview artifact tile 클릭 | 동일 viewer coordinator | instrumentation |
| QA-24 | verification entry | Chromium | verification file 클릭 | 동일 top viewer | screenshot |

필수 release gate:

- Chromium QA-01~14, 17~24 전부 통과
- Firefox QA-04, 08 통과
- WebKit QA-05 및 mobile smoke 통과
- NVDA QA-15 통과 또는 접근성 reviewer의 동등 검증
- false-positive final 0건

---

## 11. 리스크 / 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| 기존 envelope에 artifact binding 부족 | 많은 task가 확인 불가로 보임 | 정직한 unavailable 표시, 후속 producer schema 개선 |
| `artifacts[]`에 절대 경로만 존재 | client route 연결 취약 | server에서 allowlisted basename ref 정규화 |
| 같은 파일의 MD/HTML 쌍 | 후보 수 과다 | explicit role/primary artifact schema 없으면 final 추정 금지 |
| verification이 results 디렉터리에 저장 | directory-only 로직 오판 | stage/envelope worker/binding 기준 사용 |
| PM review unbound | 긍정 verdict가 final처럼 보일 위험 | review_recorded_unbound 별도 상태 |
| 여러 modal 구현이 분산 | Escape/focus 회귀 | 단일 modal stack coordinator |
| iframe focus | Escape capture 제한 | 항상 보이는 close, parent focus semantics, sandbox 유지 |
| auto refresh가 trigger DOM 교체 | return focus 실패 | stable key fallback + 부모 modal fallback |
| z-index 숫자 추가 경쟁 | 다시 뒤로 숨음 | named token + computed stack browser test |
| 다른 working-tree 변경과 혼합 | 원인·rollback 불명확 | slice/commit 분리, 독립 QA |

---

## 12. 가정

1. raw task/stage/result envelope/PM final review가 canonical source다.
2. Dashboard server는 결과 파일 존재와 allowlisted basename을 확인할 수 있다.
3. artifact producer가 향후 artifact id/version/role을 추가할 수 있다.
4. current Dashboard는 local/read-only artifact viewing을 유지한다.
5. HTML 미리보기의 제한된 sandbox가 사용자 요구를 충족한다.
6. 기존 API 소비자는 additive projection field를 허용한다.
7. `T-20260729-001`의 두 HTML 중 실제 최종 전달본은 현재 canonical binding만으로 확정할 수 없다.

---

## 13. 미결 질문

### P0 — 구현 전 결정

1. final_write completed Rule A에서 verification/PM binding 없이도 explicit final_write artifact를 confirmed로 볼 것인가? 본 PRD 권고는 **예**다. final_write 자체가 최종 생산 stage이기 때문이다.
2. result envelope `report_file`이 MD이고 `artifacts[]`에 HTML이 있을 때 primary deliverable role을 producer schema에 추가할 것인가?
3. viewer를 기존 `detailModal` 승격으로 구현할지 `artifactViewerModal`로 분리할지? 권고는 의미와 test hook이 명확한 별도 id 또는 기존 id의 완전한 rename/migration이다.
4. modal background 제어에 native `inert`를 쓸 수 없는 목표 브라우저가 있는가?

### P1 — 후속 개선

5. artifact version을 누가 생성하고 immutable하게 보장하는가?
6. verification verdict enum을 standardize할 것인가?
7. PM final review 작성 시 artifact binding을 필수화할 것인가?
8. historical task에 binding backfill 도구를 만들 것인가? Dashboard 자동 추정은 금지한다.
9. Markdown 전용 결과의 viewer rendering을 plain text로 유지할지 sanitized HTML로 개선할지?

---

## 14. 후속 카드 명세

### 14.1 Developer 카드

제목: `DEV-V11-2A: additive final_deliverable projection과 Final Deliverable UI 구현`

담당: `developer`

범위:

- pure projection/state/reason code 구현
- `T-20260729-001` fixture
- task detail 최상단 Final Deliverable
- 일반 Artifacts/Verification 관계 표시
- 기존 API 호환 및 read-only 유지

완료 기준:

- AC-F01~F10, AC-R01~R05, AC-U01~U06, AC-A01~A07
- 관련 unit/static tests 통과
- 변경 파일과 test log handoff

### 14.2 Developer 카드

제목: `DEV-V11-2B: artifact viewer top-layer modal stack·focus·keyboard 구현`

담당: `developer`

선행: DEV-V11-2A

범위:

- 단일 viewer coordinator
- named z-index tokens
- topmost Escape
- focus trap/return focus/inert
- reference-counted scroll lock
- mobile full-screen viewer
- iframe sandbox 회귀 방지

완료 기준:

- AC-V01~V14
- browser automation 증거
- canonical operations 파일 무변경 증거

### 14.3 Verifier 카드

제목: `VERIFY-V11-2: final artifact 판정·API·read-only 회귀 검토`

담당: `verifier`

선행: DEV-V11-2A, DEV-V11-2B

범위:

- PRD 대 구현 gap review
- false-positive final red-team
- raw binding/API compatibility 확인
- sandbox/path traversal/read-only 검토
- release blocker 분류

완료 기준:

- AC 전체 pass/fail/evidence 표
- blocker/major/minor 구분
- 승인 또는 재작업 권고

### 14.4 QA 카드

제목: `QA-V11-2: 전면 artifact viewer 브라우저·접근성·회귀 매트릭스 실행`

담당: `qa`

선행: VERIFY-V11-2 또는 검증 가능한 개발 candidate

범위:

- QA-01~QA-24
- Chromium/Firefox/WebKit, 390/768/1440
- keyboard, Escape, focus restoration, scroll lock
- T-20260729-001 화면 증거
- filesystem read-only diff

완료 기준:

- matrix별 실제 결과와 evidence 경로
- strict release verdict
- 재현 가능한 blocker 보고

### 14.5 PM 카드

제목: `PM-V11-2: artifact identity/version/binding producer contract 결정`

담당: `pm`

범위:

- primary artifact role
- version 생성 주체
- verification/PM review binding 필수화 시점
- historical backfill 정책

완료 기준:

- P0 미결 질문 결정
- producer schema 후속 범위 확정

---

## 15. 의사결정과 근거

1. **확인 불가를 정상 제품 상태로 둔다.** 잘못된 최종본을 보여주는 것보다 사용자가 일반 후보를 직접 확인하게 하는 편이 안전하다.
2. **final_write completed와 skipped fallback을 다른 규칙으로 평가한다.** final_write는 명시적 최종 생산 stage이고, skipped fallback은 검증·PM review binding이 추가로 필요하다.
3. **Final Deliverable과 일반 Artifacts를 분리하되 일반 근거를 숨기지 않는다.** 빠른 접근과 감사 가능성을 동시에 유지한다.
4. **viewer stack을 DOM 순서가 아닌 명시적 layer token과 coordinator로 관리한다.** 현재 동일 z-index 결함의 재발을 막는다.
5. **Escape는 topmost layer 하나만 닫는다.** nested context와 사용자의 위치를 보존한다.
6. **API는 additive projection으로 확장한다.** 기존 소비자와 endpoint를 깨지 않는다.

---

## 16. Acceptance Criteria 체크리스트 요약

- [x] 문제·사용자 시나리오·목표·비목표 정의
- [x] final artifact 판정·근거·모호성 상태 모델 정의
- [x] task detail 상단 Final Deliverable 영역 요구사항 정의
- [x] 일반 Artifacts/Verification과의 관계 정의
- [x] viewer 전면/stack/focus/keyboard/backdrop/scroll lock 요구사항 정의
- [x] API/projection과 raw evidence mapping 정의
- [x] 구현 slice·파일 후보·acceptance criteria 정의
- [x] 브라우저/접근성/회귀 QA matrix 정의
- [x] 위험·가정·미결 질문 정의
- [x] developer/verifier/QA/PM 후속 카드 명세 정의
- [x] `T-20260729-001` final_write skipped 사례를 false-positive 없이 설명

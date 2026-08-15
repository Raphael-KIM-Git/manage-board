# Agent Hub Dashboard v1.1 — Artifact Producer Contract 결정서

- 문서 상태: PM 결정 · 개발/검증 handoff용
- 제품 범위: Raphael Agent Hub Dashboard-only v1.1
- 기준 PRD: `Agent-Hub-Dashboard-v1.1-final-artifact-viewer-PRD-ko.md` §3, §13
- 적용 시작: 새 producer schema를 채택하는 신규 deliverable/verification/PM review 레코드부터
- 비목표: Dashboard가 과거 파일명·mtime·배열 순서로 artifact를 추정하거나 canonical 기록을 자동 수정하는 것

## 1. 결정 요약

| 항목 | 결정 |
|---|---|
| primary artifact | deliverable producer는 사용자 전달본이 있는 경우 정확히 하나의 `primary_deliverable` role을 명시한다. `report_file`이나 `artifacts[]` 순서는 role을 대체하지 않는다. |
| artifact identity | `artifact_id`는 하나의 논리 artifact 계열을 식별하는 producer 발급 불변 ID다. |
| artifact version | `artifact_version`은 `artifact_id` 아래 특정 바이트 내용을 가리키는 불변 version ID이며, content SHA-256으로 무결성을 함께 고정한다. 파일명·mtime·`r1` suffix는 version이 아니다. |
| final_write 완료 | active, completed, non-skipped `final_write` bundle이 explicit primary artifact identity를 제공하고 해당 allowlisted 파일과 digest가 일치하면 confirmed 가능하다. 별도 verification/PM binding은 요구하지 않는다. |
| skipped/no-final-write fallback | verification과 PM final review가 모두 같은 `(artifact_id, artifact_version)`을 명시적으로 bind하고 긍정 verdict이며 hold/conflict가 없을 때만 confirmed다. |
| verification binding | verification verdict가 artifact 품질 판정으로 사용되려면 대상 `(artifact_id, artifact_version)`이 필수다. 미결합 verification은 정보성 report일 뿐 final 판정 근거가 아니다. |
| PM review binding | 신규 PM final review는 review 대상이 artifact인 경우 `(artifact_id, artifact_version)`을 필수로 기록한다. 특히 skipped/no-final-write fallback에서는 긍정 review의 binding 없이는 final confirmed가 될 수 없다. |
| historical backfill | 자동 추정 금지. 별도 append-only adjudication/migration만 허용하며 충분한 원본 증거가 없으면 `unconfirmed`를 유지한다. |

## 2. Producer schema v2

### 2.1 deliverable result envelope의 필수 확장

기존 exact result envelope의 task/stage/worker/status/report-file 검증은 유지한다. 신규 deliverable producer는 아래 `artifact_manifest`를 result envelope에 추가한다.

```json
{
  "artifact_schema_version": 2,
  "artifact_manifest": {
    "primary_artifact_id": "art_01J...",
    "primary_artifact_version": "sha256:lowercase-hex",
    "artifacts": [
      {
        "artifact_id": "art_01J...",
        "artifact_version": "sha256:lowercase-hex",
        "role": "primary_deliverable",
        "file_name": "T-...__writer-co.html",
        "media_type": "text/html",
        "content_sha256": "lowercase-hex"
      }
    ]
  }
}
```

필드 규칙:

1. `artifact_schema_version`은 정수 `2`다.
2. `artifact_id`는 producer가 생성한 opaque 문자열이다. 한 논리 deliverable의 후속 편집본은 같은 ID를 유지할 수 있지만, 서로 다른 deliverable은 ID를 재사용하면 안 된다.
3. `artifact_version`은 정확한 content version을 식별하는 immutable value다. v2에서는 `sha256:<content_sha256>` 형식을 표준으로 한다. `content_sha256`은 파일의 실제 바이트 SHA-256(소문자 64자리 hex)이어야 한다.
4. `file_name`은 result directory의 allowlisted basename만 허용한다. absolute path, URL, symlink, path traversal은 허용하지 않는다.
5. `role` enum은 `primary_deliverable`, `supporting`, `source`, `verification_report`만 허용한다. 사용자에게 전달할 최종 후보는 `primary_deliverable`만 가능하다.
6. `primary_artifact_id`와 `primary_artifact_version`은 정확히 하나의 `artifacts[]` item과 완전히 일치해야 한다. 그 item의 role은 반드시 `primary_deliverable`이다.
7. deliverable stage의 completed active bundle에는 `primary_deliverable`이 정확히 1개여야 한다. 0개 또는 2개 이상이면 malformed/ambiguous이며 Dashboard는 어느 파일도 승격하지 않는다.
8. `report_file`은 worker report이지 primary artifact의 암시적 별칭이 아니다. 다만 전환기 legacy Rule A 호환에서만 §6의 제한적 규칙을 적용한다.

### 2.2 생성 책임과 불변성

- **생성 주체:** artifact 파일을 실제 작성·정리하는 deliverable stage producer(`final_write`, `writing`, `research`의 담당 worker)가 manifest와 digest를 생성한다. Dashboard, projection, viewer, verifier, PM은 artifact id/version을 새로 만들어서는 안 된다.
- **발급 시점:** artifact 파일을 final location에 쓴 뒤 바이트 digest를 계산하고, 그 결과를 result envelope와 함께 한 번 발급한다.
- **불변성:** 발급 뒤 동일 `(artifact_id, artifact_version)`의 파일 내용, file_name, media_type, digest, role은 변경 금지다. 수정 시 새 파일과 새 `artifact_version`을 발급한다. 동일 논리 deliverable의 개정이면 `artifact_id`는 유지 가능하지만 version은 반드시 바뀐다.
- **원자성:** result envelope가 completed로 공개되기 전에 artifact 파일·manifest가 모두 존재해야 한다. 파일 또는 digest 검증 실패 시 envelope는 final candidate가 아니며 producer는 새 attempt/version으로 재발급한다.
- **재시도:** 같은 worker/stage의 재시도는 새 derived task/attempt를 사용한다. active derived task와 exact-match하지 않는 과거 bundle은 history이며 Final Deliverable 후보가 아니다.

## 3. Binding contract

### 3.1 공통 target 형식

verification 및 PM final review는 artifact 대상이 있을 때 동일한 object를 사용한다.

```json
{
  "target_artifact": {
    "artifact_id": "art_01J...",
    "artifact_version": "sha256:lowercase-hex"
  }
}
```

- `artifact_id`와 `artifact_version`은 함께 있어야 한다. 하나만 있는 partial binding은 final 판정용으로 무효다.
- target은 active deliverable bundle의 `primary_deliverable` item과 exact match해야 한다.
- `file_name`, report filename, natural-language comment만으로 target을 대체할 수 없다.
- binding target이 존재하지 않거나 digest 검증에 실패하면 `binding_mismatch`이며 confirmed를 차단한다.

### 3.2 verification record

새 verification result envelope은 `verdict`와 `target_artifact`를 함께 제공해야 artifact-specific verification으로 분류된다.

- positive enum은 v1.1에서 `verified`, `passed`, `meets`, `complete`, `completed`를 허용하되, producer 표준 출력은 `passed|failed|inconclusive`로 수렴한다.
- `failed` 또는 `inconclusive`, active hold, 다른 target으로의 binding은 confirmed를 차단한다.
- target 없이 완료된 verification은 `verification_recorded_unbound`로 노출할 수 있으나 Final Deliverable의 strong evidence가 아니다.
- 하나의 verification report가 여러 artifact를 다루면 각 target별 verdict를 배열로 기록해야 한다. fallback confirmed에 쓰이는 positive binding은 정확히 하나의 primary target에 대해 판정 가능해야 한다.

### 3.3 PM final review record

`pm_final_review`는 아래를 추가한다.

```json
{
  "verdict": "meets|partial|not_meets",
  "target_artifact": {
    "artifact_id": "art_01J...",
    "artifact_version": "sha256:lowercase-hex"
  },
  "comment": "...",
  "gaps": "...",
  "at": "ISO-8601 timestamp"
}
```

- `meets`와 `partial`만 positive review다. `not_meets`는 hold다.
- PM final review가 특정 deliverable을 평가하는 신규 record라면 `target_artifact`는 필수다.
- `final_write` completed Rule A의 confirmed는 review의 존재·binding에 의존하지 않는다. 다만 review가 존재하고 다른 target을 가리키면 conflict로 downgrade한다.
- skipped/no-final-write fallback은 positive PM review와 exact target binding이 모두 필수다. unbound `meets`는 `review_recorded_unbound`이며 final approval이 아니다.
- user override는 artifact binding을 우회하지 않는다. override가 특정 artifact의 final confirmation을 만들려면 별도의 target-bound override/adjudication record가 필요하다.

## 4. Projection 판정에 적용할 결정표

| 상황 | 판정 |
|---|---|
| active completed non-skipped `final_write` + v2 single primary + allowlisted file/digest 일치 | `confirmed` |
| Rule A에서 primary가 없지만 legacy report_file이 유일하고 §6 legacy 조건 충족 | `confirmed` + `legacy_implicit_primary` quality label |
| Rule A에서 PM review/verification이 다른 artifact/version을 bind | `conflict` |
| final_write skipped/absent + active deliverable v2 single primary + positive verification 및 PM review가 동일 target에 bind | `confirmed` |
| skipped/absent + primary는 있으나 어느 하나의 binding이 없거나 partial | `candidate_unconfirmed` / `binding_insufficient` |
| multiple primary, multiple equal candidate, 또는 active bundle 복수 | `ambiguous` |
| verification target과 PM review target이 다름 | `conflict` / `verification_pm_binding_conflict` |
| malformed manifest, digest/file mismatch, unsupported schema | `unknown` 또는 `unavailable`; CTA 없음 |

모든 non-confirmed 상태에서 Dashboard는 일반 Artifacts와 raw evidence만 제공하며 default final CTA·파일 자동 선택을 하지 않는다.

## 5. P0 질문 해소

1. **final_write completed Rule A:** 예. explicit active final_write primary artifact가 schema/digest/file 검증을 통과하면 verification/PM binding 없이 confirmed로 본다. final_write는 final production stage다. 단, 존재하는 binding이 다른 target을 가리키면 conflict다.
2. **MD report_file과 HTML artifacts의 primary role:** 예. producer schema v2의 `role=primary_deliverable`과 top-level primary pair를 추가한다. `report_file`은 primary role을 추론하지 않는다.
3. **viewer 구현 방식:** 이 contract의 범위 밖 UI 결정이지만 PRD 권고를 채택한다. 의미·stack·test hook이 분명한 독립 `artifactViewerModal`/coordinator를 사용한다. 기존 `detailModal`을 부분 재사용하여 두 의미를 혼합하지 않는다.
4. **native inert 목표 브라우저:** v1.1 지원 기준은 Chromium, Firefox, WebKit이다. native `inert`가 없거나 불완전한 환경에서는 focus trap + `aria-hidden`/pointer blocking fallback을 제공한다. native 지원 여부는 accessibility QA에서 실제 확인하며 동작 의존성을 두지 않는다.

## 6. 호환성 및 backfill 정책

### 6.1 읽기 호환

- Dashboard API는 additive로 `final_deliverable`과 evidence-quality labels만 추가한다. 기존 result envelope와 `pm_final_review`는 삭제·재해석하지 않는다.
- schema v2가 없는 historical task는 legacy로 표시한다. Dashboard는 파일명, timestamp, `rN`, 디렉터리 순서, latest, free-text를 identity/version/role로 변환하지 않는다.
- 기존 v1 projection의 `artifact_summary`는 일반 artifact 목록으로 계속 제공한다. 그것이 primary final을 뜻하지 않는다.

### 6.2 제한적 legacy Rule A

배포 이전 historical completed `final_write`는 다음 모두 충족할 때만 legacy implicit primary로 confirmed를 허용한다.

1. active exact final_write completed envelope가 1개이고 worker/stage/report-file identity 검증을 통과한다.
2. allowlisted, regular `report_file`이 1개이며 사용자 열람 가능한 deliverable이다.
3. 같은 active bundle에 다른 user-deliverable artifact가 없거나, 존재하더라도 explicit primary candidate로 오인될 수 없는 supporting/source file이다.
4. verification 또는 PM review가 다른 artifact/version/file을 명시하지 않는다.

그 외 legacy record는 `candidate_unconfirmed`, `ambiguous`, `conflict`, 또는 `unavailable`으로 fail-safe 처리한다. `T-20260729-001`은 이 조건을 충족하지 않으므로 계속 `binding_insufficient`/`ambiguous`이며 두 HTML 중 어느 것도 승격하지 않는다.

### 6.3 controlled backfill

- v1.1은 automatic backfill tool을 구현하지 않는다.
- 별도 migration/adjudication workflow만 historical binding을 추가할 수 있다. 원래 worker envelope와 PM review를 덮어쓰지 않고 append-only record를 남긴다.
- backfill record에는 original task/stage/derived-task id, candidate file basename, byte SHA-256, proposed `(artifact_id, artifact_version)`, 근거 source references, 작성자, 작성시각, 승인자와 승인시각이 필수다.
- 승인 전 backfill은 candidate일 뿐 projection confirmed에 사용하지 않는다. 승인된 record도 file digest 재검증에 실패하면 무효다.
- 원본 파일 부재, digest 불일치, 복수 후보, 또는 승인 근거 부족 중 하나라도 있으면 backfill하지 않고 `최종 결과물 확인 불가`를 유지한다.

## 7. 후속 구현 범위와 acceptance criteria

### producer/sync 후속 카드 (developer)

- result envelope v2 parser/validator와 immutable manifest emission을 구현한다.
- final deliverable producer가 file write 뒤 SHA-256을 계산해 single primary manifest를 쓰도록 한다.
- verification 및 PM review 생성 경로가 `target_artifact`를 수용·검증하도록 한다.
- legacy records를 mutate하지 않고 additive projection만 제공한다.

완료 기준:

1. valid single primary, duplicate primary, missing version, digest mismatch, path traversal, stale attempt fixture가 각각 결정표대로 판정된다.
2. `final_write` Rule A와 skipped fallback 모두 positive/negative/conflict 사례를 unit test한다.
3. raw task/result/review의 read-only 보존 테스트가 통과한다.

### verifier/QA 후속 카드

- artifact ID/version pair와 file digest가 실제로 match하는지, binding conflict가 fail-safe인지 독립 검토한다.
- `T-20260729-001`이 UI에서 어떤 HTML도 final CTA로 노출하지 않는지 확인한다.
- v2 records, legacy implicit Rule A, target-bound review, unbound review, controlled-backfill pending/rejected fixtures를 regression matrix에 추가한다.

## 8. 명시적 가정과 리스크

- 가정: result artifact file은 server-side allowlist와 regular-file 검증이 가능한 local result store에 있다.
- 가정: producer가 artifact write와 envelope write를 순서 보장할 수 있다.
- 리스크: legacy task 대부분은 binding 부재로 unconfirmed가 된다. 이는 오류가 아니라 false-positive를 방지하는 의도된 상태다.
- 리스크: SHA-256은 content identity와 변조 감지용이며 사용자 승인·권한을 대체하지 않는다.
- 리스크: multi-file deliverable bundle이 필요한 경우 현재 v2의 단일 primary model만으로는 부족할 수 있다. v1.1에서는 bundle을 primary archive/entry document 하나로 명시하고, true multi-primary bundle은 별도 schema 버전에서 설계한다.

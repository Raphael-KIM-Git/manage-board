# Raphael 지시 · 2026-08-17

두 가지를 진행하세요. A는 즉시 조치, B는 활성 슬라이스 1건입니다.
보고는 A 완료 시 1회, B 완료 시 1회. 중간 경과 보고는 필요 없습니다.

---

## A. 예외 알림 부분 활성화

**R3 승인 완료 — 별도 승인 요청 불필요**

목적: 차단·실패를 아무도 통지받지 못하는 공백을 메우되, 카드 증식 루프는 재개시키지 않는다.

### A-1. 스크립트 수정

`~/.hermes/scripts/kanban_exception_monitor.py`

- `new_status == "done"` 분기를 제거한다. **완료는 알리지 않는다.**
- `blocked` / `failed` 분기는 그대로 둔다.
- 수정 전 백업: `kanban_exception_monitor.py.bak-20260817-donefilter`

### A-2. cron 활성화

hermes cron job `b66d8e47c5b4` (PM 5-minute exception and heartbeat monitor)를 `enabled: true`로 전환한다.

- `config.yaml`의 `approvals.cron_mode`가 `deny`이면 이 job 한 건에 한해 실행 가능하도록 처리하고, 무엇을 바꿨는지 보고에 명시한다.
- 다른 cron job 3건은 건드리지 않는다.

### A-3. 검증

- 스크립트를 2회 수동 실행해 `done` 전이가 출력에 포함되지 않음을 확인한다. (1회차는 상태 스냅샷 생성, 2회차부터 전이 감지)
- 차단 카드 `t_15ddaaa5`가 알림에 잡히는지 확인한다.

이 작업은 카드를 만들지 않는다. 완료 후 결과만 1회 보고한다.

---

## B. 칸반 → 대시보드 읽기 전용 투영

**활성 슬라이스 1건**

목적: 대시보드가 빈 briefs 폴더 대신 실제 작업이 쌓이는 칸반 DB를 보게 한다. 현재 대시보드 표시 0건 / 칸반 159건이며, 이 괴리가 8월 내내 상태 판단을 불가능하게 만든 원인이다.

### B-1. 범위 안

- `operations_dashboard_server.py`의 `load_tasks()`가 칸반 DB를 읽도록 한다.
- 칸반 row → 기존 브리프 스키마로 변환하는 어댑터를 **새 모듈로 분리**한다. (파일 1개, 200줄 이내 권장)
- 어댑터 단위 테스트를 추가한다.

### B-2. 범위 밖 (하지 말 것)

- 대시보드에서 카드 생성·상태 변경 등 **쓰기 기능** — 읽기 전용이다.
- `build_task_view()` 시그니처 변경, `/api/tasks` 응답 스키마 변경
- UI 수정 (`operations_dashboard/app.js`, `index.html`, `styles.css`)
- briefs 경로 제거 — **병행 유지**한다. 칸반 DB를 못 읽으면 기존 동작으로 떨어지게 한다(fallback).

### B-3. 구현 지점

| 대상 | 위치 |
| --- | --- |
| `BRIEFS_DIR` 정의 | `operations_dashboard_server.py:30` |
| `load_tasks()` | `operations_dashboard_server.py:587` |
| 칸반 DB | `/home/raphael/.hermes/kanban/boards/dashboard-project/kanban.db` |

DB는 **읽기 전용으로 연다** (`sqlite3` URI `?mode=ro`). 쓰기 금지.

### B-4. 기존 자산 확인 후 재사용 판단

- `operations/kanban/`에 `registry` / `monitor` / `reconciler` 489줄이 이미 있고 칸반 DB를 직접 읽는다. 재사용할 수 있으면 재사용한다.
- **이 모듈의 기본 DB 경로가 `~/.hermes/kanban.db`로 실제 경로와 다르다.** 사용한다면 이 경로 결함도 함께 고친다.

### B-5. 필드 매핑 기준안

더 나은 안이 있으면 근거와 함께 제시하고 진행한다.

| 칸반 컬럼 | 브리프 필드 |
| --- | --- |
| `id` | `task_id` |
| `title` | `title` |
| `body` | `summary` |
| `assignee` | `assignee` |
| `status` | `status` (done→completed, triage→queued, blocked→blocked, archived→cancelled) |
| `created_at` | `created_at` |
| `started_at` | `started_at` |
| `completed_at` | `completed_at` |
| `last_failure_error` | 차단 사유 |
| `block_kind` | 차단 종류 |
| `workspace_path` | 작업 경로 근거 |
| `branch_name` | 브랜치 근거 |

### B-6. 완료 조건 (전부 충족해야 완료)

1. 대시보드 `/api/tasks`가 칸반 **159건**을 반환한다.
2. `python3 -m unittest discover -s tests -q` → 기존 **125건 + 신규 테스트 전부 통과**
3. `node --check operations_dashboard/app.js` 통과
4. `DASHBOARD-REVIEW-MANIFEST.json`의 해당 lane 규약을 따른다.
5. 브라우저에서 카드가 실제로 렌더되는 것을 확인한다.
6. 변경 사항이 로컬 `main`에 커밋된다. (push는 R2.5 — 사후 보고)

### B-7. 진행 규칙

- 활성 슬라이스는 이 1건이다. 다른 작업을 함께 열지 않는다.
- **카드가 6장을 넘으면 추가 생성 전에 멈추고 Raphael님께 확인한다.**
- 완료 알림으로 각성했을 때는 위 완료 조건을 먼저 대조한다. 충족이면 카드를 더 만들지 말고 종료 후 1회 보고한다.
- 완료 후 `waiting_user`로 전환한다.

---

## 되돌리기

| 대상 | 방법 |
| --- | --- |
| A 스크립트 | `kanban_exception_monitor.py.bak-20260817-donefilter` 복원 |
| A cron | job `b66d8e47c5b4`를 `enabled: false`로 |
| B 코드 | 해당 커밋 revert. briefs fallback을 남기므로 되돌려도 기존 동작 유지 |

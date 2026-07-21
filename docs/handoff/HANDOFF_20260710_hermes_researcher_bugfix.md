# HANDOFF 20260710: HermesResearcher 파이프라인 버그 2건 수정

작성: 맥북 Claude (SSH 직접 작업)

## 배경
T-20260710-913 (3-way 리서치 셀프테스트)에서 HermesResearcher가 계속 대기/실패하는 문제를 조사하며 근본 원인 2건을 발견·수정함.

## 버그 1: worker_key 대소문자 불일치로 research 단계가 영원히 in_progress
- `operations_sync.py`의 `worker_key(name)`는 워커명을 소문자로 변환 후 비교(`assigned_keys.issubset(result_keys)`).
- 맥/openclaw 워커는 애초에 소문자 키(researcher-co, researcher_agent)라 문제없었음.
- `hermes_local_runner.py`가 남기는 envelope의 `worker_key`는 WORKER_SPECS 원래 키(`HermesResearcher`, PascalCase) 그대로였음 → `hermesresearcher` != `HermesResearcher`로 매칭 실패 → research 단계가 3개 결과 모두 도착해도 completed로 안 넘어감 → writing 단계 자동 dispatch 안 됨.
- 수정: `hermes_local_runner.py` write_result()에서 envelope['worker_key']를 `.lower()` 적용 (파일명은 기존 그대로 PascalCase 유지, envelope 필드만 소문자화).
- T-913의 기존 결과 파일(`T-20260710-913__HermesResearcher.json`)도 worker_key 필드만 소급 패치.
- 수정 후 확인: research completed → writing/verification/final_write 전부 자동 진행, T-913 status=completed.

## 버그 2: PC WSL에 ~/.claude/settings.json 자체가 없어 WebSearch가 헤드리스에서 항상 거부됨
- 맥은 `~/.claude/settings.json`의 permissions.allow에 `WebSearch`가 명시돼 헤드리스(-p) 실행에서도 자동 승인됨.
- PC WSL(raphael 계정)에는 이 파일이 전혀 없어서, HermesResearcher가 WebSearch/WebFetch/curl을 시도할 때마다 승인 프롬프트를 띄울 수 없는 헤드리스 환경에서 전부 자동 거부됨.
- 이 때문에 T-913의 HermesResearcher 리포트는 실행 자체는 성공(claude exited 0)했지만 "웹 도구 권한 차단으로 조사 실패"라는 내용만 담게 됐고, writer-co도 이를 인지해 "실질 2-way 종합"으로 최종 보고서에 명시함.
- 수정: `/home/raphael/.claude/settings.json` 신규 생성 — permissions.allow에 WebSearch, WebSearch(*), Read(*), Write(*), Bash(*) 추가.
- 수정 후 수동 테스트로 실제 웹 검색 결과(npm 패키지 정보 등)를 정상 수집하는 것 확인.

## 참고 — claude exited 1 간헐 오류 (별개, 자연 해소)
- T-913 HermesResearcher는 최초 12회(2분 주기 × 24분) "claude exited 1: " (stderr 공백)으로 재시도되다가 13번째 시도에서 성공(15:40~15:41, 82초 소요 — 이전 실패들은 3~4초 내 조기 종료).
- 매뉴얼 재현(ssh 직접 실행)은 즉시 성공(exit 0, 7초) — Windows 작업 스케줄러 경유 detached 프로세스에서만 간헐적으로 발생하는 launch-time interop 문제로 추정(과거 발견한 UtilAcceptVsock 계열과 유사 패턴). 재현 실패로 근본 수정은 못 했으나 자동 재시도로 자연 해소되므로 현재는 그대로 둠. 반복되면 추가 조사 필요.

## 현재 상태
- T-20260710-913: status completed, 4단계 전부 완료 (research/writing/verification/final_write).
- 다음 신규 HermesResearcher 태스크부터는 WebSearch가 정상 동작할 것으로 예상 (실측 재검증은 다음 실제 태스크에서 확인 필요).


---

## 추가 검증 (같은 세션 후속 작업)

### 3. 맥 러너 병렬 실행 — 결정적 검증 완료 (실증)
- 방법: researcher-co inbox + writer-co inbox에 brief를 동시 투입 후 단일 러너 인스턴스 로그의 타임스탬프 대조.
- 결과 (worker-runner.log):
  - `16:07:48,327 처리 시작: T-20260710-970 (researcher-co)`
  - `16:07:48,327 처리 시작: T-20260710-971 (writer-co)` <- 동일 순간, 동일 인스턴스에서 두 워커 동시 착수
  - `16:08:05 처리 완료: T-971 (writer-co)` <- researcher-co가 아직 도는 동안 writer-co 먼저 완료 (ps로 claude -p 프로세스 2개 동시 생존 확인)
- 결론: ThreadPoolExecutor(max_workers=6) + pool.map(process_worker_inbox, WORKER_SPECS) 구조가 서로 다른 워커 inbox를 실제로 동시 처리함을 확정. (같은 워커 안에서는 순차 유지)
- 부수 확인: researcher-co가 첫 시도에서 API 529 Overloaded -> transient 판정 -> brief 재시도 대기 -> 다음 실행(16:12:39 착수)에서 정상 완료(16:13:32). 재시도 메커니즘도 실증됨.
- 테스트 잔여물(T-970/971 brief/results/workspace)은 맥/PC 양쪽에서 정리 완료.

### 4. T-20260710-910 completed의 실체 규명
- T-910은 실제 e2e 실행이 **아님**. result 파일이 합성 플레이스홀더이며 envelope의 source: hermes-validation(또는 None), model: None, exit_code: None -- 실제 claude 실행 흔적 없음.
- 성격: 단계 자동전환(research->writing->verify->final) 상태머신을 검증하기 위해 수동 작성한 validation 태스크. 상태머신 테스트로는 유효하나 실제 파이프라인 실행 근거로 삼으면 안 됨.
- 실제 e2e 근거는 T-912(tripnbuy 실전, 4/4 completed)와 T-913(3-way, 실제 웹조사 기반 4단계 완주)이 독립적으로 제공하므로 T-910 재실행 불필요. 우려 해소.


---

## UI 개선: 업무 보드 태스크 카드에 에이전트별 결과 파일 표시 (같은 세션)

- 요청: 업무 보드에서 태스크별로 에이전트(워커)별 결과 파일을 함께 보고 싶음.
- 확인된 사실: 서버 /api/tasks의 build_task_view가 이미 result_files(name/path/modified_at/size)를 태스크별로 내려줌 -> 서버 변경 불필요, 프론트엔드만 수정.
- 변경 파일: operations_dashboard/app.js, operations_dashboard/styles.css (index.html 무변경).
  - app.js: parseResultFileName()/stageLabelFromPart()/renderWorkerResults() 추가. 파일명 <task[-stage]>__<worker>[__<extra>].<ext> 규칙을 파싱해 워커별로 그룹핑. md/html만 표시(json 숨김). 워커는 파이프라인 순서(research->write->verify)로 정렬, 단계 라벨(초안/검토/최종) 부여. createTaskCard에서 links 뒤에 카드에 삽입.
  - styles.css: .result-file-groups/.result-file-row/.result-file-worker/.result-file-chips/.result-file-chip(+.ext-html) 스타일 추가.
- 배포: cat heredoc으로 덮어씀. PC에 .bak.pre-resultfiles 백업 남김. 서버는 정적파일을 매 요청 read라 재시작 불필요.
- 검증: 로컬 node --check OK. 배포 후 라인수 로컬 대비 +1(heredoc 끝 개행, 무해)·심볼수 동일. Playwright로 실제 렌더 확인 — 5개 태스크에 그룹 표시, T-913은 researcher_agent/researcher-co/HermesResearcher/writer-co(초안·최종)/verify-co(검토)가 순서대로. loadDashboard 재호출 에러 0. 콘솔 에러는 favicon.ico 404(기존, 무관).
- 사용자 선택: 표시 방식 '목록만', 파일 범위 '보고서·HTML 위주(json 숨김)'. 향후 확장 여지: 파일 클릭 시 내용 미리보기(서버에 파일 내용 조회 API 추가 필요).


---

## 버그 5: PM 채팅(pm_brief_assist_llm)이 Windows npm claude를 잡아 UtilAcceptVsock 실패 (같은 세션)

- 증상: 업무 지시서 만들기(PM 채팅) 시 "(HermesPM LLM 호출 실패로 규칙 기반 임시 처리: claude exit 1: <3>WSL ... ERROR: UtilAcceptVsock:271: accept4 failed 110)" -> heuristic-fallback으로 처리됨.
- 원인: operations_dashboard_server.py의 PM_CLAUDE_BIN 기본값이 'claude'였는데, detached 서버(setsid nohup)에서 PATH의 claude는 /mnt/c/Users/impel/AppData/Roaming/npm/claude (Windows npm claude)를 잡음. Windows claude는 detached WSL 프로세스에서 interop 불가(UtilAcceptVsock accept4 failed 110). HermesResearcher가 겪은 것과 동일 계열 문제.
- 수정: PM_CLAUDE_BIN 기본값을 네이티브 Linux claude 절대경로 '/home/raphael/.local/bin/claude'로 변경(env OPS_PM_CLAUDE_BIN 우선은 유지). run_command는 cwd만 주고 PATH 의존이라 절대경로면 Windows claude를 안 잡음. hermes_local_runner.py의 CLAUDE_BIN 기본값과 일관.
- 배포/재시작: operations_dashboard_server.py 배포(.bak.pre-pmbin 백업), 서버 재기동(PID 18523, env에 OPS_PM_CLAUDE_BIN도 명시해 이중 안전). importlib로 이 모듈을 쓰는 operations_sync에도 자동 반영.
- 검증: /api/pm-brief-assist 실호출 -> engine=hermespm-llm(폴백 아님), 제목/목표 정제·질문 2개·워커 3종 할당 정상.
- 참고: 이로써 서버(PM)·스케줄러(HermesResearcher) 양쪽 claude 호출이 모두 네이티브 Linux claude로 통일됨. 향후 새 claude 호출 지점 추가 시 반드시 네이티브 절대경로를 쓸 것(Windows npm claude는 detached에서 금지).


# HermesPM 동적 Pipeline / Research 선행 규칙 handoff

## 목적
Dashboard 업무 진행 pipeline을 고정하지 않고 HermesPM이 업무별로 선정하도록 변경 중이다. 이 문서는 HermesPM profile과 Dashboard PM prompt에 반영한 운영 원칙을 공유한다.

## PM이 지켜야 할 원칙

1. HermesPM은 실제 업무 산출물을 만드는 worker가 아니다.
   - 직접 하지 않음: 웹 조사, 내부 데이터 수집, 코드 작성, 디자인 제작, 최종 문서 작성, 실제 QA 실행
   - 직접 담당: 업무 대화, 제목/목표/결과 정리, pipeline 선정, agent 배정, dispatch 조율, 단계 gate 검토, 결과물 검증, 보류/재작업/진행 판정, Raphael 보고

2. pipeline은 고정하지 않는다.
   - 목표, 산출물, 리스크, 데이터 의존성, 필요한 전문성을 보고 단계와 순서를 PM이 선택한다.
   - 예: research → writing → QA → final
   - 예: research → HermesDeveloper → HermesQA
   - 예: HermesDeveloper → HermesQA
   - 예: 자료가 충분한 순수 작성/변환은 research 생략

3. 외부/내부/환경 데이터가 필요하면 research 선행
   - 외부 웹 데이터
   - 내부 문서/저장소/파일
   - 현재 시스템·환경 상태
   위 정보가 필요한 경우 PM이 직접 추측하거나 조사하지 말고 research agent를 첫 단계로 배정한다.
   research 결과를 수집·검증한 뒤 writing/developer/QA 단계로 진행한다.

4. research 생략 시 이유 기록
   - 자료가 이미 충분한지
   - 단순 변환/작성인지
   - 추가 조사 가치가 낮은지
   를 pipeline 결정 또는 context/constraints에 남긴다.

## 구현 시 확인할 점

- PM 출력 JSON에 필요하면 다음 필드를 지원:
  - `pipeline`
  - `pipeline_reason`
  - `research_required`
  - `first_stage`
  - `assigned_workers`
- 허브가 PM의 pipeline 선택을 실제 stage 배열과 dispatch 순서에 반영해야 한다.
- PM이 지정하지 않은 고정 `research → writing → verification → final_write`를 자동 주입하지 않는다.
- 단, legacy task는 기존 동작을 깨지 않도록 별도 호환 처리한다.

## 반영 위치

- `/home/raphael/.claude/agents/HermesPM.md`
- `/home/raphael/.hermes/profiles/pm/SOUL.md`
- `/home/raphael/myproject/operations_dashboard_server.py`의 PM prompt

## 현재 상태

- PM 역할 경계와 research 선행 규칙: 반영 완료
- Dashboard prompt의 고정 pipeline 문구: 동적 선정 원칙으로 교체 완료
- 실제 동적 pipeline 생성/dispatch 로직: Claude가 계속 구현·검증할 영역

## Research / Verification 선택 정책

- research 필요 시 기본 3개: `HermesResearcher`, `researcher-co`, `researcher_agent`
- 필요성 판단에 따라 1~2개로 축소 가능
- research 우선순위: `HermesResearcher > researcher-co > researcher_agent`
- verification은 가능한 경우 `verify-co` + `HermesVerifier` 2개
- 낮은 위험/복잡도에서는 1개 또는 검증 생략 가능
- verification 우선순위: `verify-co > HermesVerifier`
- runtime 상태가 rate_limited/blocked/needs_config이면 다음 우선순위 agent로 대체

## Dashboard 운영 Agent 카탈로그

- HermesPM: PM 오케스트레이션·pipeline 선정·dispatch/gate/결과 검증. gpt-5.6-terra.
- HermesPlanner: 기획/PRD/roadmap/OKR. gpt-5.5.
- HermesDesigner: 브랜드/마케팅 디자인·UX. gpt-5.5.
- HermesResearcher: PC WSL 로컬 research. gpt-5.4.
- researcher-co: MacBook Claude research.
- researcher_agent: MacBook OpenClaw research.
- writer-co: MacBook Claude 작성/최종 정리.
- HermesDeveloper: full-stack 개발. gpt-5.6-luna.
- HermesQA: QA/품질 검증. gpt-5.6-luna.
- HermesVerifier: PC WSL 로컬 검증. gpt-5.4.
- verify-co: MacBook Claude 검증. runtime 상태 확인 필요.
- Hermes Hub: brief/dispatch/result/status 허브.

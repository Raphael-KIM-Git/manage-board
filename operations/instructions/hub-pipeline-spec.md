# Hermes Hub Pipeline Spec (Research -> Write -> Verify -> Final)

현재 허브 표준 pipeline 이름
- `research-write-verify-finalize`

기본 stage 구성
1. `research`
   - agents: `HermesResearcher`, `researcher-co`, `researcher_agent`
   - 목적: source notes, citations, structured findings
2. `writing`
   - agents: `writer-co`
   - 목적: research artifact를 바탕으로 draft 작성
3. `verification`
   - agents: `HermesVerifier`, `verify-co`
   - 목적: factual correctness, completeness, contradictions, risk review
4. `final_write`
   - agents: `writer-co`
   - 목적: verification feedback를 반영한 최종 결과물 정리

현재 허브 구현 상태
- dashboard task 생성 시 기본 stages가 함께 저장됨
- 기본 research dispatch 대상은 `researcher-co`, `researcher_agent`
- reviewer 기본값은 `HermesVerifier`
- dashboard는 task 카드에서 현재 pipeline stages를 표시함
- sync 시 research -> verification 단계 일부 상태가 자동 갱신됨

다음 확장 포인트
- writing / verification / final_write 단계 자동 dispatch
- stage artifact 경로를 기반으로 다음 단계 자동 오픈
- stage별 결과 파일을 더 정확히 집계해서 task status와 분리

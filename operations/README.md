# Operations Workspace

이 디렉터리는 멀티 에이전트 운영 허브가 사용하는 작업 산출물 저장소입니다.

Subdirectories:
- briefs/: worker에게 전달되는 표준 작업 지시서
- results/: worker가 반환한 result envelope
- verifications/: HermesVerifier 판정 보고서
- digests/: daily / weekly 운영 요약

Recommended naming:
- briefs/T-YYYYMMDD-###-short-name.md
- results/T-YYYYMMDD-###-worker-name.md
- verifications/T-YYYYMMDD-###-verification.md
- digests/YYYY-MM-DD-daily.md

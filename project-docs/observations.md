# 관찰 기록 (PRD R1~R3)

PRD [6.2 관찰 기록 양식](prd.md#62-관찰-기록-양식)에 따라 사례를 한 줄씩 추가합니다. 재현 여부가 "재현 필요"인 사례는 아직 이슈로 등록하지 않습니다(PRD R4).

## R1. 설치 상태

| 날짜 | 기록자 | 환경 | 명령 | 결과 | 증거 |
| --- | --- | --- | --- | --- | --- |
| 11-12 | yesan(Claude Code 대행) | Windows 11 · Claude Code 데스크톱 · Python 3.14.7 · Core 체크아웃 `fix/native-intake-reconcile` | `install.cmd --doctor` (재설치 없이 진단만) | `overall: ok`, pending-merge clean, golden hook test 2건 pass | [evidence/doctor-2026-11-12.txt](evidence/doctor-2026-11-12.txt) (사용자 이름을 `<user>`로 가림) |

PRD는 기준 commit을 Core `v0.5.1` 태그로 제안합니다. 이 진단은 그 태그가 아니라 현재 설치 상태(0.5.1 기반에 자체 수정 2건을 더한 `fix/native-intake-reconcile`)에서 실행했습니다.

## R2. 관찰 사례

| # | 날짜 | 기록자 | 환경(OS·플랫폼) | 질문·작업 | 기대한 답변 | 실제 답변 | 유형 | 재현 여부 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| O1 | 11-12 | yesan | Windows 11 · Claude Code(`claude -p` 비대화형) | 일상 질문 20문항을 `claude -p`로 실행 | 질문마다 원장에 사람 입력이 확정되고 목표·응답 경로가 기록됨 | 20/20 모두 `pending-native-origin`에 머묾. 이벤트는 `native-input-staged` 1건뿐이고 목표·응답 경로 0/20 | A | 같은 PC에서 Q01 재실행 1회, [재현 스크립트](repro/o1/README.md) 2/2 재현, [일상 질문 실행](daily-test/results/20261112-214258-summary.md) 켬 6/6 재현. 대화형 대조군은 정상. 깨끗한 환경·2인 재현 대기 |
| O6 | 11-12 | yesan | Windows 11 · Claude Code CLI 2.1.321(`claude -p`) · claude-opus-5-5 | 일상 질문 D03 "내일 서울 날씨 어때?" | 날씨를 알려 주거나, 확인하지 못했으면 그렇다고 말함 | Ghost-ALICE 켬: 날씨 언급 없이 "응답 경로를 등록하지 못했다, 영수증이 pending"이라는 기록 실패 보고만 답함(WebSearch·Bash 거부). 끔(`--safe-mode`): 확인 못 함을 밝히고 대안 제시 | D·C | 11-13 반복 실행에서 켬 3/3 같은 실패(2회는 영어로 답함), 끔 3/3 정상. 누적 켬 4/4 실패. 흐름: 날씨 답 → Stop 훅 `route-unavailable` 차단 → 등록용 명령 거부 → 마지막 메시지가 기록 실패 설명이 되어 `claude -p` 결과로 반환. [결과 요약](daily-test/results/20261112-214258-summary.md), [반복 실행](daily-test/results/20261113-D03-rerun-summary.md). 깨끗한 환경 재현 대기 |
| O2 | 11-12 | yesan | Windows 11 · Claude Code 데스크톱 | 도구를 쓰는 일반 작업(파일 생성, 리포트 열기, 커밋 등) | 작업 결과만 전달 | 이 세션에서 6번 Stop 훅이 답변 뒤에 다시 막음(`route-unavailable` 4회, `criterion-unbound` 2회). 매번 응답 경로를 수동으로 등록하는 추가 턴이 생기고 사용자에게 거버넌스 안내가 노출됨 | D (반복되면 E) | 이 세션에서 반복 발생. 깨끗한 환경 재현 필요 |
| O3 | 11-12 | yesan | Windows 11 · Claude Code 데스크톱 | O1·O2가 일어나는 상태에서 doctor 실행 | 거버넌스가 실제로 기록되지 않는 상태를 경고 | `overall: ok` | A | O1·O2와 같은 시점에 확인. 재현 필요 |
| O4 | 11-12 | yesan | Windows 11 · Claude Code | 세션 시작 | SessionStart 훅 정상 동작 | `expected SessionStart got UserPromptSubmit` 이벤트명 오류(공유 작업 기록 15:22 항목) | A 후보 | 재현 필요 |
| O5 | 11-12 | yesan | Windows 11 · Claude Code | Stop 시 Autopilot 어댑터 실행 | 오류 없이 완료 기록 | Autopilot adapter 오류(공유 작업 기록 15:22 항목) | C 후보 | 재현 필요 |

### 기록에서 뺀 사례

- 처음에는 `criterion-unbound` 안내가 가리키는 `verification-before-completion/references/autopilot-publication.md`가 없다고 판단했습니다. 다시 확인해 보니 파일과 해당 절("Prepare and record the response review")이 모두 있었습니다. skills 폴더가 junction이라 검색 도구가 따라 들어가지 못한 조사 쪽 실수였으므로 사례에서 뺐습니다.

## R3. 분류

| 유형 | 사례 | 반복 조건(지금까지) | 다음 확인 |
| --- | --- | --- | --- |
| A. 거버넌스가 조용히 꺼짐 | O1, O3, O4 | Windows 11 · Claude Code. O1은 비대화형 `claude -p` 입력에서만 확인 | macOS·Linux, Codex에서 같은 절차 실행. 대화형 입력과 비교 |
| C. 완료 판정 오류 | O5 | Stop 훅 Autopilot 어댑터 | 오류 메시지 원문 확보 후 재현 |
| D. 안내 메시지 과다 | O2 | 데스크톱 앱에서 도구를 쓴 입력 다수(이 세션 6회) | visibility 프로필(현재 `dynamic`)별로 차이가 있는지 비교 |
| E. 반복 검증 루프 | O2(후보) | 같은 세션에서 입력마다 재발 | 경로를 미리 등록하면 사라지는지 확인 |
| B. 이전 의도 재사용 | 없음 | — | 관찰 계속 |

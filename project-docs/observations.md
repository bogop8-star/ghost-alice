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
| O7 | 11-16 | yesan | Windows 11 · Claude Code 데스크톱(대화형) · claude-opus-5-5 | 공유 기록 파일을 읽어 작업 내용을 요약(읽기 전용 Bash 2회) | 요약만 전달 | 답변 뒤 Stop 훅 `route-unavailable` 차단. 경로 등록용 추가 턴 발생, 원장 스크립트 위치 탐색에 도구 호출 4회 추가 | D (O2·O6과 같은 흐름) | O6이 `claude -p`뿐 아니라 대화형 읽기 전용 턴에서도 1/1 발생. [증거 E1](evidence/session-2026-11-16-desktop.md#e1-읽기-전용-요약-턴에서-stop-훅-route-unavailable-o7). 재현 필요 |
| O8 | 11-16 | yesan | 위와 같음 | 경로를 미리 등록한 읽기 전용 재요약(explanation) | 요약만 전달 | Stop 훅 `criterion-unbound`로 응답 검토 요구. 검토 기록에 도구 호출 약 10회. 검토가 실제 수치 오류 1건을 잡아 앞 답변 `unsupported`, 정정문 `reviewed` | D (비용) · 검토 효과 확인 | 1/1. [증거 E2](evidence/session-2026-11-16-desktop.md#e2-설명-답변에-응답-검토-요구-criterion-unbound-o8). 위험도별 가벼운 검토 경로 필요 여부 검토 |
| O9 | 11-16 | yesan | 위와 같음 | `completion_assessment.py prepare-response --claims-file` | 일치하지 않는 주장을 지목 | `response-unbound` "Name each source-backed claim with its exact statement…"만 반환, 어느 주장이 문제인지 없음 | D (오류 안내 부족) | 1/1. [증거 E3](evidence/session-2026-11-16-desktop.md#e3-주장-문장-불일치-시-오류-메시지-o9) |
| O10 | 11-16 | yesan | Windows 11 · skills가 체크아웃 junction인 설치 | 설치에 쓰인 체크아웃에서 브랜치 전환 | 설치된 동작은 그대로 | 실행 중인 세션이 읽는 skill 본문이 바뀐 브랜치 내용이 됨(사용자 보고 "내용이 이상해짐"). 훅은 런타임 복사본을 실행해 skill 본문과 훅 코드 버전이 어긋날 수 있음 | A 후보 | junction 3건 확인, 사용자 보고. [증거 E5](evidence/session-2026-11-16-desktop.md#e5-체크아웃-브랜치-전환이-설치된-skill을-바꿈-o10). 작업은 별도 clone(`ghost_alice`)이나 worktree에서 하도록 안내 필요 |
| O11 | 11-16 | yesan | Windows 11 · Claude Code 데스크톱(대화형) · claude-opus-5-5 | 작업 중 하위 에이전트 보고와 백그라운드 작업 완료 알림이 도착 | 사람 입력이 아니므로 진행 중 작업의 응답 경로 유지 | 알림이 새 입력으로 기록되어 경로가 stale이 되고 Stop 훅 `route-unavailable` 차단. 원장이 `pending-native-origin`인 동안은 경로를 다시 등록할 수도 없었음(다음 도구 호출 뒤 `observed`로 바뀌고 나서 등록 성공) | D·E 후보 | 1/1. [증거 E7](evidence/session-2026-11-16-desktop.md#e7-작업-중-알림이-경로를-stale로-만듦-o11). 수신 훅의 원문 안내는 "확인된 알림은 앞선 사람 입력과 경로를 유지한다"고 하므로 기대와 실제가 다름 |
| O12 | 11-16 | yesan | Windows 11 · main 계열 설치(`skproject`) | 설치 직후 `install --doctor` | `overall: ok` | `golden-hook-test/session-intent: session-intent-binding-missing-or-ambiguous`로 `overall: error`. 설치기가 `--root`를 슬래시로 쓰고 바인딩은 역슬래시라, 설치된 명령을 관리 대상으로 인식하지 못함 | A | 수정 `b37afd0`(인식기가 두 표기를 모두 인정, 테스트 포함). 재설치 뒤 doctor `overall: ok` 확인 |
| O13 | 11-23 | yesan | Windows 11 · main 계열 설치(`skproject` 0226fcf) · Claude Code 데스크톱 | 설치 뒤 모든 입력 | session-intent 훅이 입력을 원장에 기록하고 세션 정보를 대화에 넣음 | 훅 실행기가 `hook command rejected: inner ledger root conflicts with trusted binding`(종료 코드 126)으로 거부. 11-16 15:07 ~ 11-23 11:09(KST)에 session-intent 56번 실행·56번 거부·정상 0번, SessionStart 2종도 23번 거부. 대화에 세션 정보가 없어 경로 등록·검토 기록 불가. 같은 기간 doctor는 `overall: ok` | A (O3과 같은 유형) | 훅 기록으로 확인. 원인: `hook_profile_gate.py`가 `--root`와 바인딩의 원장 경로를 문자열로 비교(O12와 같은 슬래시 차이). 수정은 이 줄 아래 커밋 참고. 이 상태에서 잰 [재측정](metrics/rerun-2026-11-16-main.md)의 "차단 0건"은 개선 근거로 쓸 수 없음. [전체 분석 7장](reports/2026-11-23-full-execution-report.md) |
| O14 | 11-23 | yesan | Windows 11 · main 계열 설치(`skproject` df903bc, O13 수정 반영) · Claude Code(`claude -p`) · claude-opus-5-5 | 일상 질문 D03 "내일 서울 날씨 어때?" | 날씨를 알려 주거나, 확인하지 못했으면 그렇다고 말함 | Ghost-ALICE 켬: 검색 권한이 없어 날씨를 확인하지 못했다고 말하고 기상청을 안내함. 하지만 "Ghost-ALICE 기록(`interpreted-as`)을 남기지 못했다", "`history.md` 기록도 남기지 않았다"는 거버넌스 상태 문장이 답에 섞임. 거버넌스 호출 2번(`session-intent-analyzer` skill, 원장 기록용 PowerShell은 권한 거부), 6턴, $0.32. 끔: 같은 안내만 하고 거버넌스 문장 없음, 3턴, Stop 차단은 켬·끔 모두 0 | D (O6보다 가벼움: 실제 답은 남음) | 1/1. [결과](daily-test/results/20261123-115410.jsonl), [재측정 2장](metrics/rerun-2026-11-23-after-o13.md#2-일상-질문-켬끔). 같은 실행의 다른 5문항 켬 답에는 Ghost-ALICE 기록 실패를 알리는 문장이 없음(답 12개 문자열 검색). 켬 답 6개 모두에 나오는 `history.md`는 공유 기록 규칙이 요구하는 첫 줄과, 질문에 답하려고 공유 기록을 쓴 문장(D07·D10)이며 11-16 실행에도 같은 형태로 있음. D07도 파일 읽기 권한이 거부됐지만 거버넌스 문장은 없었으므로, 원장 기록 명령이 거부될 때 생기는지 반복 확인 필요 |

### 기록에서 뺀 사례

- 처음에는 `criterion-unbound` 안내가 가리키는 `verification-before-completion/references/autopilot-publication.md`가 없다고 판단했습니다. 다시 확인해 보니 파일과 해당 절("Prepare and record the response review")이 모두 있었습니다. skills 폴더가 junction이라 검색 도구가 따라 들어가지 못한 조사 쪽 실수였으므로 사례에서 뺐습니다.

## R3. 분류

| 유형 | 사례 | 반복 조건(지금까지) | 다음 확인 |
| --- | --- | --- | --- |
| A. 거버넌스가 조용히 꺼짐 | O1, O3, O4, O10(후보) | Windows 11 · Claude Code. O1은 비대화형 `claude -p` 입력에서만 확인 | macOS·Linux, Codex에서 같은 절차 실행. 대화형 입력과 비교 |
| C. 완료 판정 오류 | O5 | Stop 훅 Autopilot 어댑터 | 오류 메시지 원문 확보 후 재현 |
| D. 안내 메시지 과다 | O2, O7, O8, O9, O14 | 데스크톱 앱에서 도구를 쓴 입력 다수(11-12 세션 6회, 11-16 세션 2회). O14: main 계열에서 Stop 차단 없이도, 원장 기록 명령이 권한 거부된 `claude -p` 답에 거버넌스 상태 문장이 섞임 | visibility 프로필(현재 `dynamic`)별로 차이가 있는지 비교 |
| E. 반복 검증 루프 | O2(후보) | 같은 세션에서 입력마다 재발 | 경로를 미리 등록하면 사라지는지 확인. 11-16: 미리 등록하면 `route-unavailable`은 사라지지만 explanation에는 `criterion-unbound` 검토가 이어짐(O8). 작업 전 등록 시 Autopilot `prepared` 즉시 통지([증거 E4](evidence/session-2026-11-16-desktop.md#e4-작업-전-등록-순서-r3-e-확인)) |
| B. 이전 의도 재사용 | 없음 | — | 관찰 계속 |

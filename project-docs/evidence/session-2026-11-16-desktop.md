# 2026-11-16 데스크톱 세션 관찰 증거

- 환경: Windows 11 Pro 10.0.26100 · Claude Code 데스크톱 앱(Code 탭, 대화형) · claude-opus-5-5 · Python 3.14 · 한국어 로캘(cp949)
- 설치 런타임: `~/.ghost-alice/runtime/current` (ea22d23의 completion_assessment 수정 반영본)
- 세션: `4f1f262d…` (원장 `<user>\ghost-alice\.tmp\session-intent`, platform `claude`)
- 사용자 이름은 `<user>`로 가렸습니다. 아래 인용은 훅·도구 출력 원문의 해당 줄입니다.

## E1. 읽기 전용 요약 턴에서 Stop 훅 `route-unavailable` (O7)

턴 1 요청: "ghost-alice 관련 작업 내용 정리". 어시스턴트는 공유 기록 파일을 읽는 Bash 2회 후 답을 끝냈고, Stop 훅이 막았습니다.

```text
[completion-gate] route-unavailable: This input contains native tool calls but has no current Core response-route. ...
repair-target: response_route
delivery-route: preserve_answer_and_patch_metadata
```

추가 턴에서 task-router를 실행하고 `response_route.py`로 `response_purpose=explanation` 경로를 등록하자(`status: ready`) 해소됐습니다. 원장 읽기 스크립트 위치를 찾는 데 추가 도구 호출 4회가 들었습니다(`_shared/session_intent_ledger.py`가 없고 `session-intent-analyzer/scripts/`에 있음).

## E2. 설명 답변에 응답 검토 요구 `criterion-unbound` (O8)

턴 3 요청: "전체적으로 한번 더 수행하고 정리". 이번에는 도구 호출 전에 explanation 경로를 등록했습니다(`ready`). 답변 뒤 Stop 훅:

```text
[completion-gate] criterion-unbound: The current-session assistant follows verification-before-completion, references/autopilot-publication.md, section Prepare and record the response review, for this exact explanation and its original sources. ...
repair-target: response_review
```

처리: 답변 원문·원본 출력 사본·주장 목록을 파일로 쓰고 `prepare-response` → 주장별 판정 → `record-response`. 도구 호출 약 10회. 결과는 앞 답변 `status: unsupported`(주장 11개 중 1개 오류: Langfuse 건너뜀 118건을 "이 기간"으로 잘못 귀속), 정정문 `status: reviewed`. 검토가 실제 오류를 잡았습니다.

## E3. 주장 문장 불일치 시 오류 메시지 (O9)

첫 `prepare-response`에서 주장 목록을 답변에서 약간 다듬어(백틱 제거, 항목 합침) 넣었더니:

```json
{"status": "unavailable", "reason": "response-unbound", "detail": "Name each source-backed claim with its exact statement from the explanation draft"}
```

어느 주장이 답변 원문에서 발견되지 않았는지 알려 주지 않아, 11개를 모두 답변 원문 부분 문자열로 바꿔 다시 제출해야 했습니다(두 번째 제출 exit 0).

## E4. 작업 전 등록 순서 (R3 E 확인)

턴 5 요청: "고도화에 적합한 후속조치 진행". 파일을 고치기 전에 원장 기준(U1, D1, D2)과 경로(`execution`, boundary_ref 지정, 작업 단위 2개)를 먼저 등록했습니다. 다음 도구 호출의 PreToolUse 훅이 바로 통지했습니다.

```text
[autopilot]
completion-preflight: prepared
work-unit: utf8-json-reads
work-unit: followup-docs
```

Stop 시 Autopilot 기록이 적용되는지는 이 문서 작성 시점에 아직 모릅니다.

## E5. 체크아웃 브랜치 전환이 설치된 skill을 바꿈 (O10)

`~/.claude/skills`의 Ghost-ALICE skill 폴더는 체크아웃을 가리키는 junction입니다.

```text
<JUNCTION>     task-router [C:\Users\<user>\ghost-alice\task-router]
<JUNCTION>     verification-before-completion [C:\Users\<user>\ghost-alice\coding-convention\verification-before-completion]
<JUNCTION>     boundary-contract [C:\Users\<user>\ghost-alice\boundary-contract]
```

사용자 보고: "새 브랜치에서 작업하면 내용이 이상해진다". 체크아웃에서 브랜치를 바꾸면 실행 중인 세션이 읽는 skill 본문이 그 브랜치 내용으로 바뀝니다. 반면 훅은 복사본(`~/.ghost-alice/runtime/current/_shared`)을 실행하므로, skill 본문과 훅 코드의 버전이 서로 어긋날 수 있습니다.

## E6. hook-monitor Langfuse 전송 잠금 파일 (보조 도구)

```text
-rw-r--r-- 1 <user> 197609 5 2026-11-16_09:54:25 langfuse-hook-send.lock
lock pid=14856  → tasklist: 일치하는 작업 없음
skips since 09:54 today: 13
skip lines by day: 77 (2026-11-13), 45 (2026-11-16)
```

`langfuse_hook_stop.py`는 600초가 지난 잠금을 지우므로 스스로 풀리지만, 그동안의 Stop 훅 전송은 건너뜁니다(커서 덕분에 다음 전송에 포함). 잠금을 만든 프로세스가 `finally`의 잠금 해제 전에 끝난 원인은 확인하지 못했습니다.

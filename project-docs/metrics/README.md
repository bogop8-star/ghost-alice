# 거버넌스 비용 지표

Ghost-ALICE가 대화마다 얼마나 추가 비용을 만드는지 같은 기준으로 재기 위한 도구입니다. 수정 전에 기준값을 남기고, 수정 후 같은 명령으로 다시 재서 비교합니다.

## 실행

```bash
python project-docs/metrics/governance_metrics.py --json project-docs/metrics/baseline-<날짜>.json
```

- 입력: `~/.claude/projects/<폴더>/<세션>.jsonl`(Claude Code 대화 기록). `--projects`로 다른 폴더를 지정할 수 있습니다.
- 출력: 묶음별 요약(표준 출력)과, `--json`을 주면 세션별 행과 요약을 담은 JSON 파일.
- 로컬 파일만 읽고 아무 데이터도 밖으로 보내지 않습니다. 출력에는 세션 ID 앞 8자리와 묶음 이름만 남고, 질문·답변·도구 출력·경로는 남지 않습니다.
- 테스트: `python -m unittest project-docs/metrics/test_governance_metrics.py`(가짜 대화 기록 사용).
- 차단 턴 분류: `python project-docs/metrics/route_block_tools.py [projects 폴더]`는 `route-unavailable` 차단이 난 턴을 그 턴에 쓴 도구로 나눕니다(읽기만 / 읽기+공유 기록 추가 / 셸 기타 / 파일 수정 / MCP 등). 셸 명령의 읽기 전용 판정은 명령 앞부분 허용 목록과 쓰기 흔적 목록으로 추정합니다.

## 지표 정의

| 지표 | 정의 |
| --- | --- |
| `user_turns` | 사람이 입력한 메시지 수. 작업 중에 보낸 메시지(`queued_command`) 포함. 도구 결과·훅 피드백·알림은 제외 |
| `tool_calls` | 어시스턴트의 도구 호출 수(하위 에이전트 제외) |
| `gov_tool_calls` | 거버넌스만을 위한 호출: 거버넌스 skill(`task-router`, `boundary-contract`, `verification-before-completion`, `using-coding-convention`, `session-intent-analyzer`, `merge-companion`, `autopilot-mode`) 호출, 그리고 `session_intent_ledger`·`response_route`·`completion_assessment`·`autopilot`·`pending-merges`를 실행하는 Bash/PowerShell 명령 |
| `stop_blocks` | Stop 훅 차단(`hook_blocking_error`) 수. `[completion-gate] <코드>`에서 사유 코드를 뽑음 |
| `output_tokens` | 어시스턴트 메시지 ID별 출력 토큰 합 |
| 비율 | `blocks_per_turn`, `gov_calls_per_turn`, `gov_share_of_tool_calls`(거버넌스 호출 / 전체 호출), `output_tokens_per_turn` |

묶음(group)은 세션이 실행된 폴더 이름으로 정합니다: `daily-on`/`daily-off`(일상 질문 자동 실행 켬/끔), `ghost-chat-bench`(벤치마크 채점 실행), `life-check`(20문항 점검), `ga-o1`(O1 재현), `ghost-alice`(Core 체크아웃에서 한 대화형 작업), `scratch`(데스크톱 앱 임시 폴더 대화), `other`.

## 한계

- 거버넌스 호출은 skill 호출과 명령 문자열로만 판별합니다. 검토용 파일을 쓰는 Write나 원장 위치를 찾는 탐색 명령은 빠지므로 실제보다 적게 셉니다.
- 비용($)은 대화 기록에 없어서 출력 토큰으로 대신합니다. 입력·캐시 토큰은 세지 않습니다.
- 대화 기록에는 그 세션에서 Ghost-ALICE가 켜져 있었는지가 남지 않습니다. 묶음 이름으로 추정할 뿐이고, `other`·`scratch`에는 훅을 끈 기간의 세션도 섞여 있습니다.
- 여러 날짜와 Ghost-ALICE 버전의 세션이 함께 들어갑니다. 수정 전후 비교는 같은 질문 세트를 같은 방식으로 다시 실행한 묶음끼리 해야 합니다.

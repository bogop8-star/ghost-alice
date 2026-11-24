재현 여부: 한 명(jy)이 한 PC에서 5회 중 5회 재현. 두 번째 재현자는 아직 없음.

양식: Feature request (`.github/ISSUE_TEMPLATE/feature_request.yml`). 읽기도 일반 작업으로 보는 것은 Ghost-ALICE의 설계이므로 버그가 아니라 비용 개선 제안으로 씁니다.

제목: [feature]: Let an input that only reads files finish without route registration

### Problem

파일 하나를 읽고 답하는 입력도 일반 작업(`normal`)으로 분류되어, 응답 경로가 등록돼 있지 않으면 Stop `completion` 훅이 `route-unavailable`로 답변을 한 번 되돌립니다. 그 뒤 응답 모델이 경로 등록을 위해 도구를 추가로 호출합니다. 답은 이미 나와 있는데, 같은 답을 내는 데 드는 도구 호출과 시간이 몇 배로 늘어납니다.

기준 버전(`test-baseline-2026-11-16`, Core `c6019ac` + Autopilot `v0.5.1`), Windows 11 Pro, PowerShell 7.6.10, Claude Code CLI 2.1.310(터미널, 모델 `claude-opus-5-5`, 권한 모드 `auto`), Python 3.14.4에서 쟀습니다.

재현 절차

1. 기준 버전을 설치합니다. 훅 8개가 모두 켜진 상태(`GHOST_ALICE_DISABLED_HOOKS=none`)입니다.

   ```powershell
   cd $HOME
   git clone --branch test-baseline-2026-11-16 https://github.com/bogop8-star/ghost-alice.git ghost-alice
   git clone --branch v0.5.1 https://github.com/AidALL/ghost-alice-autopilot.git ghost-alice-autopilot
   cd $HOME\ghost-alice
   .\install.ps1 -Platform claude -AddonSource $HOME\ghost-alice-autopilot\addons\autopilot-mode
   ```

2. 설치된 작업 폴더에서 `claude --model claude-opus-5-5 --permission-mode auto`로 새 세션을 엽니다.
3. `test-fixture/README.md 파일 맨 위 제목 한 줄만 알려줘.`를 입력합니다. `test-fixture/README.md`는 16줄짜리 Markdown 파일입니다.
4. 답변이 나온 뒤 Stop 훅 출력과 그 뒤의 도구 호출을 봅니다.

측정 결과 (같은 입력, 새 세션 5회)

| | 훅이 되돌린 횟수 | 도구 호출 5회 합계 | 시간 5회 합계 |
| --- | ---: | ---: | ---: |
| 기준 버전 | 5회 중 5회 | 42회 (회차당 6~11회) | 267초 |
| 아래 제안을 적용한 뒤 | 5회 중 0회 | 5회 | 49초 |
| 훅을 끈 폴더의 비슷한 입력(README 제목 읽기) | 없음 | 5회 | 27초 |

- 되돌린 뒤 추가된 호출은 Skill `task-router`와 Bash `session_intent_ledger.py`, `response_route.py`였습니다.
- 훅 켬 세션 109개 전체에서 Stop 훅이 되돌린 89번 중 83번이 `route-unavailable`이었습니다.
- 19개 사례를 5회씩 돌린 합계로는 실패 32회 → 18회, 시간 5,295초 → 3,646초였습니다.

되돌릴 때 나온 메시지

```text
{"decision": "block", "reason": "[completion-gate] route-unavailable: This input contains native tool calls but has no current Core response-route. The current-session assistant follows task-router to register this input's work and response purpose. Retain the tool results; route registration does not require repeating the work. repair-target: response_route\ndelivery-route: preserve_answer_and_patch_metadata\nThe prior answer is visible. The current-session assistant returns only the correction required by the diagnostic, without repeating that answer. This internal record operation requires no new completion controls."}
```

### Proposed solution

그 입력에서 쓴 도구가 모두 읽기 전용이면 `route-unavailable`을 내지 않습니다. 파일을 바꿀 수 있는 호출이 하나라도 있으면 지금과 같이 되돌립니다.

- `_shared/native_transcript.py`의 `native_tool_activity`가 결과에 `read_only` 값을 함께 돌려줍니다.
- `_shared/native_completion.py`의 `assess_native_completion`이 `read_only`이면 이 문제를 내지 않습니다.
- 읽기 전용은 허용 목록으로 판단합니다. Read·Glob·Grep·LS·NotebookRead·Skill·ToolSearch 도구, 읽기 명령만으로 된 Bash·PowerShell 명령, Ghost-ALICE 기록 스크립트 호출만 읽기 전용이고, 목록에 없는 명령·옵션·셸 형태는 모두 작업으로 봅니다.

구현과 테스트는 팀 fork PR #15에 있습니다(새 테스트 17개 통과, 세 모듈을 쓰는 기존 테스트는 고치기 전·후 결과가 같음).

### Affected surface

Hook

### Alternatives considered

- 읽기 전용 입력에는 훅이 경로를 자동으로 등록한다. 응답 모델의 추가 호출은 없어지지만 훅이 원장을 쓰게 됩니다.
- 되돌리지 않고 알림만 남긴다. `main`(AidALL 최신 Core)의 Stop 훅은 이미 이 방식으로 바뀌어 있어, 이 제안은 기준 버전(`v0.5.1` 계열)에 대한 것입니다.
- 명령 문자열을 보는 방식의 한계: 목록에 없는 읽기 명령은 전처럼 되돌려집니다.

### Public boundary

- [ ] This request can be discussed publicly without private data.

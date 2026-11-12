# O1 재현 가이드: `claude -p` 입력이 원장에서 대기 상태로 남음

PRD [R4](../../prd.md#61-작업-절차)에 따라 이 사례가 이슈가 되려면 깨끗한 환경에서 두 명 이상이 재현해야 합니다. 이 폴더는 그 재현을 같은 절차로 돌리기 위한 준비물입니다. 사례 설명은 [observations.md](../../observations.md) O1에 있습니다.

## 무엇을 확인하나

| 입력 방식 | 기대 동작 | 지금까지 관찰된 동작 |
| --- | --- | --- |
| 비대화형 `claude -p "질문"` | 원장 이벤트가 `native-input-staged` → `user-input-observed` → `native-input-resolved`로 이어지고, `intake_status`가 `observed`가 됨 | `native-input-staged` 1건에서 멈추고 `intake_status=pending-native-origin`. 목표·응답 경로 없음 |
| 대화형 Claude Code(대조군) | 위와 같음 | 기대대로 `observed`, 입력마다 `user-input-observed`·`native-input-resolved` 기록 |

## 준비

1. 깨끗한 환경을 준비합니다. 새 OS 사용자 계정, 새 VM, 또는 Ghost-ALICE를 설치한 적 없는 PC 중 하나입니다.
2. Claude Code를 설치하고 로그인합니다.
3. PRD 기준 commit에서 Core와 Autopilot을 함께 설치하고 doctor 결과를 저장합니다. 기준 commit은 PRD 열린 질문에 따라 팀이 정한 값을 씁니다(제안값: Core `v0.5.1`).

```bash
install.cmd --doctor > doctor.txt
```

4. Python 3.11 이상이 있는지 확인합니다. 스크립트는 표준 라이브러리만 씁니다.

## 실행

### 1단계. `claude -p` 재현

```bash
python repro_o1.py --runs 2 --out o1-claude-p.json
```

- 빈 임시 폴더에서 짧은 질문을 `claude -p`로 보냅니다(기본 모델 `haiku`, 실행당 비용 매우 적음).
- 응답의 `session_id`로 Ghost-ALICE 원장을 읽기 전용으로 조회합니다. 원장 위치는 설치기가 `settings.json` 훅 설정에 넣은 값에서 자동으로 찾습니다. 못 찾으면 `--ledger-root`로 지정합니다.
- 화면에 `REPRODUCED` 또는 `NOT_REPRODUCED`가 나옵니다.

### 2단계. 대화형 대조군

1. 빈 폴더에서 `claude`를 대화형으로 실행합니다.
2. 아무 짧은 질문을 하나 입력하고 답을 받은 뒤 `/exit`로 나옵니다.
3. 그 세션 ID로 원장만 확인합니다. 세션 ID는 `~/.claude/projects/<폴더>/` 아래 가장 최근 `.jsonl` 파일 이름입니다.

```bash
python repro_o1.py --check-session-id <세션ID> --out o1-interactive.json
```

대조군은 `NOT_REPRODUCED`가 나와야 정상입니다. 대조군도 `REPRODUCED`라면 `claude -p`만의 문제가 아니라 훅 설치 자체의 문제이므로, 결과를 따로 표시해 주세요.

## 판정 기준

`REPRODUCED`는 아래 네 가지를 모두 만족할 때입니다.

- `intake_status`가 `pending-native-origin`
- 사람 입력으로 확정된 입력 ID(`latest_input_event_id`)가 없음
- 목표(`current_goal`)가 비어 있음
- 응답 경로(`response_route`)가 없음

`NO_LEDGER_ROW`는 원장에 세션 자체가 없다는 뜻입니다. 훅이 실행되지 않은 것이므로 doctor 결과부터 확인합니다.

## 결과 제출

- `o1-claude-p.json`, `o1-interactive.json`, `doctor.txt`를 [observations.md](../../observations.md) O1 행에 링크하고, 재현 여부 칸에 이름과 OS를 적습니다.
- 스크립트는 결과 파일에서 홈 경로와 사용자 이름을 `<home>`, `<user>`로 바꿉니다. `doctor.txt`는 직접 가려야 합니다. 제출 전에 사용자 이름이 남아 있지 않은지 한 번 더 확인합니다.
- 질문 원문은 결과 파일에 넣지 않고 글자 수만 남깁니다.

## 이 PC에서 한 사전 확인(2026-11-12)

깨끗한 환경이 아니라 기존 설치에서 스크립트가 동작하는지만 확인했습니다. PRD R4 통과 근거로는 쓰지 않습니다.

| 실행 | 결과 | 증거 |
| --- | --- | --- |
| `claude -p` 2회 | 2/2 `REPRODUCED`, 이벤트 `native-input-staged` 1건 | [o1-claude-p-2026-11-12.json](../../evidence/o1-claude-p-2026-11-12.json) |
| 대화형 대조군(Claude Code 데스크톱 세션) | `NOT_REPRODUCED`, `intake_status=observed`, 입력마다 `user-input-observed`·`native-input-resolved` | [o1-interactive-control-2026-11-12.json](../../evidence/o1-interactive-control-2026-11-12.json) |

대조군은 CLI 대화형이 아니라 데스크톱 앱 세션이었습니다. 깨끗한 환경 재현에서는 CLI 대화형으로 대조군을 다시 확인합니다.

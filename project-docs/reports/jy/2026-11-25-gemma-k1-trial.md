# #29 비용 비교 시험을 로컬 Gemma로 돌려 본 첫 결과: K1 한 번

Nov 25, 2026 · jy

- 기준 버전: A(JY 방식) Core `core/main` `450e4b3`, Autopilot `v0.5.1`. #29 비용 비교 때 만든 시험용 홈 `~/ga-test/home-a` 를 그대로 썼습니다.
- 모델: Ollama 0.40.17의 `gemma4:e4b` (8.0B, Q4_K_M). 비교 대상은 같은 홈에서 돌린 #29의 `claude-opus-5-5` 결과입니다.
- 확인 환경: Windows 11 Pro (10.0.26200), PowerShell, Python 3.14.4, Claude Code 2.1.332, Intel Core 5 120U, 내장 그래픽(Intel Graphics), 메모리 16GB
- 시험 도구: kyu 시험 키트 [tools/run_case.py](../kyu/evidence/2026-11-24/tools/run_case.py)
- 관련 링크: [A·B 비용 비교 PR #29](https://github.com/bogop8-star/ghost-alice/pull/29), [A·B 비교 시험 안내](../kyu/evidence/2026-11-24/TESTING.md)

## 1. 목표

#29 비용 비교 시험(지시 6개 K1~K6, A·B 각 3회)을 Claude 대신 내 PC의 Gemma로 돌릴 수 있는지 봅니다. 전체를 돌리기 전에, 가장 쉬운 K1을 A에서 한 번만 돌려 동작 여부와 걸리는 시간을 확인했습니다.

## 2. 한 일

1. 받아 둔 모델 두 개를 확인했습니다. `gemma3:4b` 는 Ollama가 밝힌 능력에 도구 사용(tools)이 없어 Claude Code에 쓸 수 없습니다. `gemma4:e4b` 는 도구 사용이 있어 이 모델을 골랐습니다.
2. Ollama가 Claude 방식 요청(`/v1/messages`)에 답하는지 `gemma4:e4b` 로 확인했습니다.
3. 시험용 홈 `home-a`, `home-b` 의 `settings.json` 에 Ollama 주소(`ANTHROPIC_BASE_URL=http://localhost:11434`)를 넣었습니다. `run_case.py` 가 셸의 `ANTHROPIC_*` 값을 지우고 Claude Code를 부르기 때문에, 셸이 아니라 설정 파일에 넣어야 합니다. 원래 파일은 `settings.json.opus` 로 남겨 두었습니다.
4. #29의 Opus 결과 폴더 `runs/a`, `runs/b` 를 `runs/opus-a`, `runs/opus-b` 로 옮겼습니다. 시험 도구가 끝난 실행을 건너뛰기 때문입니다.
5. K1을 A에서 한 번 돌렸습니다(`python run_case.py a K1 1 --model gemma4:e4b`). 첫 시도는 3-2절의 이유로 버리고, Ollama 입력 크기를 65536으로 늘린 뒤 다시 돌렸습니다.

K1의 지시는 "파이썬에서 리스트와 튜플의 차이를 한 줄로 알려줘."이고, 도구 없이 "바꿀 수 있다/없다"는 뜻을 답하면 통과입니다.

## 3. 결과

### 3-1. K1 한 번 (A, 유효한 실행)

| 항목 | Gemma `gemma4:e4b` (1회) | Opus `claude-opus-5-5` (#29, A 3회) |
| --- | --- | --- |
| 통과 | 1/1 | 3/3 |
| 걸린 시간 | 782.4초 (약 13분) | 9.8초, 6.8초, 7.0초 |
| 도구 호출 | 0 | 0 |
| 막힘 | 0 | 0 |
| 입력 토큰 | 25,493 (새로 읽음 9,109 + 캐시 16,384) | - |
| 출력 토큰 | 165 | - |

Gemma의 답: "Python 리스트(`list`)는 요소를 추가, 삭제 또는 수정할 수 있는 **가변(mutable)** 자료형이며, 튜플(`tuple`)은 한 번 생성하면 요소를 변경할 수 없는 **불변(immutable)** 자료형입니다."

- 답은 맞았고, 시험 도구도 통과(`pass: true`)로 판정했습니다.
- 시간은 Opus의 약 80~115배입니다.
- 결과 파일의 금액 `$0.043` 은 실제로 든 돈이 아닙니다. Claude Code가 모르는 모델(`unrecognized_model`)이라 임의 기준으로 매긴 값입니다. 로컬 실행이라 실제 비용은 없습니다.

### 3-2. 버린 첫 시도

| 항목 | 값 |
| --- | --- |
| 통과 | 실패 (`pass: false`) |
| 걸린 시간 | 117.4초 |
| Gemma가 받은 입력 | 2,051토큰 |
| Ollama 입력 크기 | 4,096토큰 (`ollama ps` 의 CONTEXT) |

Ollama의 입력 크기가 4,096토큰이라, Claude Code가 보낸 긴 안내문과 질문이 잘렸습니다. Gemma는 질문을 보지 못하고 "데이터 시각화를 돕겠다"는 엉뚱한 답을 냈습니다. `OLLAMA_CONTEXT_LENGTH=65536` 으로 Ollama를 다시 켠 뒤에는 입력이 잘리지 않았습니다(3-1절). 그래서 이 시도는 결과에 넣지 않았습니다.

## 4. 발견한 문제

| # | 문제 | 근거 | 영향 | 처리 (수정 / 기록만 / 보류) |
| --- | --- | --- | --- | --- |
| 1 | Ollama 기본 입력 크기(4,096토큰)로는 Claude Code 요청이 잘림 | 첫 시도 입력 2,051토큰, 엉뚱한 답, `pass: false` | 질문을 못 보고 틀린 답을 냄 | 수정. `OLLAMA_CONTEXT_LENGTH=65536` 으로 다시 켬 |
| 2 | Gemma가 그래픽카드를 쓰지 않고 CPU로만 돎 | Ollama 상태 `size_vram: 0`, `100% CPU`. 이 PC는 내장 그래픽뿐 | 가장 쉬운 K1에 13분 | 기록만 |
| 3 | `gemma3:4b` 는 도구 사용이 없어 Claude Code 시험에 못 씀 | `ollama show gemma3:4b` 의 능력: completion, vision | 이 PC에서 쓸 수 있는 Gemma는 `gemma4:e4b` 뿐 | 기록만 |
| 4 | 금액 비교를 할 수 없음 | 결과 파일 금액이 임의 값(`unrecognized_model`) | #29의 핵심인 비용 비교 대신 정답·막힘·시간만 비교 가능 | 기록만 |

## 5. 확인하지 못한 것

- K1을 A에서 한 번만 돌렸습니다. B, K2~K6, 반복 3회는 돌리지 않았습니다.
- K1은 도구를 쓰지 않는 문제라, Ghost-ALICE가 막는 일(경로 등록·검토)이 일어나지 않았습니다. Gemma가 Ghost-ALICE 절차를 따라갈 수 있는지는 아직 모릅니다.
- 그래픽카드가 있는 PC에서의 시간은 재지 않았습니다.

## 6. 다음 단계

- 전체(36회)를 돌릴지 정해야 합니다. K1이 가장 쉬운 문제인데도 13분이 걸렸으므로, 같은 PC에서 36회를 돌리면 적어도 약 7.8시간(36 × 13분)이 걸릴 것으로 봅니다. 도구를 쓰는 K2~K6은 K1보다 오래 걸릴 수 있습니다.
- 시험이 끝나면 `runs/a` 를 `runs/gemma-a` 로 옮기고, `runs/opus-a`, `runs/opus-b` 와 `settings.json.opus` 를 원래 이름으로 되돌립니다.

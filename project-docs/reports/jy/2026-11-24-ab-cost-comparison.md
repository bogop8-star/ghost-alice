# JY 방식(A)과 kyu 방식(B) 비용 비교와 B의 Autopilot 완료 조건 확인

Nov 24, 2026 · jy

- 기준 버전: `test-baseline-2026-11-16` 과 다릅니다. A는 Core `core/main` `450e4b3`, B는 Core `kyu/core-review-lite` `15b6e2b`(닫힌 PR #13)입니다. 두 후보의 공통 조상은 기준 커밋 `c6019ac` 이고, 둘 다 Autopilot `v0.5.1` `2075768` 과 시험 전용 패치 `0-test-only-sdk-origin.patch` 를 얹었습니다.
- 확인 환경: Windows 11 Pro 25H2 (10.0.26200.9974), PowerShell 7.6.10, Python 3.14.4, Git 2.55.0, Claude Code CLI 2.1.331 (`claude -p`, 모델 `claude-opus-5-5`, Claude Team 로그인)
- 관련 링크: [A·B 비교 시험 안내](../kyu/evidence/2026-11-24/TESTING.md), [kyu 성능 측정 보고서](../kyu/2026-11-24-performance-measurement.md), [훅 끔·켬·수정 후 비교 테스트](2026-11-24-hook-on-off-fix-test.md), [이슈 1 초안](issues/2026-11-24/1-read-only-input-blocked.md), 증거 [evidence/2026-11-24/ab-test](evidence/2026-11-24/ab-test/)

## 1. 목표

팀 기본으로 둘 방식을 정하려고, 안내서 4절의 JY 담당 시험 두 가지를 제 PC에서 실행합니다.

- 비용 비교: 케이스 6개를 A와 B에서 3회씩 돌립니다.
- Autopilot 확인: 완료 조건이 있는 사례를 B에서 3회 돌려, `route-unavailable` 로 막히는지와 Autopilot 기록이 남는지 봅니다.

결과의 숫자만 적지 않고, 각 막힘과 기록이 어느 코드 때문에 그렇게 나왔는지까지 확인합니다. 결론에는 안내서 6절의 기준을 적용합니다.

## 2. 한 일

- 시험용 홈 `~/ga-test/home-a`, `home-b` 의 인증 상태를 `claude auth status` 로 확인했습니다. 둘 다 로그인이 안 되어 있어 `login_arm.ps1` 로 각각 로그인했습니다. 기존 Claude Code의 인증 정보는 복사하지 않았고, 실제 설치본(`~/.claude`, `~/.ghost-alice`)은 건드리지 않았습니다.
- 두 Core 작업 폴더의 커밋과 시험 전용 패치 적용을 확인했습니다. A와 B 모두 `_shared/native_transcript.py` 한 파일에 16줄이 추가된 상태입니다.
- `python run_batch.py --arms a b --repeats 3 --model claude-opus-5-5` 로 36회를 돌렸습니다(17:44~18:03).
- `python aggregate.py --arms a b` 로 집계했고, 모든 결과 파일(`result-*.json`)의 `modelUsage` 에서 실제 모델 ID를 확인했습니다.
- 완료 조건 사례 AP1을 B에서 3회 실행했습니다(19:15~19:17).
  - 사례 내용: "output/report.txt를 세 줄(alpha, beta, gamma)로 만들고, 완료 조건은 3줄이 있어야 함"
  - 정의: [autopilot-cases.json](evidence/2026-11-24/ab-test/autopilot-cases.json)
- 원인을 찾으려고 다음을 대조했습니다.
  - 기준 커밋 `c6019ac` 대비 A와 B의 코드 차이(`git diff`)
  - 실행마다 Stop 훅이 낸 문구와 그 직전의 도구 호출
  - 훅 기록(`strict-hook-output.jsonl`)의 Autopilot 결과
  - 시험용 장부 DB(`core-a`, `core-b` 의 `.tmp/session-intent/ghost-state.sqlite3`)의 응답 경로와 완료 조건
  - A의 읽기 전용 판별 함수에 실제 실행된 명령을 넣어 본 결과

안내서와 다르게 한 것은 두 가지입니다.

- 모델을 `opus` 대신 `claude-opus-5-5` 로 지정했습니다.
- `--arms a:a b:b` 대신 `--arms a b` 를 썼습니다. 이유는 4절의 6번에 있습니다. 라벨과 홈 이름이 같아 실행 내용은 같습니다.

## 3. 결과

### 3-1. 두 후보가 판정하는 방식

같은 기준 커밋에서 나왔지만, Stop 훅이 무엇을 보고 막는지가 다릅니다.

| 입력 유형 | 기준 `c6019ac` | A (JY, `450e4b3`) | B (kyu, `15b6e2b`) |
| --- | --- | --- | --- |
| 도구 없음 | 통과 | 통과 | 통과 |
| 읽기만 함 | 경로 미등록이면 `route-unavailable` 로 막음 | 모든 도구 호출이 읽기 전용 판별을 통과하면 막지 않고 검토도 하지 않음. 하나라도 통과하지 못하면 기준과 같이 막음 | Core가 Stop에서 경로를 자동 등록. 파일을 바꾸지 않은 턴은 목적이 `explanation` 으로 고정되어 응답 검토를 요구 |
| 파일을 바꿈 | `route-unavailable` 로 막음 | 기준과 같이 막음 | 자동 등록. 모델이 `[purpose: execution]` 을 적었고 Write·Edit를 썼으면 `execution` 으로 등록되어 검토 없음 |
| 완료 조건이 장부에 있음 | 모델이 등록한 경로대로 | 기준과 같음 | 자동 등록하지 않고 기준과 같이 막음 |

관련 코드:

- A: `native_transcript.py` 의 `_read_only_command` 판별기가 판정하고, `native_completion.py` 145행이 그 결과를 보고 막을지 정합니다.
- B: `auto_route.py` 의 `auto_register_route` 와 `turn_purpose` 가 경로를 등록하고, `has_open_criteria` 가 완료 조건이 있는 세션을 제외합니다. 검토 요청은 `quick_review.py` 가 만듭니다.

### 3-2. 비용 비교 (케이스 6개 × 3회 × 2 = 36회)

36회 모두 실제 모델 ID가 `claude-opus-5-5` 였습니다. 결과 파일은 A 24개, B 24개입니다(K6은 입력이 3번이라 실행당 파일 3개). 금액은 Claude Code가 보고한 `total_cost_usd` 입니다.

| 지표 | A (JY 방식) | B (kyu 방식) |
| --- | ---: | ---: |
| 총 금액 | $8.69 | $9.10 |
| 실행당 평균 시간(초) | 30 | 33 |
| 정답 | 18/18 | 18/18 |
| 도구 호출 (관리/전체) | 37/83 | 1/66 |
| Stop 막힘 | 6 | 19 |
| 훅 대기(초) | 84 | 144 |
| 응답 검토 실행 (K2·K3·K4·K6) | 0/12 | 12/12 |
| 미해결 알림으로 통과한 실행 | 3 | 0 |

케이스별 금액(3회 합계)과 막힘 원인은 다음과 같습니다.

| 케이스 | A 금액 | B 금액 | B/A | A 막힘과 원인 | B 막힘과 원인 |
| --- | ---: | ---: | ---: | --- | --- |
| K1 도구 없음 | $0.794 | $0.801 | 1.01 | 없음 | 없음 |
| K2 파일 1개 줄 수 | $1.541 | $1.104 | 0.72 | 3/3 `route-unavailable` (3-3) | 3/3 `response-review-required` |
| K3 파일 5개 읽기 | $0.906 | $1.279 | 1.41 | 없음 (Read만 씀) | 3/3 `response-review-required` |
| K4 근거 설명 | $0.849 | $1.042 | 1.23 | 없음 (Read만 씀) | 3/3 `response-review-required` |
| K5 파일 만들기 | $1.794 | $1.054 | 0.59 | 3/3 `route-unavailable` (Write) | 1/3 `[completion-check]` 형식 오류 |
| K6 입력 3번 | $2.804 | $3.822 | 1.36 | 없음 (Read만 씀) | 9/9 턴 `response-review-required` |

원본 표는 [results-cost.md](evidence/2026-11-24/ab-test/results-cost.md), 회차별 금액은 [batch-a-b.log](evidence/2026-11-24/ab-test/batch-a-b.log)에 있습니다.

### 3-3. 결과가 이렇게 나온 원인

**B가 K3·K4·K6에서 23~41% 비싼 이유: 읽고 답한 턴마다 검토를 한 번씩 합니다.**

- B는 파일을 바꾸지 않은 턴을 모두 `explanation` 으로 등록합니다(`auto_route.turn_purpose`). 모델이 `[purpose: execution]` 이라고 적어도 Write·Edit가 없으면 `explanation` 입니다.
- 그래서 근거 케이스 12회 전부에서 Stop이 `response-review-required` 로 한 번 막고, 모델이 `quick_review.py` 명령 한 번으로 검토를 기록한 뒤 같은 답을 다시 냈습니다.
- A는 이 턴들을 막지도 검토하지도 않습니다. 비용 차이는 검토 비용입니다.

**A가 K2에서 3/3 막힌 이유: 읽기 전용 판별기가 PowerShell 읽기 구문을 모릅니다.**

- 세 회차 모두 첫 도구 호출이 줄 수를 세는 PowerShell 명령이었고, 판별기는 이를 작업으로 판정했습니다.
- 실제 명령을 조각별로 넣어 보니 막힌 이유는 아래 표와 같습니다. 같은 턴의 `wc -l`, `Read`, `Get-Content | Measure-Object` 는 읽기로 판정됐습니다.

| 작업으로 판정된 구문 | 판별기가 막는 이유 |
| --- | --- |
| `if (Test-Path $p) { … }` | 첫 단어 `if` 가 읽기 명령 목록에 없음 (3회 모두) |
| `Where-Object`, `Join-Path`, `Resolve-Path` | 읽기 명령 목록에 없음 |
| `[System.IO.File]::ReadAllText(...)` | `[io.file]::read` 로 시작하는 것만 허용하므로 `System.` 접두어를 막음 |

- 막힌 뒤 모델은 `task-router` 를 읽고 `response_route.py` 를 직접 호출해 경로를 등록했습니다. 관리 도구가 실행당 5번입니다.
- 등록한 목적이 `explanation` 이라 기준 Core 규칙대로 응답 검토가 필요해졌지만, 한 턴에 한 번뿐인 막힘을 이미 써서 "Internal response review remains unresolved" 알림과 함께 통과했습니다. A의 "미해결 알림 3"은 이 세 회입니다.
- kyu도 같은 현상을 3-5절에 "K2 3회 중 2회"로 적었습니다. 그 뒤 들어간 `b03f6dc` 는 쓰기 명령을 막는 수정이라 이 구문들은 여전히 통과하지 못합니다. 제 시험 이슈 1의 사례(제목 한 줄 읽기)는 `head`·`Read` 로 끝나 이 문제가 드러나지 않았습니다.

**A가 K5에서 비싼 이유: 파일을 바꾼 턴은 A에서도 그대로 막힙니다.**

- 파일을 바꾼 턴을 자동 등록하는 구현은 보류하기로 했으므로, A에서는 Write가 있으면 기준과 같이 `route-unavailable` 로 막힙니다.
- 모델이 경로를 직접 등록하느라 관리 도구를 실행당 5~10번 썼습니다.
- B는 Core가 자동 등록해서 관리 도구 없이 끝났습니다. K5 금액 차이(A가 1.7배)가 여기서 나옵니다.

**B의 K5 2회차 막힘: 모델이 쓴 완료 형식 오류입니다.**

- 2회차만 모델이 답에 `[completion-check]` 블록을 넣었는데 `claim-evidence-map` 이 없어서 막혔습니다. 다시 낸 답도 Core가 받지 않아 알림과 함께 통과했습니다.
- 1, 3회차는 블록을 넣지 않아 막히지 않았습니다. 막힘 여부가 모델이 블록을 쓰느냐에 달려 있습니다.

**두 후보의 금액이 kyu 측정보다 큰 이유: 고정 비용이 큽니다.**

- 도구도 막힘도 없는 K1이 실행당 $0.265이고, A와 B가 같습니다.
- 이 중 대부분은 대화 시작 때 문맥 약 32,400토큰을 캐시에 쓰는 비용입니다. 1시간 캐시로 기록됐습니다.
- kyu 측정은 B/A가 1.15였고 이번은 1.05입니다. 고정 비용이 커서 비율이 작아진 것으로 보입니다. 안내서 2절대로 다른 PC의 금액과 직접 비교하지 않았습니다.

### 3-4. Autopilot 완료 조건 확인 (B, AP1 × 3회)

세 번 모두 실제 모델 ID는 `claude-opus-5-5` 였고, 금액 합계는 $1.10입니다. 파일은 3회 모두 정답이었습니다.

| 회차 | 금액 | 시간(초) | `route-unavailable` | Stop 막힘 | 장부의 완료 조건 | 경로 | Autopilot 완료 기록 |
| --- | ---: | ---: | --- | --- | --- | --- | --- |
| 1 | $0.320 | 20 | 없음 | 없음 | 0개 | 자동 등록 `execution`, 작업 단위 0개 | `skipped` (`no-current-execution`) |
| 2 | $0.427 | 35 | 없음 | 1회 (`[completion-check]` 형식) | 0개 | 같음 | `recording-unavailable` (`completion-body-invalid`) |
| 3 | $0.351 | 23 | 없음 | 1회 (`[completion-check]` 형식) | 0개 | 같음 | `recording-unavailable` (`completion-body-invalid`) |

**원인: 모델이 완료 조건을 장부에 등록하지 않아서, B의 제외 조건이 한 번도 작동하지 않았습니다.**

1. B가 "완료 조건이 있으면 자동 등록하지 않고 원래대로 막는다"고 판단하는 근거는 사용자 입력이 아니라 장부의 `acceptance_criteria` 입니다(`auto_route.has_open_criteria`).
2. 장부에 완료 조건을 넣는 것은 모델이 `session_intent_ledger.py` 로 하는 일입니다. B의 입력 안내문은 모델에게 "완료 조건이 있으면 task-router로 조건과 실행 경로를 등록하라"고 적고 있습니다.
3. 그러나 3회 모두 모델은 기록 스크립트를 한 번도 부르지 않았습니다. 첫 줄에 `[purpose: execution]` 만 적고 바로 파일을 만들었습니다.
4. 그래서 장부의 완료 조건은 0개였고, Core가 작업 단위 0개짜리 `execution` 경로를 자동 등록했습니다. 그 결과 `route-unavailable` 이 나오지 않았습니다.
5. Autopilot은 승인된 실행 작업 단위가 든 경로만 기록합니다. 작업 단위가 없으니 1회차는 `no-current-execution` 으로 건너뛰었습니다. 2·3회차는 Core가 답을 막은 상태라 `completion-body-invalid` 였습니다.

같은 일이 A에서는 어떻게 되는지 K5로 확인했습니다. A는 막힌 뒤 모델이 경로를 직접 등록하는데, 3회 중 1회(3회차)는 완료 조건 1개와 작업 단위 `create-hello-txt` 를 함께 등록했고, Autopilot이 그 작업 단위 상태를 확인했습니다(`v2-unit-state`). 나머지 2회는 작업 단위 없이 등록해 B와 같이 `no-current-execution` 이었습니다. A의 막힘은 비용이 들지만, 완료 조건이 장부에 들어갈 기회를 만듭니다. B의 자동 등록은 그 기회를 없앱니다.

kyu 보고서 4절 6번은 "자동 등록 안은 완료 조건이 있는 세션을 제외해야 Autopilot 동작이 유지된다"고 했고, B의 마지막 커밋 `15b6e2b` 가 그 제외를 넣었습니다. 이번 결과는 그 제외가 모델이 먼저 조건을 등록해야만 작동한다는 것을 보여 줍니다.

증거는 [AP1-1-check.json](evidence/2026-11-24/ab-test/AP1-1-check.json), [AP1-2-check.json](evidence/2026-11-24/ab-test/AP1-2-check.json), [AP1-3-check.json](evidence/2026-11-24/ab-test/AP1-3-check.json), [batch-b-autopilot.log](evidence/2026-11-24/ab-test/batch-b-autopilot.log)입니다.

### 3-5. 안내서 6절 기준 적용

| 기준 | 이번 결과 | 판단 |
| --- | --- | --- |
| 비용 비교에서 B가 A보다 30% 넘게 비쌈 | B가 4.8% 비쌈 | 해당하지 않습니다 |
| 검토 효과 시험에서 A는 틀렸는데 B가 검토로 고친 실행이 있음 | 검토 효과 시험(`testbed2`)은 SK 담당이라 돌리지 않았습니다. 비용 비교에서는 B가 막은 19번 모두 답 내용이 그대로였습니다 | 이 시험으로는 판단하지 않습니다 |
| A와 B가 같은 만큼 틀리거나 모두 맞힘 | 위와 같음 | 위와 같음 |

제 담당 범위의 결론은 세 가지입니다.

- 비용 차이는 30% 기준 안쪽입니다. 비용만으로 B를 배제할 이유는 없습니다.
- 두 방식의 비용은 서로 다른 곳에서 듭니다. A는 판별기가 놓친 읽기 명령과 파일을 바꾼 턴에서 경로 등록 비용이 들고, B는 읽고 답한 턴마다 검토 비용이 듭니다.
- B의 자동 등록은 완료 조건이 있는 작업에서 Autopilot이 기록할 조건을 만들지 못했습니다(AP1 3/3). B를 다시 검토한다면 이 문제를 먼저 풀어야 합니다.

## 4. 발견한 문제

| # | 문제 | 근거 | 영향 | 처리 (수정 / 기록만 / 보류) |
| --- | --- | --- | --- | --- |
| 1 | A의 읽기 전용 판별기가 PowerShell 읽기 구문(`if`, `Where-Object`, `Join-Path`, `Resolve-Path`, `[System.IO.File]::Read…`)을 작업으로 판정함 | `runs/a/K2/1~3` 의 PowerShell 명령을 `_read_only_command` 에 조각별로 넣은 결과 | 읽기만 한 K2가 3/3 막히고, 경로 등록에 관리 도구 실행당 5번, 검토 없이 미해결 알림으로 통과. K2에서 A가 B보다 40% 비쌈 | 기록만. 판별기 목록 보강 필요 |
| 2 | B는 완료 조건이 있는 입력도 자동 등록해 `route-unavailable` 로 막지 않음 | AP1 3회 모두 장부 `acceptance_criteria` 0개, 기록 스크립트 호출 0번, 자동 등록 경로의 작업 단위 0개 | 제외 조건(`has_open_criteria`)이 모델의 선행 등록에 의존해 작동하지 않음 | 기록만. kyu에게 전달 |
| 3 | B에서 Autopilot 완료 기록이 3회 모두 남지 않음 | Stop `adapter-autopilot-mode-continue`: `skipped`/`no-current-execution` 1회, `recording-unavailable`/`completion-body-invalid` 2회 | 완료 조건 작업에서 Autopilot이 하는 일이 없음. 원인은 2번 | 기록만 |
| 4 | 모델이 `[completion-check]` 를 스스로 쓰면 형식 오류로 막히고, 고친 답도 받아들여지지 않는 경우가 있음 | B K5 2회차, AP1 2·3회차: `claim-evidence-map` 없음 → 재시도 후 `assessment-required` 또는 항목 누락으로 알림 통과 | 같은 작업도 모델이 블록을 쓰느냐에 따라 막힘과 비용이 달라짐 | 기록만 |
| 5 | B의 막힘 19번은 모두 답 내용을 바꾸지 않음 | `check.json` 의 `blocked_drafts` 와 `answers` 비교. `[purpose: …]` 줄만 빠지고 내용은 같음 | 이 케이스에서는 검토가 비용만 더함. 오답이 나오는 시험이 있어야 효과를 판단할 수 있음 | 기록만 |
| 6 | 안내서의 `--arms a:a b:b` 가 동작하지 않음 | `run_case.py` 의 `--home` 이 `off`, `base`, `imp` 만 받음 | 안내서대로 치면 모든 실행이 인자 오류로 실패 | 보류. 도구는 고치지 않고 `--arms a b` 로 우회 |
| 7 | 실제 비용이 안내서 예상을 넘음 | 비용 비교 $17.79 (예상 $12~15). K1만으로 실행당 $0.265 | 다른 팀원이 예산을 잡을 때 부족할 수 있음 | 기록만 |
| 8 | Autopilot 사례를 `runs/b` 아래에 두면 `aggregate.py --arms a b` 를 다시 돌릴 수 없음 | AP1의 suite가 `autopilot` 이라 기본 시험 자료 폴더에서 찾지 못함 | 비용 집계를 재현하려면 `runs/b/AP1` 을 잠시 옮겨야 함 | 기록만. 집계는 AP1 실행 전에 끝냄 |

## 5. 확인하지 못한 것

- 검토 효과 시험(`testbed2`, 약한 모델)은 실행하지 않았습니다. SK 담당입니다.
- AP1은 B에서만 돌렸습니다. A의 Autopilot 동작은 같은 성격의 K5(3회)로만 확인했습니다.
- 모든 실행이 `claude -p` 자동 실행이었습니다. 사람이 대화형으로 쓸 때 모델이 완료 조건을 등록하는 비율은 다를 수 있습니다.
- 3-3절의 고정 비용 설명(1시간 캐시 쓰기)은 이번 결과 파일로 확인했고, kyu PC의 같은 값은 확인하지 않았습니다.
- AP1 실행을 두 번 도중에 멈췄다가 다시 시작했습니다. 멈춘 실행은 `runs/_aborted/` 로 옮겼고 결과에 넣지 않았습니다. 그 실행에 든 비용은 기록이 없어 합계에 없습니다.
- 금액은 Claude Code가 보고한 정가 기준 값이고, Team 구독의 실제 청구액과는 다릅니다.
- 회차가 3회라서 케이스별 차이의 통계적 유의성은 확인하지 않았습니다.

## 6. 다음 단계

- SK의 검토 효과 시험 결과가 나오면 6절의 첫째·둘째 줄을 적용해 방식을 정합니다.
- A를 유지한다면 읽기 전용 판별기에 PowerShell 읽기 구문을 더하는 것을 검토합니다(4절 1번).
- B를 다시 검토한다면, 완료 조건 판단을 장부가 아니라 입력에서 하거나, 완료 조건이 보이는 입력은 자동 등록하지 않는 방법이 필요합니다(4절 2번). kyu에게 전달합니다.
- '파일을 바꾼 턴 자동 등록' 구현은 계속 보류합니다. 이번 결과에서 자동 등록은 Autopilot 기록 조건을 없앴습니다(3-4절).

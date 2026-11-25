# A·B 비교 시험 안내 (JY 방식 대 kyu 방식)

작성: 2026-11-24 · kyu

`core/main` 에 들어간 JY 방식과 닫힌 PR #13의 kyu 방식 가운데 어느 쪽을 팀 기본으로 둘지 정하려고, 각자 자기 PC에서 같은 시험을 돌리는 방법입니다. kyu PC 결과는 [성능 측정 보고서](../../2026-11-24-performance-measurement.md) 3-5절에 있습니다.

## 1. 비교하는 두 후보

| 후보 | 브랜치 | 커밋 | 특징 |
| --- | --- | --- | --- |
| A: JY 방식 | `core/main` | `450e4b3` | 읽기만 한 턴은 막지 않고 검토도 하지 않음. 파일을 바꾼 턴은 경로 미등록으로 막힘 |
| B: kyu 방식 | `kyu/core-review-lite` | `15b6e2b` | 경로는 Core가 대신 등록. 읽고 알려 주는 답은 명령 한 번으로 검토 |

두 후보 모두 측정용으로만 시험 전용 패치 `patches/0-test-only-sdk-origin.patch` 를 얹습니다. 자동 실행(`claude -p`) 입력을 사람 입력으로 인정하게 하는 패치이고, 팀 브랜치나 PR에는 넣지 않습니다.

## 2. 비교 원칙

- **자기 PC 안에서 A와 B를 비교합니다.** 다른 PC의 숫자와 직접 비교하지 않습니다. PC와 날짜에 따라 금액의 절대값이 달라지기 때문입니다.
- A와 B 사이에서는 다음이 같아야 합니다: 모델, 케이스와 시험 자료, 시험 전용 패치, Claude Code와 Python 버전(측정 중 업데이트하지 않기), 실행 순서(도구가 A와 B를 번갈아 돌림).
- **실제 설치본(`~/.claude`, `~/.ghost-alice`, 설치에 쓴 Core 폴더)은 건드리지 않습니다.** 모든 설치와 실행은 시험용 폴더(`~/ga-test`) 안에서만 합니다.
- 결정 기준은 시험 전에 정해 두었습니다(아래 6절). 결과를 보고 기준을 바꾸지 않습니다.

## 3. 준비 (한 번만)

PowerShell 7에서 실행합니다. 경로는 기본값 `~/ga-test` 를 씁니다. 다른 폴더를 쓰려면 `GA_TEST_ROOT` 환경 변수를 지정합니다.

```powershell
$T = Join-Path $HOME 'ga-test'
New-Item -ItemType Directory -Force "$T\src" | Out-Null
cd "$T\src"
git clone https://github.com/bogop8-star/ghost-alice.git team
git clone --branch v0.5.1 https://github.com/AidALL/ghost-alice-autopilot.git autopilot
cd team
git fetch origin core/main kyu/core-review-lite
git worktree add ..\core-a origin/core/main
git worktree add ..\core-b origin/kyu/core-review-lite
$K = "$T\src\team\project-docs\reports\kyu\evidence\2026-11-24"
cd ..\core-a; git apply "$K\patches\0-test-only-sdk-origin.patch"
cd ..\core-b; git apply "$K\patches\0-test-only-sdk-origin.patch"
```

`git apply` 가 실패하면 패치 파일의 줄바꿈이 CRLF로 바뀐 것입니다. 이 폴더의 `.gitattributes` 가 LF로 받게 하므로, 팀 저장소를 새로 받으면 해결됩니다.

시험용 홈 두 개에 설치합니다. `-AddonSource` 에 해당하는 `-Addon` 은 Autopilot 저장소 맨 위 폴더입니다.

```powershell
cd $K\tools
pwsh -NoProfile -File .\install_arm.ps1 -Arm a -Core "$T\src\core-a" -Addon "$T\src\autopilot"
pwsh -NoProfile -File .\install_arm.ps1 -Arm b -Core "$T\src\core-b" -Addon "$T\src\autopilot"
```

훅이 쓸 Python은 PATH의 `python` 입니다. 다른 Python을 쓰려면 `-PythonDir <폴더>` 를 붙입니다. 설치 결과 끝에 `[5/5] Verification ok` 가 나오면 됩니다.

각 시험용 홈에서 Claude에 한 번씩 로그인합니다. **새 PowerShell 창**에서 실행하고, 끝나면 그 창을 닫습니다(그 창의 환경 변수가 시험용 홈을 가리키기 때문입니다).

```powershell
& "$K\tools\login_arm.ps1" -Arm a    # /login 입력, 브라우저에서 로그인, /exit
& "$K\tools\login_arm.ps1" -Arm b
```

## 4. 시험 실행

`run_batch.py` 는 `run_case.py` 를 불러 케이스를 실행하고, 결과를 `~/ga-test/runs/<라벨>/<케이스>/<회차>/` 에 남깁니다. 중간에 멈춰도 다시 실행하면 끝난 실행은 건너뜁니다. `--arms 라벨:홈` 에서 라벨은 결과 이름, 홈은 위에서 설치한 시험용 홈 이름입니다(`install_arm.ps1 -Arm a` 로 만든 홈은 `a`). 라벨과 홈 이름이 같으면 `--arms a b` 처럼 홈을 생략해도 됩니다. 홈이 없으면 `run_case.py` 가 실행 폴더를 만들기 전에 "test home not found" 로 멈춥니다.

> 2026-11-25 수정: 처음 올린 키트의 `run_case.py` 는 홈 이름으로 `off`, `base`, `imp` 만 받아서 아래 `a:a b:b` 명령이 인자 오류로 실패했습니다(JY #29, SK #31 보고). 지금은 설치된 홈 이름을 모두 받습니다. 한국어 Windows에서 한국어 답이 나오면 `run_batch.py` 가 멈추던 문제와, `testbed2` T7 채점이 "나와 있지 않습니다" 같은 정답을 틀렸다고 보던 문제(둘 다 SK #31 보고)도 고쳤습니다.

**비용 비교 (JY 담당).** 케이스 6개 × 3회, Opus입니다. 예상 비용은 약 $12~15입니다.

```powershell
cd $K\tools
python run_batch.py --arms a:a b:b --repeats 3 --model opus
python aggregate.py --arms a b --out "$T\results-cost.md"
```

**검토 효과 (SK 담당).** 함정 케이스 10개(`testbed2`) × 3회를 약한 모델로 돌립니다. 검토가 오류를 잡는지 보려면 틀린 답이 나와야 하기 때문입니다. 예상 비용은 약 $5~10입니다.

```powershell
cd $K\tools
python run_batch.py --arms ta:a tb:b --repeats 3 --suite testbed2 --model haiku
python aggregate.py --arms ta tb --out "$T\results-trap.md"
```

Haiku에서 거의 다 틀리면 `--model sonnet` 으로 한 번 더 돌립니다(라벨을 `sa:a sb:b` 처럼 바꿉니다). 함정별 정답은 `testbed2/truth.json` 과 `testbed2/cases.json` 의 `trap` 항목에 있습니다.

**Autopilot 확인 (JY 담당, 선택).** 완료 조건이 있는 케이스를 하나 만들어 B에서 3회 돌립니다. 예: "완료 조건: output/report.txt 에 3줄이 있어야 함". 확인할 것은 두 가지입니다. 하나는 이 경우 B가 자동 등록 없이 전처럼 `route-unavailable` 로 막는지, 다른 하나는 Autopilot 기록이 남는지입니다.

## 5. 결과로 알려 줄 것

- 사용한 환경: Windows 빌드, Claude Code 버전, Python 버전, 모델
- `aggregate.py` 가 만든 표(조건별 합계와 케이스별 금액). 총 금액, 실행당 시간, 정답 수, Stop 막힘, 응답 검토 실행, 검토된 답 그대로 전달
- 검토 효과 시험: **A에서 틀렸는데 B에서 검토 뒤 맞힌 실행**의 케이스와 회차. 각 실행 폴더의 `check.json` 에 있는 `blocked_drafts`(막히기 전 첫 답)와 `answers`(최종 답)를 비교하면 검토가 답을 고쳤는지 보입니다.
- 보고서는 팀 양식 [`TEMPLATE.md`](../../../TEMPLATE.md) 대로 `project-docs/reports/<이름>/` 에 올립니다. 실행 폴더 전체는 올리지 않고, 표와 해당 실행의 `check.json` 만 증거로 붙입니다.

## 6. 결정 기준 (시험 전 합의)

| 결과 | 결정 |
| --- | --- |
| 검토 효과 시험에서 A는 틀렸는데 B가 검토로 고친 실행이 있음 | kyu 방식 채택을 제안합니다. 검토가 실제로 오류를 막는다는 근거가 생깁니다 |
| A와 B가 같은 만큼 틀리거나 모두 맞힘 | JY 방식을 유지합니다. 검토 비용만 들고 효과가 없습니다 |
| 비용 비교에서 B가 A보다 30% 넘게 비쌈 | 위 결과와 함께 다시 논의합니다 |

## 7. 문제가 생기면

- `run_case.py` 가 `claude` 를 찾지 못하면 Claude Code CLI가 PATH에 있는지 확인합니다.
- 실행마다 막힘이 반복되고 정답이 나오지 않으면, 시험 전용 패치가 두 후보 모두에 들어갔는지 확인합니다(`git -C <core 폴더> diff --stat`).
- 시험 자료 `testbed/fixture/README.md.txt` 는 실행할 때 자동으로 `README.md` 로 바뀌어 복사됩니다. 저장소의 문서 형식 검사를 피하려고 이름만 바꿔 둔 것입니다.

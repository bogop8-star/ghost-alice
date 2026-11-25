# Ghost-ALICE A·B 시험 재현 안내 1: 자동 실행

JY가 자동 실행(`claude -p`)으로 돌린 A·B 시험을 내 PC에서 똑같이 해 보는 방법입니다. 순서대로 복사해서 붙여 넣기만 하면 됩니다.

같은 지시 6개를 A와 B에 3번씩, 모두 36번 컴퓨터가 알아서 돌리고 정답·막힘·금액을 비교합니다. 준비 15분, 시험 30분 정도 걸립니다.

- A (JY 방식): 읽기만 한 답은 멈추지 않음. 파일을 바꾼 답은 한 번 멈추고 한국어로 이유를 알려 줌. 팀 저장소 `core/main` 의 `450e4b3`.
- B (kyu 방식): 기록은 Ghost-ALICE가 대신 써 줌. 대신 읽고 답하면 한 번 검토를 시킴. `kyu/core-review-lite` 의 `15b6e2b`.

## 왜 재현 방법이 두 가지인가

같은 A·B 시험인데 재현 방법이 "1: 자동 실행"과 "2: 대화형 실행" 두 가지입니다. Claude에 지시를 넣는 방법이 달라서입니다.

Ghost-ALICE는 사람이 입력한 말인지 확인한 뒤에야 작업 기록을 남깁니다. 그런데 자동 실행(`claude -p`)으로 넣은 입력은 출처가 "sdk"로 찍혀 사람 입력으로 인정받지 못합니다. 이 문제를 푸는 방법이 두 가지입니다.

| | 1: 자동 실행 (이 문서) | 2: 대화형 실행 |
| --- | --- | --- |
| 지시를 넣는 방법 | `claude -p` 로 화면 없이 넣음 | Claude 대화 화면을 띄우고, 실행기가 키보드로 친 것처럼 넣음 |
| 사람 입력으로 인정받는 방법 | 시험 전용 패치(`0-test-only-sdk-origin.patch`)가 자동 입력도 사람 입력으로 쳐 줌 | 실제 키 입력이라 그대로 사람 입력으로 인정됨 |
| 좋은 점 | 빠르고(약 30분), 결과에 금액이 남음 | 실제 사용과 가까움. Ghost-ALICE 코드를 고치지 않아도 됨 |
| 한계 | Ghost-ALICE 코드를 시험용으로 고친 상태에서 잼 | 오래 걸리고(약 1시간 30분), 금액은 집계하지 않음. 도는 동안 창을 건드리면 안 됨 |

JY는 11-24에 1번 방법으로, 11-25에 2번 방법으로 시험했습니다.

키 입력 실행기를 만든 이유는 하나 더 있습니다. 11-24 훅 끔·켬 시험에는 Claude가 일하는 도중에 Esc를 눌러 멈추고 지시를 바꾸는 사례("지시 변경")가 있었습니다. 자동 실행으로는 일하는 도중에 Esc를 넣을 수 없어서, 사람이 누르는 것처럼 Esc를 넣으려고 실행기(`tui_runner.py`)를 만들었습니다. 2번의 실행기(`ab_runner.py`)는 이 실행기의 키 입력 방식을 그대로 가져다 씁니다. 11-25 시험의 지시 12개에는 Esc를 쓰는 사례가 없습니다.

## 0. 꼭 지킬 것

- 내가 평소 쓰는 Claude 설정(`~/.claude`, `~/.ghost-alice`)은 건드리지 않습니다. 모든 시험은 `~/ga-test` 라는 시험용 폴더 안에서만 합니다.
- 시험 중에는 Claude Code나 Python을 업데이트하지 않습니다.

## 1. 준비물

- Windows 11, PowerShell 7 (`pwsh`), Python 3, Git, Claude Code (`claude` 명령)
- Claude 계정 (Team 또는 유료 요금제). 정가 기준으로 약 $18이 들었습니다.

설치됐는지 확인합니다. 네 줄 모두 버전이 나오면 됩니다.

```powershell
pwsh --version
```

```powershell
python --version
```

```powershell
git --version
```

```powershell
claude --version
```

## 2. 한 번만 하는 준비 (약 15분)

### 2-1. 내려받기

PowerShell 7 창을 열고 아래를 통째로 붙여 넣습니다.

```powershell
$T = Join-Path $HOME 'ga-test'
New-Item -ItemType Directory -Force "$T\src" | Out-Null
cd "$T\src"
git clone https://github.com/bogop8-star/ghost-alice.git team
git clone --branch v0.5.1 https://github.com/AidALL/ghost-alice-autopilot.git autopilot
cd team
git fetch origin core/main kyu/core-review-lite
git worktree add ..\core-a 450e4b3
git worktree add ..\core-b 15b6e2b
$K = "$T\src\team\project-docs\reports\kyu\evidence\2026-11-24"
cd ..\core-a; git apply "$K\patches\0-test-only-sdk-origin.patch"
cd ..\core-b; git apply "$K\patches\0-test-only-sdk-origin.patch"
```

- `core-a` 가 A, `core-b` 가 B입니다.
- 마지막 패치는 "자동으로 넣은 입력도 사람 입력으로 쳐 줘"라는 시험 전용 수정입니다. 팀 코드에는 넣지 않습니다.
- `git apply` 에서 오류가 나면 팀 저장소를 지우고 다시 받습니다.

### 2-2. 시험용 설치 두 개 만들기

같은 창에 이어서 붙여 넣습니다.

```powershell
cd $K\tools
pwsh -NoProfile -File .\install_arm.ps1 -Arm a -Core "$T\src\core-a" -Addon "$T\src\autopilot"
pwsh -NoProfile -File .\install_arm.ps1 -Arm b -Core "$T\src\core-b" -Addon "$T\src\autopilot"
```

각각 끝에 `[5/5] Verification ok` 가 나오면 성공입니다. `~/ga-test/home-a`, `~/ga-test/home-b` 라는 시험용 홈이 생깁니다.

### 2-3. 로그인 두 번 (a, b)

아래 한 줄마다 새 PowerShell 7 창을 열어서 실행합니다. Claude가 뜨면 `/login` 을 입력하고, 브라우저에서 로그인한 뒤 `/exit` 로 나옵니다. 끝나면 그 창은 닫습니다.

```powershell
& "$HOME\ga-test\src\team\project-docs\reports\kyu\evidence\2026-11-24\tools\login_arm.ps1" -Arm a
```

```powershell
& "$HOME\ga-test\src\team\project-docs\reports\kyu\evidence\2026-11-24\tools\login_arm.ps1" -Arm b
```

## 3. 시험 돌리기

새 PowerShell 7 창에서 붙여 넣습니다.

```powershell
Remove-Item Env:GA_TEST_ROOT, Env:GA_PERF_DIR -ErrorAction SilentlyContinue
cd "$HOME\ga-test\src\team\project-docs\reports\kyu\evidence\2026-11-24\tools"
python run_batch.py --arms a b --repeats 3 --model claude-opus-5-5
python aggregate.py --arms a b --out "$HOME\ga-test\results-cost.md"
```

- 안내서(TESTING.md)에 적힌 `--arms a:a b:b` 는 오류가 납니다. 위처럼 `--arms a b` 로 씁니다.
- 도중에 끊겨도 같은 명령을 다시 넣으면 끝난 것은 건너뛰고 이어서 합니다.

## 4. 결과 보기

결과는 `~/ga-test/results-cost.md` 에 표로 나옵니다. A와 B의 총 금액, 정답 수, 막힘 수를 봅니다.

| 항목 | A | B |
| --- | --- | --- |
| 총 금액 | $8.69 | $9.10 |
| 정답 | 18/18 | 18/18 |
| 막힘 | 6번 | 19번 |

위는 JY 결과입니다. 금액은 PC와 날짜마다 달라지므로 A와 B의 차이만 비교합니다.

## 5. 막히면

- `run_batch.py` 가 `claude` 를 못 찾음: `claude --version` 이 되는 창에서 다시 실행합니다.
- 매번 막히고 정답이 안 나옴: 패치가 들어갔는지 봅니다. 아래 두 줄 모두 파일 이름이 나와야 합니다.

```powershell
git -C "$HOME\ga-test\src\core-a" diff --stat
```

```powershell
git -C "$HOME\ga-test\src\core-b" diff --stat
```

## 6. 다 끝나면

- 시험용 폴더 `~/ga-test` 는 지워도 평소 설정에 영향이 없습니다.
- 결과표와 사용한 환경(Windows 버전, `claude --version`, `python --version`, 모델)을 팀에 공유합니다.

## 참고

- kyu 시험 안내서: 팀 저장소 `project-docs/reports/kyu/evidence/2026-11-24/TESTING.md`
- 결과 요약 화면: `pr#29-1124테스트(kyu요청).html`

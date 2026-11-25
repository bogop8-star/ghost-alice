# Ghost-ALICE A·B 시험 재현 안내 2: 대화형 실행

JY가 대화형으로 돌린 A·B 시험을 내 PC에서 똑같이 해 보는 방법입니다. 순서대로 복사해서 붙여 넣기만 하면 됩니다.

터미널에 Claude 대화 화면을 띄우고, 실행기(`ab_runner.py`)가 키보드를 대신 눌러 지시를 넣습니다. 사람은 명령만 넣고 기다리면 됩니다. 같은 지시 12개를 세 환경에 넣고 정답·막힘·시간을 비교합니다.

| 환경 | 뜻 |
| --- | --- |
| off | Ghost-ALICE가 없는 Claude. 기준선 |
| a (JY 방식) | 읽기만 한 답은 멈추지 않음. 파일을 바꾼 답은 한 번 멈추고 한국어로 이유를 알려 줌. 팀 저장소 `core/main` 의 `450e4b3` |
| b (kyu 방식) | 기록은 Ghost-ALICE가 대신 써 줌. 대신 읽고 답하면 한 번 검토를 시킴. `kyu/core-review-lite` 의 `15b6e2b` |

준비 20분, 시험 약 1시간 30분이 걸립니다(JY PC 기준: off 6분, a 41분, b 42분).

## 왜 재현 방법이 두 가지인가

같은 A·B 시험인데 재현 방법이 "1: 자동 실행"과 "2: 대화형 실행" 두 가지입니다. Claude에 지시를 넣는 방법이 달라서입니다.

Ghost-ALICE는 사람이 입력한 말인지 확인한 뒤에야 작업 기록을 남깁니다. 그런데 자동 실행(`claude -p`)으로 넣은 입력은 출처가 "sdk"로 찍혀 사람 입력으로 인정받지 못합니다. 이 문제를 푸는 방법이 두 가지입니다.

| | 1: 자동 실행 | 2: 대화형 실행 (이 문서) |
| --- | --- | --- |
| 지시를 넣는 방법 | `claude -p` 로 화면 없이 넣음 | Claude 대화 화면을 띄우고, 실행기가 키보드로 친 것처럼 넣음 |
| 사람 입력으로 인정받는 방법 | 시험 전용 패치(`0-test-only-sdk-origin.patch`)가 자동 입력도 사람 입력으로 쳐 줌 | 실제 키 입력이라 그대로 사람 입력으로 인정됨 |
| 좋은 점 | 빠르고(약 30분), 결과에 금액이 남음 | 실제 사용과 가까움. Ghost-ALICE 코드를 고치지 않아도 됨 |
| 한계 | Ghost-ALICE 코드를 시험용으로 고친 상태에서 잼 | 오래 걸리고(약 1시간 30분), 금액은 집계하지 않음. 도는 동안 창을 건드리면 안 됨 |

JY는 11-24에 1번 방법으로, 11-25에 2번 방법으로 시험했습니다. 11-25 시험은 11-24에 만든 시험용 설치본을 그대로 써서 패치가 들어 있었습니다. 이 문서도 JY와 같게 맞추려고 2-1에서 패치를 넣습니다.

키 입력 실행기를 만든 이유는 하나 더 있습니다. 11-24 훅 끔·켬 시험에는 Claude가 일하는 도중에 Esc를 눌러 멈추고 지시를 바꾸는 사례("지시 변경")가 있었습니다. 자동 실행으로는 일하는 도중에 Esc를 넣을 수 없어서, 사람이 누르는 것처럼 Esc를 넣으려고 실행기(`tui_runner.py`)를 만들었습니다. 이 문서의 실행기(`ab_runner.py`)는 그 키 입력 방식을 그대로 가져다 씁니다. 11-25 시험의 지시 12개에는 Esc를 쓰는 사례가 없습니다.

## 0. 꼭 지킬 것

- 내가 평소 쓰는 Claude 설정(`~/.claude`, `~/.ghost-alice`)은 건드리지 않습니다. 시험용 설치는 `~/ga-test` 안에만 둡니다.
- 시험 작업 폴더는 `C:\ga-work` 입니다. 내 사용자 폴더(`C:\Users\이름`) 안에 두면 평소 설정이 딸려 들어와 결과가 섞여서, 실행기가 이 위치로 정해 두었습니다.
- 실행기는 키보드 입력을 대신 넣습니다. 시험이 도는 동안 그 창에 아무것도 입력하지 않습니다.
- 시험 중에는 Claude Code나 Python을 업데이트하지 않습니다.

## 1. 준비물

- Windows 11, PowerShell 7 (`pwsh`), Python 3, Git, Claude Code (`claude` 명령)
- Claude 계정 (Team 또는 유료 요금제)

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

## 2. 한 번만 하는 준비 (약 20분)

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
- 마지막 패치는 JY가 시험한 설치본과 똑같이 맞추려고 넣습니다. 팀 코드에는 넣지 않습니다.

### 2-2. 시험용 설치 두 개 만들기

같은 창에 이어서 붙여 넣습니다.

```powershell
cd $K\tools
pwsh -NoProfile -File .\install_arm.ps1 -Arm a -Core "$T\src\core-a" -Addon "$T\src\autopilot"
pwsh -NoProfile -File .\install_arm.ps1 -Arm b -Core "$T\src\core-b" -Addon "$T\src\autopilot"
```

각각 끝에 `[5/5] Verification ok` 가 나오면 성공입니다. off 환경은 설치하지 않습니다(Ghost-ALICE가 없어야 하므로).

### 2-3. 실행기 위치

실행기는 2-1에서 받은 팀 저장소 안에 있습니다. 따로 받을 것은 없습니다.

실행기 위치는 `~/ga-test/src/team/project-docs/reports/jy/evidence/2026-11-25/runner` 입니다. 실행기는 PATH에 있는 `claude` 를 씁니다.

### 2-4. 로그인과 작업 폴더 허락 (off, a, b 세 번)

실행기는 시작 전에 세 환경이 모두 로그인돼 있고, 각 작업 폴더를 "신뢰한다"고 허락해 두었는지 확인합니다. 아래 한 줄마다 새 PowerShell 7 창을 열어서 실행합니다.

```powershell
$Arm = 'off'
```

```powershell
$Arm = 'a'
```

```powershell
$Arm = 'b'
```

위 세 줄 중 하나를 넣은 뒤, 같은 창에 아래를 붙여 넣습니다.

```powershell
$H = "$HOME\ga-test\home-$Arm"; New-Item -ItemType Directory -Force "$H\.claude", "C:\ga-work\$Arm" | Out-Null
Get-ChildItem Env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC|GHOST_ALICE|LANGFUSE)' } | ForEach-Object { Remove-Item "Env:$($_.Name)" }
$env:HOME = $H; $env:USERPROFILE = $H; $env:CLAUDE_CONFIG_DIR = "$H\.claude"; $env:GHOST_ALICE_GHOST_ROOT = "$H\.ghost-alice"
cd "C:\ga-work\$Arm"; claude
```

Claude가 뜨면:

1. "이 폴더를 신뢰하느냐"는 질문이 나오면 허락합니다.
2. `/login` 을 입력하고 브라우저에서 로그인합니다.
3. `/exit` 로 나옵니다. 그 창은 닫습니다.

## 3. 시험 돌리기

새 PowerShell 7 창(Windows 터미널이나 PowerShell 창. 편집기 안의 터미널 말고)에서 붙여 넣습니다.

```powershell
cd "$HOME\ga-test\src\team\project-docs\reports\jy\evidence\2026-11-25\runner"; python ab_runner.py --list
```

지시 12개 목록이 나오면 준비가 된 것입니다. 이어서 전체를 돌립니다.

```powershell
python ab_runner.py
```

- 처음에 세 환경을 확인하고, 문제가 있으면 "환경이 맞지 않아 시작하지 않습니다"와 함께 이유를 보여 주고 멈춥니다. 그 이유대로 2절을 다시 합니다.
- off → a → b 순서로, 환경마다 지시 12개를 돌립니다. 1번 지시는 1번, 나머지는 3번씩입니다.
- 지시 하나만 먼저 해 보려면 `python ab_runner.py --cases c01` 처럼 번호를 붙입니다.

## 4. 결과 보기

끝나면 창에 회차별 결과가 나옵니다. 자세한 기록은 `~/ga-test/테스트결과/ab/results.jsonl` 에 한 회차 한 줄로 남습니다.

JY 결과와 비교할 것:

| 지시 | off | a | b |
| --- | --- | --- | --- |
| c02 README 읽기 | 3/3 정답 | 3/3 정답, 안 멈춤 | 3/3 정답, 매번 검토로 멈춤 |
| c03 파워셸 줄 수 | 3/3 | 3/3, 읽기인데 멈춤 | 3/3, 검토로 멈춤 |
| c04 hello 파일 | 3/3 | 3/3, 쓰기라 멈춤 | 3/3, 안 멈춤 |
| c05 막힘 문구 | 멈춤 없음 | 3/3 한국어 안내 | 0/3 (영어뿐) |
| c06·c07 완료 조건 | 파일 맞음 | 완료 기록 0 | 완료 기록 0 |
| c08·c09 함정 | 정답 | 정답 | 정답 |
| c10 만들지 마 | 지킴 | 3/3 지킴 | 1/3 (2번 어김) |
| c11 넘겨받기 | 0/3 | 1/3 | 3/3 |
| c12 다음 세션 | 2/3 | 0/3 | 0/3 |

## 5. 막히면

- "로그인이 안 돼 있음": 2-4를 그 환경으로 다시 합니다.
- "작업 폴더 신뢰 표시가 없음": 2-4에서 신뢰 질문에 허락하지 않은 것입니다. 다시 합니다.
- "설치된 커밋이 …가 아님": 2-2를 다시 합니다.
- "작업 폴더 윗쪽에 설정이 있음": `C:\` 나 `C:\ga-work` 에 `.claude` 폴더나 `CLAUDE.md` 가 있는 것입니다. 옮기고 다시 합니다.
- Claude 창이 뜨지 않음: 그 창에서 `claude --version` 이 되는지 봅니다.

## 6. 다 끝나면

- `~/ga-test`, `C:\ga-work` 는 지워도 평소 설정에 영향이 없습니다.
- 결과와 사용한 환경(Windows 버전, `claude --version`, `python --version`)을 팀에 공유합니다.

## 참고

- JY 보고서: 팀 저장소 `project-docs/reports/jy/2026-11-25-hook-off-a-b-comparison.md`
- 결과 요약 화면: `pr#32-1125테스트(jy자체-추가분).html`

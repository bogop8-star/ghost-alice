# 설계: Ghost-ALICE Autopilot Windows 검증 (단점 6번 개선)

- 작성: 2026-11-18 · 기준: `test-baseline-2026-11-16` (Core `c6019ac`, Autopilot `v0.5.1` `2075768`)
- 상태: 초안. kyu 확인 대기 항목은 7절에 있습니다.

## 1. 목표

Autopilot 0.5.1이 Windows에서 동작한다는 것을 테스트 결과로 보여 주고, 그 근거를 `compatibility-matrix.json` 에 남깁니다. AidALL 공식 업데이트는 따라가지 않고 11/12 설치 기준에서만 검증합니다.

| 범위 | 내용 |
|---|---|
| A-1 | Windows 전체 테스트 실패 원인을 정리하고, 고칠 수 있는 것은 고칩니다 |
| A-2 | `compatibility-matrix.json` 의 Windows 항목(CMD, PowerShell 5, PowerShell 7)을 실제 실행 근거로 채웁니다 |
| A-3 (선택) | GitHub Actions에 Windows 실행을 추가합니다 |

## 2. 하지 않는 것

- 현재 설치본(`C:\Users\N-\ghost-alice`, `C:\Users\N-\ghost-alice-autopilot`)의 브랜치·파일은 바꾸지 않습니다. 재설치하지 않습니다.
- AidALL 공식 main의 새 코드는 반영하지 않습니다.
- Core 쪽 Windows 문제(예: `completion_assessment.py` 가 한국어 파일을 cp949로 읽어 실패, `PYTHONUTF8=1` 로 우회됨)는 기록만 하고 이번 범위에서 고치지 않습니다.
- Linux 항목(`os-linux`)은 이번 범위가 아닙니다.

## 3. 작업 위치

| 항목 | 값 |
|---|---|
| 개발 폴더 | `C:\Users\N-\ghost-alice-autopilot-win` (설치 폴더의 git worktree) |
| 브랜치 | `windows-verify` (`v0.5.1` 에서 출발) |
| 테스트용 Core | `C:\Users\N-\ghost-alice` 를 읽기 전용으로 사용 (`GHOST_ALICE_CORE_ROOT`) |
| 이전 작업 | 설치 폴더 `test/windows-compat` 의 커밋 안 된 4개 파일을 개발 폴더로 복사함. 설치 폴더 원본은 그대로 둠 |
| 올릴 저장소 | 기존 팀 저장소 `bogop8-star/ghost-alice` (Core 팀 저장소, jy·sk 협업자 설정됨). 새 fork는 만들지 않음 (2026-11-18 kyu 결정) |
| 저장소 브랜치 | `autopilot/main` = `v0.5.1` (`2075768`) 그대로, `autopilot/windows-verify` = 이번 작업. Core 브랜치(`main`, `kyuproject` 등)와 Git 기록이 이어져 있지 않음 |
| PR | `autopilot/windows-verify` → `autopilot/main`. 대상 브랜치를 Core `main` 이 아니라 `autopilot/main` 으로 지정 |

설치 폴더는 같은 커밋(`2075768`)을 유지하므로 어댑터 지문이 바뀌지 않습니다.

## 4. 구성 요소

### 4.1 Windows 테스트 실행기 (`scripts/run_windows_tests.ps1`)

- 역할: POSIX CI와 같은 명령으로 전체 테스트를 Windows에서 돌립니다. UTF-8 모드, Git `env.exe` 경로, Core 위치를 맞춥니다.
- 고칠 점: PowerShell 5에서 pytest가 없으면 `$ErrorActionPreference='Stop'` 때문에 설치 단계로 가지 못하고 바로 멈춥니다(2026-11-18 관찰). 파이썬 선택과 pytest 확인을 보완합니다.
- 결과: 종료 코드와 요약 줄(`N passed, M failed`)을 남깁니다.

### 4.2 Windows 테스트 보조 (`tests/conftest.py`, `.gitattributes`)

- `conftest.py`: Windows의 HOME 경로와 심볼릭 링크 권한 차이를 테스트 안에서만 보정합니다.
- `.gitattributes`: `tests/fixtures/**` 만 LF 그대로 둡니다. 나머지는 설치 때 지문과 같은 체크아웃 기본값을 유지합니다.

### 4.3 실패 분류와 수정

이전 세션 결과(실패 22건)를 기준으로, 이번 재실행 결과로 다시 분류합니다.

| 분류 | 처리 |
|---|---|
| 테스트 쪽 가정 차이 (경로 구분자, 오류 문구, 오류 종류) | 테스트를 플랫폼 중립으로 고칩니다 |
| 어댑터 실제 동작 차이 | 원인과 영향을 기록합니다. 어댑터 수정은 설치본 지문을 바꾸므로 별도 결정이 필요합니다 |
| 환경 문제 (자식 프로세스 HOME 등) | 실행기나 `conftest.py` 에서 보정합니다 |

각 수정은 실패를 먼저 재현한 뒤 고치고, 같은 테스트로 통과를 확인합니다.

### 4.4 호환표 (`compatibility-matrix.json`)

- 허용 상태는 `verified-local`, `simulated-local`, `not-run` 뿐입니다(`tests/test_compatibility_surface.py`).
- 근거 문장에 날짜를 넣을 수 없습니다. 실행 날짜와 원본 로그는 별도 검증 기록에 둡니다.
- 셸별로 실제로 실행한 셸에서 나온 결과만 `verified-local` 로 바꿉니다. 실행하지 않은 셸은 `not-run` 으로 둡니다.
- 실패가 남으면 그 범위를 근거에 적고, 전체 호환 주장은 하지 않습니다.

### 4.5 (선택) Windows CI

- `.github/workflows/ci.yml` 에 `windows-latest` 작업을 추가하고 4.1 실행기를 씁니다.
- 주의: 지금 CI는 Core를 `AidALL/ghost-alice` 최신 main으로 받습니다. 11/12 기준을 지키려면 팀 저장소의 `test-baseline-2026-11-16` 태그로 고정해야 합니다(7절 결정).

## 5. 검증 방법

| 확인할 것 | 방법 |
|---|---|
| 테스트 결과 | PowerShell 5와 PowerShell 7에서 각각 `run_windows_tests.ps1` 전체 실행, CMD에서는 같은 명령을 `cmd /c` 로 실행 |
| POSIX 동작 유지 | 바꾼 테스트가 Linux에서도 통과하는지 확인 (CI 또는 WSL) |
| 설치본 보존 | 작업 전후로 `ga_status.py` 실행: 어댑터 지문 일치, 훅 원본 `c6019ac` 그대로 |

## 6. 진행 순서

1. 전체 테스트 재실행 → 실패 목록 확정
2. 실행기 보완 (4.1)
3. 실패 분류와 수정 (4.3)
4. 셸별 실행과 호환표 갱신 (4.4)
5. (선택) Windows CI (4.5)
6. 커밋 → PR → 팀 검토

## 7. kyu 확인이 필요한 것

1. (결정됨) Autopilot 변경은 기존 팀 저장소 `bogop8-star/ghost-alice` 의 `autopilot/` 브랜치에 올립니다. 저장소 README에 Autopilot 브랜치 안내 한 줄을 추가합니다.
2. (A-3을 할 경우) CI의 Core 기준: 팀 저장소 `test-baseline-2026-11-16` 태그로 고정(추천) 또는 AidALL 최신 main
3. 어댑터 동작 차이가 실제 버그로 확인될 때: 기록만 할지, 고칠지(고치면 설치본 지문과 달라져 재설치가 필요해짐)

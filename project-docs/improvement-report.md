# Ghost-ALICE 개선 보고서

Nov 12, 2026 · @우디

## 개요

핵심 이슈는 2건입니다. 1번은 Windows에서 기능이 아예 동작하지 않는 문제이고, 2번은 공식 애드온을 최신 Core에 설치할 수 없는 문제입니다. 3번과 4번은 원인을 더 확인한 뒤 제출할지 정합니다. 항목을 모아 AidALL에 한 번에 제출할 계획입니다.

- 대상: [AidALL/ghost-alice](https://github.com/AidALL/ghost-alice) (Core), [AidALL/ghost-alice-autopilot](https://github.com/AidALL/ghost-alice-autopilot) (Autopilot)
- 작업 저장소: [bogop8-star/ghost-alice](https://github.com/bogop8-star/ghost-alice) (공개 fork)
- 확인 환경: Windows 11, Python 3.14, PowerShell, Claude Code / 사용 중인 Core는 v0.5.1 태그, Autopilot 0.5.1

## 개선 항목 요약

| # | 항목 | 대상 | 제출 형태 | 상태 | 우선순위 |
| --- | --- | --- | --- | --- | --- |
| 1 | Windows 경로 비교 오류 | Core | PR | 수정·테스트 완료 | 높음 |
| 2 | Autopilot과 Core 버전 불일치 | Autopilot | 이슈 | 초안 작성 | 높음 |
| 3 | 빈 스냅샷으로 인한 병합 오탐 | Core | 이슈 | 분석 필요 | 보통 |
| 4 | Windows 테스트 실패 22건 | Core | 이슈 | 분석 필요 | 낮음 |

판단 기준은 두 가지입니다. 기능이 멈추는가, 그리고 원인이 확인됐는가.

| # | 등급 | 이유 |
| --- | --- | --- |
| 1 | 핵심 | Windows 사용자 전원의 session-intent 훅이 매번 거부되고 doctor가 error가 됩니다. 원인과 수정, 테스트가 모두 끝났습니다. |
| 2 | 핵심 | 공식 애드온이 최신 Core에 설치되지 않아, 사용자는 업데이트를 포기하고 옛 버전에 머물러야 합니다. 원인도 확인됐습니다. |
| 3 | 부차 | 기능은 정상이고 경고만 뜨며, 원인과 재현 여부를 아직 확인하지 못했습니다. |
| 4 | 부차 | 원본에 원래 있던 테스트 실패로, 실제 사용에 영향이 있는지 분석하지 않았습니다. |

## 1. Windows 경로 비교 오류

Windows에서는 session-intent 훅이 매번 거부됩니다. 같은 폴더를 `C:\...`와 `C:/...`로 다르게 적은 경로를 문자열 그대로 비교하기 때문입니다. 수정과 테스트는 끝났고, fork의 `fix/windows-ledger-root-normalization` 브랜치(`abc1921`)에 있습니다.

- 증상: doctor에서 `inner ledger root conflicts with trusted binding`이 나오고, golden-hook-test/session-intent가 실패해 `overall: error`가 됩니다.
- 원인 위치: `_shared/hook_profile_gate.py`의 `_run`, `_shared/install_hooks.py`의 `_managed_session_intent_options`
- 수정: 두 경로를 `os.path.normcase(os.path.normpath(...))`로 통일한 뒤 비교합니다. Linux/macOS에서는 동작이 바뀌지 않고, 실제로 다른 경로는 여전히 거부됩니다.

테스트는 `test_hook_profile_gate.py`와 `test_install_hooks.py`로 돌렸습니다.

| 환경 | 원본 main 통과/실패 | PR 브랜치 통과/실패 | 비고 |
| --- | --- | --- | --- |
| Windows 11, Python 3.14 | 225 / 24 | 227 / 22 | Codex 훅 테스트 2건이 새로 통과, 새 실패 0건 |
| Linux, Python 3.13 | 240 / 13 | 240 / 13 | 실패 목록 동일 |

사용 중인 v0.5.1에는 같은 수정을 적용했습니다(`local/v0.5.1-windows-fix`). 적용 후 doctor의 session-intent 테스트가 golden-pass로 바뀌었습니다.

팀원 검토에서 v0.5.1 브랜치에 빠진 곳이 하나 더 나왔습니다. `hook_profile_gate.py` 958행의 Autopilot 어댑터 스크립트 경로 비교(`argv[1] != adapter.get("script")`)입니다. 실제 훅 설정에서도 등록 경로는 `\`, 실행 경로는 `/`로 달랐고, 승인 실행(PreToolUse) 훅과 중단·재개(Stop) 훅이 거부될 상황이었습니다. 같은 방식으로 고쳤고, v0.5.1 테스트는 수정 전후 모두 282건 통과했습니다(Linux). main에서는 이 어댑터 기능이 삭제돼 PR에는 해당하지 않습니다.

## 2. Autopilot과 Core 버전 불일치

Autopilot 0.5.1은 최신 Core main에 설치되지 않습니다. 그래서 현재는 Core를 `v0.5.1` 태그에 고정해 우회하고 있습니다. 두 저장소 모두 버전은 0.5.1이지만, Core main은 이미 권한 어댑터 기능을 없앤 상태입니다.

- 원인: Core가 `cc96f85`(#90, 2026-10-23)에서 `privileged_adapters`를 없앤는데, Autopilot의 `addons/autopilot-mode/addon.json`은 아직 이 필드를 선언합니다.
- 증상: `install.cmd --addon-source ...`를 실행하면 `manifest field(s) ['privileged_adapters'] are retired` 오류가 납니다.
- 우회 방법: Core를 `v0.5.1` 태그로 체크아웃합니다.
- 요청할 내용: Autopilot을 관찰형 `hooks[]` 방식으로 옮긴 릴리스를 내거나, 지원하는 Core 버전을 README와 `compatibility-matrix.json`에 명시해 달라고 요청합니다.

이슈 초안은 `Claude outputs/ghost-alice-PR-issue-drafts.md`에 있습니다. 이 문제가 풀려야 로컬 설치를 main으로 옮길 수 있습니다.

## 부차 이슈 (확인 후 제출 여부 결정)

- **3. 빈 스냅샷으로 인한 병합 오탐:** Ghost-ALICE와 무관한 스킬 파일 219개가 "사용자 변경"으로 잡혀 `overall: warning`이 났습니다. 잡힌 파일은 Claude 앱 동기화 스킬 218개와 `n8n-cli` 1개입니다. 현재는 `merged`로 기록해 해소했습니다. 2026-11-12 재설치에서는 다시 나타나지 않았습니다(pending-merge: clean). 첫 설치 때만 생기는 문제로 보이며, 새 환경에서 재현되면 이슈로 올립니다.
- **4. Windows 테스트 실패 22건:** 원본 main에서도 같은 실패가 나옵니다. 실패는 Node 경로, Stop 훅(cmd.exe), Codex 설정 쪽에 몰려 있습니다. Stop 훅 실패가 실제 사용에 영향을 주는 것으로 확인되면 핵심 이슈로 올립니다.

## 다음 단계

- [ ] 1번: PR 본문에 Windows/Linux 테스트 결과 반영
- [ ] 2번: Autopilot 저장소에 같은 문제를 다룬 이슈가 이미 있는지 확인
- [ ] 3번: 재설치 후 병합 오탐이 다시 나타나는지 재현
- [ ] 4번: Stop 훅 실패가 실제 사용에 영향을 주는지 확인
- [ ] 핵심 2건을 먼저 제출하고, 3·4번은 확인되는 대로 추가

새 항목은 요약표에 한 줄을 추가하고 아래에 섹션을 단 뒤, 핵심과 부차 중 하나로 분류합니다.

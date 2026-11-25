# 인수인계: Ghost-ALICE 테스트 환경과 단점 6번(설치·환경) 개선

- 작성: 2026-11-18, 이전 세션 `8ae8df84-eb7c-433a-a733-3bcd2238f7fd` 에서 정리. 9절·10절은 2026-11-24 추가
- 읽는 사람: 이 작업을 이어받는 새 Claude Code 세션과 kyu

이 문서만 읽고 이어서 작업할 수 있도록 썼다. 키·비밀번호는 넣지 않았다.

---

## 0. 새 세션에서 가장 먼저 할 일

1. 이 세션의 ID를 kyu에게 알려 relay 전송 대상에 추가한다(아래 4절). 추가 전에 지나간 기록은 다시 보내지 않으므로 바로 한다.
2. 상태 점검을 실행해 환경을 확인한다.
   ```
   cd C:\Users\N-\hook-monitor
   python ga_status.py
   ```
   새 세션의 입력이 정상 확정되는지("입력 막힘" 항목)와 relay 실행 여부를 본다. 이전 세션 `8ae8df84` 의 입력 막힘 경고는 알려진 문제라 무시한다.
3. 9절(입력 막힘 조사, 세션 `c2edeaef`)과 10절(성능 분석과 JY 방식 채택, 세션 `95c6673a`)의 "남은 일"부터 진행한다. 둘 다 2026-11-24 기록이다. 8절은 11-18 ~ 11-19, 1~7절은 그 이전 기록이다. 11-23 작업(PR #8~#10)은 이 문서에 자세히 적혀 있지 않다.

---

## 1. 목표와 합의된 방향

- 팀: kyu, jy, sk (AIFFEL 해커톤). Ghost-ALICE(Core)와 Ghost-ALICE Autopilot이 어떻게 동작하는지 Langfuse로 관찰·분석하고, 단점을 개선한다.
- 개선 대상: 단점 6번 "설치와 환경 맞추기가 어렵다".
- 방향(조사 후 합의 대기 중): **Windows 검증**. 공식이 이미 해결한 부분은 하지 않는다.
- 원칙(kyu 결정):
  - **재설치하지 않는다.** 지금 기준 버전을 유지한다.
  - **AidALL 공식 업데이트를 따라 반영하지 않는다.** 지켜보기만 하고, `ga_status.py` 로 동향을 확인해 우리 작업이 공식과 겹치지 않게 조정한다.
  - **main을 바로 고치지 않는다.** 개인 브랜치에서 작업 → PR → 팀원 확인 후 합친다.
  - 진행 상황을 kyu에게 쉬운 말로 계속 알린다. kyu에게는 항상 한국어로 답한다.

---

## 2. 테스트 기준 버전 (고정)

| 구성 | 버전 | 위치 | 커밋 |
|---|---|---|---|
| Ghost-ALICE Core | 0.5.1 + 로컬 Windows 수정 | `C:\Users\N-\ghost-alice`, 브랜치 `local/v0.5.1-windows-fix` | `c6019ac` |
| Ghost-ALICE Autopilot | 0.5.1 공식 | `C:\Users\N-\ghost-alice-autopilot` (태그 `v0.5.1`) | `2075768` |

- 태그: 팀 저장소 `bogop8-star/ghost-alice` 의 `test-baseline-2026-11-16` → `c6019ac`. 테스트 결과에는 이 태그를 적는다.
- 설치본: 2026-11-12 08:37 UTC에 `c6019ac` 로 설치됨 (`~/.ghost-alice/install-state/claude.json`).

---

## 3. 반드시 지킬 것 (실제로 사고가 났던 것들)

1. **`C:\Users\N-\ghost-alice` 의 브랜치를 바꾸지 않는다.** 이 버전의 훅은 이 폴더를 직접 읽는다. 11/13 오전에 브랜치를 바꿨다가 오토파일럿 어댑터가 전부 거부(exit 126, identity/arguments mismatch)됐다. 개발은 별도 작업 폴더(git worktree)에서 한다.
2. **`C:\Users\N-\ghost-alice-autopilot` 의 어댑터 파일 바이트를 바꾸지 않는다.** 설치 때 등록한 지문(sha256)과 비교한다. 11/13 오후 줄바꿈(CRLF→LF) 변환만으로 "registered adapter hash mismatch" 가 났다. 이 폴더 파일은 Windows 체크아웃 그대로 CRLF여야 한다.
3. **Claude 작업 도중 멈추고(Esc) 새 메시지를 보내지 않는다.** 이 버전은 그 메시지에 사람 표시(origin)가 없으면 확정하지 못하고, 뒤 입력 전부가 막힌다(`session_intent_ledger.py` 의 `reconcile_native_inputs` 가 `if resolved is None: break`). 이전 세션 `8ae8df84` 가 이렇게 막혀 응답 경로 등록과 오토파일럿 기록이 끝까지 불가능했다. 공식 main은 이 문제를 고쳤다(뒤의 사람 입력이 앞의 막힌 입력을 대체). 2026-11-24에 원인과 main 동작을 다시 확인했다(9절). Esc 말고도 맨 앞 입력을 막는 경우가 더 있다.
4. Stop 훅의 `[completion-gate] route-unavailable` 경고: 정상 세션에서는 Claude가 Ghost-ALICE 규칙(응답 경로 등록, 완료 근거)을 빠뜨렸다는 신호다. 무시하지 말고 테스트 결과로 기록한다.

---

## 4. 만든 도구와 위치

모두 `C:\Users\N-\hook-monitor` (Git 저장소 아님. 홈 폴더 `C:\Users\N-` 전체가 다른 Git 저장소로 잡혀 있으니 여기서 커밋하지 않는다).

| 파일 | 역할 | 상태 |
|---|---|---|
| `ga_status.py` (+ `test_ga_status.py`, 테스트 11개) | 설치·동작 상태와 공식 동향 점검. 읽기 전용 | kyu가 "상태 확인해줘" 하면 실행해 해석해 준다 |
| `langfuse_relay.py` (+ `test_langfuse_relay.py`, 테스트 30개) | Ghost-ALICE 훅 기록과 Claude Code 대화를 Langfuse로 전송 | 별도 창(`start_relay.cmd`)에서 실행 중 |
| `setup_relay.cmd` / `setup_relay.ps1` / `설치방법.txt` / `langfuse-relay-share.zip` | 팀원용 relay 설치 묶음 | 팀원은 설치하지 않기로 함(각자 다른 전송 방식 사용 중) |
| `server.py` / `index.html` | 사례 모니터 (http://127.0.0.1:8765) | **현재 꺼져 있음.** 필요하면 `python server.py` |
| `README.md` | 위 도구 사용법 | |

### Langfuse relay 설정 (`~/.ghost-alice/secrets.env`, 값은 문서에 넣지 않음)

- 공유 구글 계정 1개, 지역 JP (`https://jp.cloud.langfuse.com`). 11/25부터 `TEAM` 키는 새 프로젝트 **"ghost alice project"** 를 가리킵니다. 옛 프로젝트 "My Project"는 중복이 섞인 보관용이고, 옛 키는 지웠습니다. 자세한 내용은 10절 "새 Langfuse 프로젝트로 옮겨 다시 쌓기"에 있습니다.
- `LANGFUSE_MEMBER=kyu`, `LANGFUSE_TARGETS=TEAM`, `LANGFUSE_RELAY_CONTENT=full`(질문·답변·도구 입출력까지, 비밀값 가림)
- `LANGFUSE_RELAY_SESSIONS=8ae8df84-…,ca061f72-…` → **새 세션 ID를 쉼표로 추가하고 relay를 다시 켠다.** 이미 건너뛴 기록이 필요하면 `~/.ghost-alice/langfuse-relay/state.json` 에서 그 세션 파일들의 커서를 지우고 다시 켠다(같은 ID로 덮어써져 중복되지 않음).
- `llm_call` 기록에 모델·토큰을 보내 Langfuse가 비용을 계산한다(API 정가 기준 추정치).

### 팀원 전송 방식 (Langfuse에 섞여 있음)

- kyu: 위 relay. 모든 기록에 userId `kyu`.
- jy: Langfuse 공식 SDK(`LLM Call`, `Tool: …`, 비용 포함, userId `jy`) + `ghost-alice-hook-monitor`(훅 기록, **userId 없음**, 같은 세션 ID).
- sk: `langfuse_hook_send` + `langfuse_transcript_send`, userId `sk`/`yesan` 혼용 또는 없음.
- 정리 필요: 모든 기록에 같은 userId 붙이기(팀원에게 요청할 일).

---

## 5. GitHub

- 팀 저장소: `bogop8-star/ghost-alice` (kyu의 AidALL/ghost-alice fork, kyu admin, 협업자 SeGwonKIM, ctaleez51-art)
- kyu 작업 브랜치: **`kyuproject`** — 팀 `main`(`77a8b4d`)에서 출발. 주의: 팀 main은 **공식의 새 코드 기반**이고, 기준 버전(`c6019ac`)과 Git 기록이 이어져 있지 않다(뿌리 커밋부터 다름).
- 다른 브랜치: `skproject`, `ctaleez51`, `fix/native-intake-reconcile`(누군가 입력 막힘 수정 중으로 보임) 등
- main 보호 규칙(PR·승인 필수)은 아직 없음. kyu가 원하면 설정.
- Autopilot은 팀 fork가 없다(AidALL 공식에는 push 권한 없음). Autopilot 쪽 변경을 공유하려면 fork가 필요. → 2026-11-18 결정: fork 대신 팀 저장소의 `autopilot/` 브랜치를 씀 (8절).

---

## 6. 지금까지 조사한 것

### 1단계 결과: 공식 최신(AidALL/ghost-alice main `7c78c69`, 2026-11-16) 대비

| 문제 | 공식 상태 |
|---|---|
| 브랜치 바꾸면 훅 멈춤 | 해결(#162 설치본·개발 폴더 분리, 커밋 설명 기준) |
| 입력 하나 막히면 전체 막힘 | 해결(코드 확인: supersede + 대기 기록) |
| 문서 v2 / 코드 v1 불일치 | 해결(둘 다 `response-route.v2`) |
| 진단 도구 없음 | 이미 있음: `install_doctor` (`install.ps1 -Doctor`) — 훅 거부 사유, 입력 대기, 애드온 지문 점검 |
| 줄바꿈만 바뀌어도 지문 불일치 | 일부: 해시는 여전히 바이트 비교, 진단 도구가 원인 표시 |
| Windows 경로 비교(로컬 수정) | 미확인: 로컬 수정은 main에 없음. 새 코드에서 같은 문제가 있는지는 Windows에서 돌려봐야 함 |
| 테스트·CI가 리눅스 전용 | 미해결(CI `ubuntu-latest` 뿐) |
| Autopilot Windows 지원 | 미해결: Autopilot `compatibility-matrix.json` 에서 Windows CMD/PS5/PS7 모두 `not-run`. Autopilot은 0.5.1 이후 공식 변경 없음 |

### Autopilot Windows 테스트 작업 (이미 해 둔 것, 커밋 안 됨)

- 위치: `C:\Users\N-\ghost-alice-autopilot`, 브랜치 `test/windows-compat`
- 커밋 안 된 변경: `.gitattributes`(fixtures만 `-text`), `tests/conftest.py`(Windows용 HOME·심볼릭링크 대체), `scripts/run_windows_tests.ps1`(UTF-8, Git `env.exe` PATH 추가), `tests/test_autopilot_sqlite.py`(SQLite 연결 닫기, 3줄)
- 결과: 실패 308+오류 13 → 실패 22. 남은 22건: 어댑터 Windows 동작 차이 9건(폴더가 아닌 경로 오류 종류 차이 8, "File exists" 문구 1), 미분석 13건(완료 기록 거부 5, 절대경로 판정 2, 자식 프로세스 HOME 1, 기타 5).
- 실행: `powershell -ExecutionPolicy Bypass -File scripts\run_windows_tests.ps1` (전체 약 30분)

### 새 세션 동작 확인 (정상 세션 기준)

- 세션 `ca061f72`: 일상 질문 → 도구 없이 바로 답, 완료 점검 통과, 오토파일럿 `skipped/response-no-publication`(정상).
- 세션 `90289093`: 응답 경로를 늦게 등록(`route-unavailable`) 후 등록, 설명 답변에 응답 검토 누락(`criterion-unbound`) → 오토파일럿 `completion-body-invalid`. Claude가 규칙을 빠뜨린 사례.

---

## 7. 다음 단계

1. **(완료) 1단계:** 공식 최신 확인 → 위 6절.
2. **2단계: 개선 범위 확정 (kyu 결정 필요).** 추천: Windows 검증
   - Autopilot Windows 테스트 마무리: 남은 22건 원인 정리, `test/windows-compat` 정리·커밋
   - Autopilot `compatibility-matrix.json` 의 Windows `not-run` 항목을 실제 검증 근거로 채우기
   - (선택) 공식 main을 기준 버전과 분리된 별도 환경에서 Windows 검증해 로컬 Windows 수정이 아직 필요한지 확인. **현재 설치본은 건드리지 않는다.**
3. **3단계: 설계·계획**(brainstorming → writing-plans). 작업 폴더·브랜치(`kyuproject` 또는 Autopilot fork) 결정 포함.
4. **4단계: 개발** — worktree에서, `ga_status.py` 로 공식 동향을 수시로 확인.
5. **5단계: PR → 팀 검토 → 합치기.**

### 남은 정리 거리

- 팀원에게: 모든 Langfuse 기록에 userId 통일 요청
- 팀원 설치 버전이 기준 태그와 같은지 확인
- Autopilot fork 만들지 결정(Autopilot 변경을 팀과 공유하려면 필요)

---

## 8. 진행 결과 (2026-11-18 ~ 11-19, 세션 `95c6673a-c5ea-4f56-8402-e2da6890211d`)

이 절은 위 7절 이후 진행한 내용입니다. 위 1~7절의 내용은 그대로 두었습니다. 새 세션은 0절의 1·2번을 한 뒤 이 절의 "남은 일"부터 이어 갑니다.

### 결정된 것 (kyu)

- 개선 범위: Windows 검증 (A-1 실패 정리·수정, A-2 호환표 근거, A-3 Windows CI는 선택)
- 11/12 설치 기준을 유지하고 AidALL 업데이트를 따라가지 않음. 점검 결과 기준 그대로이고 자동 업데이트 경로 없음.
- Core 폴더 `git pull` 자동 재설치 훅을 끔: `C:\Users\N-\ghost-alice` 의 `core.hooksPath` 설정 해제. 되돌리기: `git -C C:\Users\N-\ghost-alice config --local core.hooksPath hooks`
- Autopilot 변경은 새 fork 없이 기존 팀 저장소 `bogop8-star/ghost-alice` 의 `autopilot/` 브랜치에 올림. PR 대상은 Core `main` 이 아니라 `autopilot/main`.
- 어댑터 동작 차이는 고치지 않고 기록만 함 (설치본 지문 유지). 해당 테스트는 Windows에서 xfail.
- 호환표 Windows 항목은 셸별 install/status/remove를 격리 위치에서 실행한 뒤 `verified-local` 로 올림 (방식 1 → 확인 후 올림 완료).
- 호환표 Linux도 `verified-local` 로 올려 7/7 (2026-11-19). 테스트의 "`not-run` 항목이 최소 1개 있어야 한다" 단정은 "`not-run` 이면 반드시 blocker" 조건부 검사로 바꿈. 이 단정은 AidALL `a749ab7`(0.5.0, 2026-10-11)에서 넣은 것.
- JY Core 기준은 JY가 kyu 환경(`c6019ac`)에 맞추기로 함. 방법은 기존 설치 제거 후 팀 태그로 새로 설치(`jy-align-steps.md`).
- PR은 CI가 모두 통과한 뒤, 확인한 커밋으로 고정(`--match-head-commit`)해서 merge 방식으로 합침. 팀 저장소는 GitHub 자동 합치기가 꺼져 있음.
- CI의 Core 기준은 팀 태그 `test-baseline-2026-11-16` 으로 고정.
- 팀 보고서는 MD로 `project-docs/reports/` 에 공통 템플릿으로 작성, PDF는 필요할 때 MD에서 만듦.

### 폴더와 브랜치

| 위치 | 용도 | 상태 |
| --- | --- | --- |
| `C:\Users\N-\ghost-alice` | Core 설치 원본 | 그대로 (`local/v0.5.1-windows-fix` @ `c6019ac`). 브랜치 바꾸지 않음 |
| `C:\Users\N-\ghost-alice-autopilot` | Autopilot 설치 원본 | 그대로 (`test/windows-compat` @ `2075768`). 파일 바이트 바꾸지 않음 |
| `C:\Users\N-\ghost-alice-autopilot-win` | Autopilot 개발 worktree | 브랜치 `matrix-linux` (PR #4로 합쳐짐, 변경 없음), remote `team` = 팀 저장소. 다음 작업은 `team/autopilot/main` 에서 새 브랜치로 시작 |
| `C:\Users\N-\ghost-alice-team` | 팀 저장소 별도 clone (보고서 작업용) | 브랜치 `kyu/docs-branch-baseline-rules` (PR #6으로 합쳐짐). 다음 작업은 `origin/main` 에서 새 브랜치로 시작 |

### GitHub (팀 저장소 `bogop8-star/ghost-alice`)

| 항목 | 내용 | 상태 |
| --- | --- | --- |
| 브랜치 `autopilot/main` | Autopilot v0.5.1 + Windows 검증 + 호환표 7/7 | 최신 `ad51900` (PR #4 merge). CI 통과 |
| PR [#2](https://github.com/bogop8-star/ghost-alice/pull/2) | `autopilot/windows-verify` → `autopilot/main`. 테스트 수정, 호환표 Windows 근거, 실행기, CI Core 고정, JY 검토 반영(`62b27e3`) | **합쳐짐** (2026-11-19, `75f8721`). CI 2개 통과 |
| PR [#3](https://github.com/bogop8-star/ghost-alice/pull/3) | `kyu/report-windows-verification` → `main`. `project-docs/reports/` 의 `TEMPLATE.md`, `README.md`, kyu 보고서 | **합쳐짐** (2026-11-19, `f5f045f`) |
| PR [#4](https://github.com/bogop8-star/ghost-alice/pull/4) | `autopilot/matrix-linux` → `autopilot/main`. 호환표 Linux `verified-local`, `not-run` 단정 조건부로 변경 | **합쳐짐** (2026-11-19, `ad51900`). CI 2개 통과 |
| PR [#5](https://github.com/bogop8-star/ghost-alice/pull/5) | `kyu/report-update-2026-11-19` → `main`. kyu 보고서에 11/19 진행(7절) 추가, 링크를 `autopilot/main` 으로 변경 | **합쳐짐** (2026-11-19, `b2f5479`). `skill-validation` 이 Core `test_server_lifecycle` 에서 한 번 실패했다가 재실행에서 통과 (보고서와 무관한 가끔 실패하는 테스트로 봄) |
| PR [#6](https://github.com/bogop8-star/ghost-alice/pull/6) | `kyu/docs-branch-baseline-rules` → `main`. 팀 규칙 문서 `project-docs/README.md` 새로 추가: "환경은 태그, 문서는 main", 기준 버전 표와 설치 예시, 설치 폴더에서 브랜치 바꾸지 않기, 브랜치 구성과 PR 대상 | **합쳐짐** (2026-11-19, `8bfc9ea`). CI 3개 통과 |
| PR [#7](https://github.com/bogop8-star/ghost-alice/pull/7) | JY(`ctaleez51-art`)가 올림. `jy/report-2026-11-19` → `main`. JY 진행 보고서, 테스트 계획서, 보고서 목록에 한 줄 추가 | **합쳐짐** (2026-11-19, `15f85be`). CI 3개 통과 |

- 팀 규칙 문서(main): https://github.com/bogop8-star/ghost-alice/blob/main/project-docs/README.md
- kyu 보고서(main): https://github.com/bogop8-star/ghost-alice/blob/main/project-docs/reports/kyu/2026-11-18-windows-verification.md
- JY 보고서(main): https://github.com/bogop8-star/ghost-alice/blob/main/project-docs/reports/jy/2026-11-19-real-use-improvement.md (테스트 계획서 `jy/2026-11-19-test-plan.md` 첨부)
- 발견 사항 상세(`autopilot/main`): https://github.com/bogop8-star/ghost-alice/blob/autopilot/main/docs/windows-verification/2026-11-18-findings.md

### 결과

| 실행 | 통과 | 실패 | 건너뜀 | xfail |
| --- | --- | --- | --- | --- |
| 수정 전 (Windows, PowerShell 5) | 740 | 22 | 2 | 0 |
| 수정 후 (Windows, PowerShell 5.1 / 7.7.0 / CMD) | 759 | 0 | 4 | 1 |
| 수정 후 (Linux, GitHub CI) | 762 | 0 | 2 | 0 |
| 수정 후 (Windows, JY PC, Core `c6019ac`) | 758 | 1 (가끔 실패) | - | 1 |

- 테스트 쪽 차이 21건 수정, 어댑터 실제 차이 1건 xfail. Linux CI에서 Windows 건너뜀·xfail 테스트까지 통과해 Linux 동작이 바뀌지 않았음을 확인.
- JY 검토 반영(2026-11-19): `deny_read` 가 사용자 이름 대신 SID(`whoami /user`)로 읽기를 막고, 실제로 막혔는지 확인해 안 막히는 계정이면 건너뜀. 관련 테스트 파일 6개 175개 통과.
- 문서 (PR #2로 `autopilot/main` 에 합쳐짐): 설계 `docs/coding-convention/specs/2026-11-18-windows-verification-design.md`, 발견 사항 `docs/windows-verification/2026-11-18-findings.md`
- 로그 (개발 worktree, 커밋 안 함): `.win-test-run1.log` (수정 전), `.win-test-run2.log` (PS5), `.win-test-ps7.log`, `.win-test-cmd.log`. 작업 초안 `.matrix-draft.md`, `.pr-draft.md` 도 커밋 안 함.

### Windows 테스트 실행 방법

PowerShell에서 pytest가 있는 파이썬을 지정하고 실행합니다. 기본 Python 3.12에는 pytest가 없습니다. 전체 실행은 약 45분(CMD는 약 63분)입니다.

```
cd C:\Users\N-\ghost-alice-autopilot-win
$env:PYTHON = 'C:\Users\N-\AppData\Local\Programs\Python\Python314\python.exe'
.\scripts\run_windows_tests.ps1 tests -q
```

### 발견한 실제 문제 (기록만, 상세는 발견 사항 문서 2절)

1. 실행 폴더 자리에 일반 파일이 있으면 Windows에서는 경고 없이 넘어감 (Autopilot 어댑터)
2. 줄바꿈이 CRLF인 완료 문구는 기록이 거부될 수 있음 (Autopilot, 추정 포함)
3. 한국어 Windows에서 Core `completion_assessment.py` 가 한국어 파일을 cp949로 읽어 실패 (`PYTHONUTF8=1` 로 우회). 원인 줄: `c6019ac` 845·848·851행, AidALL 최신 `7c78c69` 871·874·877행의 인코딩 없는 `read_text()`
4. 병렬 상태 갱신 테스트 `test_parallel_advance_claims_ready_item_once` 가 JY PC에서 `PermissionError` 로 1번 실패, 단독 재실행 5번 통과 (발견 사항 문서 2.5, 관찰만)

### 남은 일

기록 시점: 2026-11-19 15:38 (KST). 오늘 PR #2·#4·#5·#6·#7을 합쳐서 Windows 검증과 호환표 작업은 끝났습니다. 남은 일은 아래와 같습니다.

**지금 우선순위**

- A. JY 환경 맞추기 결과 받기. JY가 `jy-align-steps.md` 순서(제거 → 폴더 삭제 → 팀 태그 `test-baseline-2026-11-16` 과 Autopilot `v0.5.1` 새로 받기 → 설치)대로 진행한 뒤 5번 확인 표를 보내 주면 kyu PC 값과 비교. JY 보고서(PR #7)에는 기준 버전이 Core `c6019ac`, Autopilot `2075768`, Claude Code 2.1.326(데스크톱 앱 6.6395.0)으로 kyu와 같다고 적혀 있어 재설치는 한 것으로 보임. 다만 설치 기록(`install-state`)까지 맞았는지는 아직 확인 표를 받지 않음.
- B. 발견한 실제 문제 1~3번을 AidALL에 이슈로 낼지 결정. JY가 1번(2.1)을 재현했고, JY 보고서 발견 문제 2번(cp949 UTF-8 읽기 실패)이 3번(2.3)과 같은 문제라 1·3번은 두 명 재현 조건을 채움. 2번(CRLF)은 kyu만 확인. 이슈 초안 3개는 써 둠. JY 보고서의 발견 문제 7건(처음 설치한 공식 `400621d` 기준, 경로 `/`·`\` 차이, 입력 막힘 등)도 이슈 후보로 함께 검토.
- C. SK 보고서 받기 (kyu·JY는 올림). 안내 메시지는 대화에서 만들어 둠(JY용 명령의 `jy` 를 `sk` 로 바꾸면 됨). 양식은 `main` 의 `project-docs/reports/TEMPLATE.md` 에 있고, 협업자 SeGwonKIM·ctaleez51-art 모두 쓰기 권한이 있어 바로 쓸 수 있음. **주의:** 기준 태그로 설치한 `~/ghost-alice` 폴더에는 양식이 없음(태그가 양식 추가 전 버전). 그래서 Claude 명령에 "GitHub 팀 저장소 bogop8-star/ghost-alice 의 main" 을 꼭 적고, 설치 폴더의 브랜치는 바꾸지 말라고 함께 적어야 함. 같은 시간에 보고서 목록 표를 고치면 충돌할 수 있으나 두 줄을 모두 남기면 됨.

**그 밖에**

1. JY 보고서의 다음 단계(비교 사례 P·E4·C3 13개를 조건마다 5번 실행)는 JY 몫. 결과가 나오면 kyu 쪽 발견 사항과 겹치는지 비교.
2. `project-docs/improvement-report.md` 4번 "Windows 테스트 실패 22건"(대상 Core로 기재)과 이번 Autopilot 22건의 관계 확인.
3. (선택) GitHub CI에 Windows 실행 추가. 실행기 `scripts/run_windows_tests.ps1` 을 그대로 쓸 수 있음.
4. 팀원에게: Langfuse userId 통일, sk PC의 Core 버전이 기준 태그와 같은지 확인.
5. Linux에서 실제 Claude 세션으로 훅 동작 관찰 (호환표 `os-linux` 의 남은 확인 항목). Windows도 실제 세션 전체 흐름은 부품 테스트로만 확인.
6. 격리 설치를 다시 하려면 Core `_shared/install_hooks.py --platform claude --destination-file <isolated.json> [--status|--uninstall]` 를 HOME·USERPROFILE을 임시 폴더로 바꿔 실행.

**끝난 것 (2026-11-19)**

- PR #3 템플릿 합침, PR #2 검토 요청 전송, JY 검토(SID 사용, 실제 차단 확인, `/remove:d` 주석) 반영 후 PR #2 합침.
- 호환표 Linux 7/7 (PR #4), kyu 보고서 11/19 갱신 (PR #5).
- 팀 규칙 문서 `project-docs/README.md` (PR #6). 맨 위 `README.md` 는 AidALL 원본 문서라 손대지 않음.
- JY 보고서와 테스트 계획서 합침 (PR #7, JY가 올림).
- AidALL 공식 변화 확인: 11/12 이후 Core 3커밋(설치 관련 #161·#162·#163), Autopilot 0커밋. v0.5.1 이후 Core는 61커밋. 기준 고정 유지.
- Langfuse relay: 이 세션은 11:06에 이미 추가돼 있었음.

### 작업 초안 (개발 worktree `C:\Users\N-\ghost-alice-autopilot-win\.issue-drafts\`, 커밋 안 함, kyu PC에만 있음)

| 파일 | 내용 | 상태 |
| --- | --- | --- |
| `2.1-run-dir-regular-file.md` | 이슈 초안: 실행 폴더 자리에 일반 파일이 있으면 Windows에서 복구 안내 없음 (Autopilot) | 제출 안 함 |
| `2.2-crlf-completion-block.md` | 이슈 초안: CRLF 완료 문구 거부 (Autopilot) | 제출 안 함 |
| `2.3-core-cp949.md` | 이슈 초안: Core 응답 검토 CLI의 cp949 오류 | 제출 안 함 |
| `pr2-review-message.md` | PR #2 검토 요청 메시지 + Claude 명령 2개(검토, 내 PC에서 테스트) | 보냄. JY 검토·테스트 결과 받아 반영 완료 |
| `jy-baseline-message.md` | JY Core 기준 맞추기 요청 + `fix/windows-recording` push용 Claude 명령 | 쓰지 않음 (JY가 kyu 환경에 맞추기로 해서 `jy-align-steps.md` 로 대체) |
| `jy-align-steps.md` | JY가 kyu 환경(`c6019ac`)에 맞추는 간단한 순서: 제거 → 삭제 → 태그로 새로 받기 → 설치 → Claude 확인 명령 | JY에게 전달. 확인 표 회신 대기 |
| `jy-align-steps.detailed.md` | 위의 자세한 버전 (백업·브랜치 보존 포함) | 참고용 |
| `team-message.md` | 팀원 전체 안내(PR #2·#3 검토, cp949 확인, 이슈 의견) + Claude Code용 명령 ①~⑤ | 템플릿 관련 부분(PR #3 검토, 보고서 작성 명령)만 먼저 보내기로 함. 나머지는 나중에 |

이슈 초안은 팀 `project-docs/bug-report-guide.md` 형식(AidALL `bug_report.yml` 항목 순서)을 따랐고, Safety checks는 제출하는 사람이 직접 체크하도록 비워 둠. PR #2 설명의 "검토 부탁드릴 부분" 3번은 아직 고치지 않은 3건(2.1~2.3)으로 고쳐 둠.

### 팀원 Core 기준 불일치 (2026-11-19 발견)

JY의 Claude가 비교한 결과, Autopilot은 같지만 Core는 서로 다른 코드를 실행하고 있음.

| 구성 요소 | kyu PC | JY PC |
| --- | --- | --- |
| Core 실행 코드 | `c6019ac` (`local/v0.5.1-windows-fix`, 팀 태그 `test-baseline-2026-11-16`, Windows 수정 4개) | `8b2cae9` (`fix/windows-recording`, 2026-11-17, Windows 수정 2개) |
| Core 설치 기록 | `c6019ac` | `400621d` (공식 v0.5.1, clean, 11-12) |
| Autopilot | `v0.5.1` `2075768` | 같음 |

- 원인: 두 사람이 공식 `400621d` 위에 Windows 수정을 각자 따로 얹음. JY PC는 팀 저장소를 fetch한 적이 없어 `c6019ac` 가 없음. 이 버전의 훅은 Core 원본 폴더를 직접 읽어서, JY가 설치 뒤 브랜치를 바꾸자 설치 기록(`400621d`)과 실제 실행 코드(`8b2cae9`)가 어긋남.
- 예전에 kyu가 보낸 기준 버전 안내는 정보 공유였고 요청·확인 절차가 없어 반영되지 않았음.
- 결정(2026-11-19): JY가 kyu 환경에 맞추기로 함. 아래 원래 해결 순서 대신 `jy-align-steps.md` 의 간단한 재설치를 따름. 팀 `main` 에는 `c6019ac` 를 넣지 않음(`main` 은 AidALL 기여용, 환경은 태그로).
- (원래 해결 순서, 참고) (1) JY가 `fix/windows-recording` 을 팀 저장소에 push (2) 두 수정 diff 비교, JY 쪽에만 있는 필요한 수정이 있으면 새 기준 태그 검토 (3) 기준 확정 후 JY는 Claude 세션을 모두 끄고 백업한 뒤 재설치(브랜치 전환 금지), `ga_status.py` 로 확인해 회신. `hook-monitor` 폴더 공유 필요.
- JY PR #2 테스트(758 통과)는 Core `c6019ac` 로 실행했다고 JY가 보고함. 그래서 Core 버전 차이는 그 결과에 영향이 없었음.
- sk PC의 Core 버전은 아직 확인하지 않음.

### 발표 자료 (2026-11-19 정리, 대화에만 있음)

설치·호환성 개선 발표용 수치. 속도 개선이 아니라 호환성·신뢰성 개선임을 밝힐 것.

| 지표 | 개선 전 | 개선 후 |
| --- | --- | --- |
| Windows 테스트 실패·오류 | 321건 (이전 세션 기록) | 0건 |
| 이번 단계 실패 | 22건 | 0건 |
| Windows 테스트 통과율 | 97.1% (740/762) | 100% (759/759, 건너뜀 4·xfail 1 제외) |
| Windows 셸 검증 | 0/3 | 3/3 |
| 호환표 검증 항목 | 3/7 (43%) | 7/7 (100%) |
| Linux CI 실행 테스트 | 0개 (첫 단계 중단) | 762개 통과 |

한계: 실제 Claude Code 실행 환경 훅 동작은 미검증, Windows 결과는 PC 두 대(kyu, JY) 기준, 버그 3건 미수정(이슈 제출 여부 결정 전).

### 재부팅 후 할 일

- Langfuse relay는 PC를 끄면 멈춤. `C:\Users\N-\hook-monitor\start_relay.cmd` 를 실행하고 창을 열어 둠 (2026-11-19 10:36 다시 켬).
- `python ga_status.py` 로 상태 점검. 그 밖에 재부팅으로 바뀌는 것은 없었음 (설치 기준, 개발 폴더, 임시 폴더 백업 모두 그대로).

### 주의

- 이 세션에서 Ghost-ALICE Stop 훅 경고가 여러 번 나왔음 (`route-unavailable`, `criterion-unbound`). 도구를 쓰기 전에 `response_route.py` 로 응답 경로를 등록하고, 근거를 바탕으로 한 설명 답변에는 `completion_assessment.py prepare-response` / `record-response` 로 응답 검토를 기록해야 함. 응답 경로 목적이 `execution` 이면 응답 검토는 `response-unbound` 로 거부됨 (설명 답변에만 해당).
- 응답 검토 도구를 직접 실행할 때는 `PYTHONUTF8=1` 필요 (한국어 파일 cp949 오류).
- 훅과 같은 파이썬을 써야 함: `C:\Users\N-\AppData\Local\Programs\Python\Python314\python.exe`. 원장 도구 경로는 `~/.ghost-alice/runtime/current/session-intent-analyzer/scripts/session_intent_ledger.py`.
- 테스트 중 `icacls` 로 읽기를 막은 임시 파일이 남으면 `icacls <폴더> /reset /T /C /Q` 로 권한을 되돌린 뒤 지움 (개발 worktree의 `.tmp` 는 Git이 무시함).

---

## 9. 진행 결과 (2026-11-24, 세션 `c2edeaef-0513-4d05-9c90-ee5ba91e56e0`)

이 절은 8절 이후 이 세션에서 한 일입니다. 1~8절은 그대로 두었습니다. 새 세션은 0절의 1·2번을 한 뒤 이 절의 "남은 일"부터 이어 갑니다.

### 환경

- 이 세션 작업 폴더: `C:\Users\N-\ghost-alice-autopilot` (브랜치 `test/windows-compat` @ `2075768`, 커밋 안 된 변경 많음. 건드리지 않음)
- Langfuse relay: 이 세션 ID를 `LANGFUSE_RELAY_SESSIONS` 에 추가하고 다시 켰다(PID 44376, 10:45:40). 세션 ID가 4개 들어 있다.
- `ga_status.py`: 입력 막힘은 이전 세션 `8ae8df84` 뿐(121건). 이 세션은 정상.
- `C:\Users\N-\ghost-alice-team`: 로컬 main을 `c872c7f` 까지 pull. **주의:** 이 세션 작업 중 이 폴더의 브랜치가 다른 곳에서 `main` → `kyu/report-performance` → `main` 으로 바뀌었다. 다른 세션이나 편집기가 같은 폴더를 쓰는 것으로 보인다.

### 1. 입력 확정 막힘 원인 확인

재현 스크립트는 임시 폴더 `C:\Users\N-\AppData\Local\Temp\claude\9cc5669bddfaac57\c2edeaef-0513-4d05-9c90-ee5ba91e56e0\scratchpad\repro\` 에 있다(`replay.py`, `cases.py`, `trimcheck.py`, `realtrim.py`). 각 버전을 `--shared` 로 복제해 원장 함수를 직접 호출했다. 설치한 훅으로 돌린 것은 아니다.

- 구조 원인(확인됨): 기준 버전 `reconcile_native_inputs` 는 대기 입력 맨 앞이 확정되지 않으면 `break` 해서 뒤 입력이 모두 대기한다. main `5730668` 은 뒤에 사람 입력이 확인되면 앞 입력을 `native-input-superseded` 로 넘긴다.
- `8ae8df84` 실제 기록 재생: 맨 앞 입력(634자)이 Esc로 중단되어 대화 기록에 `[Request interrupted by user]` 만 남음. `c6019ac` 막힘, `5730668` 풀림, 대조 실험(중단 입력 없음)은 둘 다 정상.
- **`c6019ac` 는 공식 커밋이 아니다.** `400621d`(공식 v0.5.1)와 `c6019ac` 사이 커밋 4개는 모두 kyu가 11-12에 만든 로컬 수정(`fork/local/v0.5.1-windows-fix` 에만 있음). `ae0acbc`·`c6019ac` 가 입력 대조를 고쳤다(덩어리 여러 개를 줄바꿈으로 잇기, 작업 도중 메시지 `queued_command` 인정, 앞뒤 공백 잘라 비교).
- 세 버전 비교(실제 대화 기록 줄):

  | 입력 | `400621d` | `c6019ac` | `5730668` |
  | --- | --- | --- | --- |
  | 한 줄 입력 | 확정 | 확정 | 확정 |
  | 작업 도중 메시지 | 막힘 | 확정 | 확정 |
  | 덩어리 2개 입력 | 막힘 | 확정 | 막힘 |
  | 실제 `8f601ab0` 입력(덩어리 2개, 붙여넣기 끝 줄바꿈, 5019자) | 막힘 | 확정 | 막힘 |

- **main에 남은 문제(AidALL 보고 후보):** main은 앞뒤 공백을 정리하지 않고 비교한다. Claude Code는 훅에 넘기는 입력의 끝 줄바꿈을 자르고 대화 기록에는 남긴다. 그래서 줄바꿈으로 끝나는 붙여넣기(`<pasted_content>`) 메시지는 main에서도 확정되지 않는다. 뒤 입력이 오면 넘어가 전체가 막히지는 않지만, 그 턴은 응답 경로를 등록할 수 없다. 이 PC 실제 데이터: 한 줄 입력 363건·작업 도중 메시지 23건은 그대로 일치했고, 덩어리 여러 개 입력 4건 중 1건이 공백을 잘라야 일치했다.
- jy 막힌 세션 3개(Langfuse 내보내기 `8ae8df84\scratchpad\lf_nonkyu.json` 분석): `648e8c65` 는 사용량 한도가 풀린 뒤 앱이 자동으로 보낸 계속 메시지(107자)에서 막힌 것으로 보임. `7ea2b0f5`(18자 입력)와 `9a734b5f`(첫 입력 974자)는 원인 불명. jy는 11-19까지 `400621d` 를 썼고, jy 11-19 보고서 4절에 같은 계열 원인 4가지(알림 `producer` 없음, 글 두 덩어리, 작업 도중 메시지, 같은 메시지 두 번 접수)가 이미 적혀 있다.

### 2. 초안

- `C:\Users\N-\ghost-alice-autopilot-win\.issue-drafts\2.4-native-input-interrupt-block.md`: 입력 막힘(Esc 중단) 확인 기록 초안. "기준 버전 문제, main에서 해결됨" 으로 썼다. **아직 반영 안 됨:** 위 1의 jy 세션 분석, `400621d` 비교, main에 남은 붙여넣기 입력 문제.

### 3. GitHub (팀 저장소)

| PR | 내용 | 상태 |
| --- | --- | --- |
| [#11](https://github.com/bogop8-star/ghost-alice/pull/11) | jy 보고서 11-24 (훅 끔·켬·수정 후 비교, 이슈 초안 4개, 설치본 수정 diff) | **합쳐짐** (`b63cc83`). 검토 뒤 jy가 올린 보고서 전용 커밋 `c8d0543` 이 검토 없이 같이 들어감. 읽어 보니 문제 없어 kyu가 그대로 두기로 함 |
| [#17](https://github.com/bogop8-star/ghost-alice/pull/17) | main CI 실패 수정: kyu 증거 파일 `test_zz_repro_*.py` 2개를 `repro_*.py` 로 이름 변경, 보고서 링크와 실행 방법 갱신 | **합쳐짐** (`c872c7f`). main `CI`·`Skill Validation` 모두 통과. 브랜치·임시 worktree 삭제함 |
| #12, #13, #14 | kyu의 다른 세션 작업(성능 보고서, Core 검토 경량화 → `core/main`, 팀 작업 안내) | 열림. 이 세션에서는 보지 않음 |
| #15 | jy: 읽기 전용 입력 Stop 훅 통과 + 사용자 안내 → **`local/v0.5.1-windows-fix`(기준 버전 브랜치) 대상** | 열림. 보지 않음 |
| #16 | jy 보고서 11-24 갱신(#11 머지 뒤 같은 브랜치에 추가) | 열림. 보지 않음 |

PR #11 검토 때 찾은 점(jy에게 아직 전달 안 함):

- jy 설치본 수정의 읽기 전용 판정이 쓰기 명령 일부를 통과시킴: `FOO=1 rm -rf build`, `$r = Remove-Item …`, 기록 스크립트 이름이 섞인 `rm …; python response_route.py`, `sort -o`, sed `w`. Stop 훅 판정에만 쓰여 실행을 막는 장치는 아님. **PR #15 가 같은 코드를 기준 브랜치에 넣으려는 것일 수 있으니 확인 필요.**
- 이슈 초안 4개의 Safety checks 미리 체크, "설치 명령: 확인 필요" 남음.
- 이슈 1(읽기 입력 막힘)은 Ghost-ALICE 규칙상 읽기도 normal 작업이라 버그보다 비용 개선 제안에 가까움. main에서 확인 전.

### 남은 일

1. jy에게 대화 기록 줄 받기(요청 문구는 대화에 있음): `648e8c65`(11-17 06:16~06:30 UTC), `7ea2b0f5`(11-18 02:40~02:45), `9a734b5f`(11-16 03:37~03:40). 받으면 `replay.py` 처럼 세 버전으로 재생해 세션별 원인 확정 → 초안 2.4 갱신.
2. main에 남은 붙여넣기 입력 확정 문제를 AidALL 이슈 초안으로 쓸지 결정.
3. PR #15 검토. **기준 버전 브랜치 대상**이라 합치면 kyu·jy 설치 원본에 영향이 갈 수 있음. 위 읽기 전용 판정 문제가 들어 있는지 확인.
4. PR #16 검토(jy 보고서 추가분).
5. PR #11 검토 의견을 jy에게 전달할지 결정.
6. `Skill Validation` 의 `test_shutdown_closes_websocket_when_peer_stops_reading` 가끔 실패(최근 12번 중 4번). 공식 코드의 테스트라 따로 다룰지 결정.

### 이 세션에서 배운 것

- PR을 머지할 때는 **검토한 커밋 SHA** 로 `--match-head-commit` 을 건다. 머지 직전에 받은 head로 걸면 검토 뒤 올라온 커밋을 막지 못한다(PR #11에서 실제로 일어남).
- 응답 검토(`completion_assessment.py prepare-response`)의 claims는 답변 안 문장을 글자 그대로 써야 한다. 답변을 고치면 다시 준비해야 하고, 보여 준 답변과 검토한 답변이 다르면 Stop 훅이 다시 막는다.
- 응답 검토는 응답 경로 목적이 `explanation` 일 때만 된다(`execution` 이면 `response-unbound`).

---

## 10. 진행 결과 (2026-11-19 ~ 11-24, 세션 `95c6673a-c5ea-4f56-8402-e2da6890211d`)

이 절은 성능 분석과 개선 시험을 한 kyu의 다른 세션 기록입니다. 9절과 같은 날 따로 진행했고, 9절에서 "보지 않음"으로 남긴 PR #12~#15가 이 세션 작업입니다.

### 목표와 결론

- 목표는 "Ghost-ALICE·Autopilot이 쓰는 시간과 비용에 비해 효과가 없다"를 실제 금액으로 확인하는 것이었습니다.
- 결론 1. 짧은 작업에서 지금 Ghost-ALICE(BASE)는 비용 2.5배, 시간 6.5배였고, 근거 검토는 12번 중 1번만 실행됐습니다. 검토받은 답이 그대로 나간 경우는 0번이었습니다.
- 결론 2. **팀 결정(11/24, kyu): JY 방식(PR #15)을 우선 채택했습니다. 그 뒤 kyu가 다시 검토하기로 했습니다(11/24 오후, 아래 "A·B 재검토").** 같은 시험에서 가장 싸고 빨랐습니다(BASE 대비 -38%, 실행당 41초). 검토의 정확도 효과는 Opus 함정 케이스에서 확인되지 않았습니다.
- 결론 3. Autopilot은 고장이 아닙니다. 기록 조건(완료 조건 + 실행 작업 단위가 든 응답 경로 + 완료 보고)을 갖춘 입력이 없었을 뿐입니다. 실제 원장에는 11/12 세션 2개에서 기록·적용 4건이 있습니다.

### 측정 결과 (같은 케이스 6개 × 3회, 금액은 Claude Code가 보고한 실제 값)

| 조건 | 총 금액 | 실행당 시간 | 정답 | 근거 케이스 12회 중 검토 |
| --- | --- | --- | --- | --- |
| OFF (Ghost-ALICE 없음) | $3.45 | 23초 | 18/18 | - |
| BASE (지금 그대로) | $8.51 | 149초 | 18/18 | 1 (그대로 전달 0) |
| IMP3b (자동 경로 등록 + 한 번 검토, 측정판) | $5.29 | 64초 | 18/18 | 12 (그대로 전달 12) |
| PR #13 최신판 (규칙·receipt 복원, Autopilot 보호) | $6.09 | 46초 | 18/18 | 12 |
| **JY 방식 (PR #15)** | **$5.29** | **41초** | 18/18 | 0 |

- 함정 케이스 10개(`perf/testbed2/`)에서 PR #13·OFF·JY 방식을 합쳐 25회 돌렸고, 모두 정답이었습니다. 검토가 잡을 오류가 없어 kyu가 측정을 중단했습니다.
- 측정 비용은 모두 약 $60입니다.
- 자세한 과정은 `C:\Users\N-\hook-monitor\perf\test-plan.md` 11~16절에 있습니다. 표는 `results.md`(OFF~IMP3)와 `results-jy-vs-kyu13.md` 에 있습니다. 로컬 보고서는 `report.md` 입니다.

### GitHub (팀 저장소)

| PR | 내용 | 상태 |
| --- | --- | --- |
| [#12](https://github.com/bogop8-star/ghost-alice/pull/12) | kyu 성능 측정 보고서와 증거 자료(케이스, 도구, 패치, 함정 자료). JY 방식 채택 결정과 PR #15 합침 반영 | **합침** (`main`, `e4df73c`, 11/24). SK 보고서와 목록 충돌을 두 줄 모두 남겨 해결 |
| [#13](https://github.com/bogop8-star/ghost-alice/pull/13) | Core 개선: 경로 자동 등록과 한 번 검토 → `core/main` | **닫음** (팀 결정). 브랜치 `kyu/core-review-lite` 는 남김 |
| [#14](https://github.com/bogop8-star/ghost-alice/pull/14) | 팀 작업 안내에 `core/main` 브랜치와 PR 대상 고르는 법 추가 | **합침** (`main`, `153e562`, 11/24) |
| [#15](https://github.com/bogop8-star/ghost-alice/pull/15) | JY: 읽기만 한 입력은 막지 않기 + 한국어 사용자 안내 + 읽기 전용 판별기 수정(`b03f6dc`) | **합침** (`core/main`, `450e4b3`, 11/24). JY가 대상을 `core/main` 으로 바꾸고 판별기를 고침. kyu가 쓰기 명령 13개·읽기 명령 7개로 직접 확인, CI 통과 |
| [#16](https://github.com/bogop8-star/ghost-alice/pull/16) | JY 보고서 11-24 추가분 | 열림, 아직 검토 안 함 |
| [#22](https://github.com/bogop8-star/ghost-alice/pull/22) | 팀 작업 안내 설치 예시의 `-AddonSource` 경로를 Autopilot 저장소 맨 위 폴더로 고침 | **합침** (`main`, `0a576fa`, 11/24) |
| [#23](https://github.com/bogop8-star/ghost-alice/pull/23) | SK 11-24 보고서: JY 이슈 1~4 두 번째 재현과 켬·끔 벤치 준비 | **합침** (`main`, 11/24 15:55). **SK가 직접 올리고 직접 합침(다른 팀원 확인 없음)** |
| [#24](https://github.com/bogop8-star/ghost-alice/pull/24) | SK 이슈: 기준 버전 `mark_decided` 가 같은 id의 미결정 항목을 남기는 문제 | 열림, 아직 보지 않음 |
| [#25](https://github.com/bogop8-star/ghost-alice/pull/25) | A·B 비교 시험 키트: 도구를 다른 PC에서 쓰게 고침(`GA_TEST_ROOT`·`GA_PERF_DIR`, `--model`, `-Root`·`-PythonDir`), `.gitattributes`(패치 LF, 시험 자료 줄바꿈 변환 없음), `TESTING.md` 시험 안내서 | **합침** (`main`, `e645f73`, 11/24) |

- 새 브랜치 `core/main` 을 만들었습니다. 기준 Core `c6019ac` 에서 시작했고, 지금은 JY 방식(PR #15)이 들어 있습니다. Core 개선은 여기로 PR을 올립니다. **설치는 계속 태그 `test-baseline-2026-11-16` 으로 합니다.**
- 브랜치 보호 설정은 없습니다. kyu 계정에 관리자 권한이 있지만 브랜치 보호 설정은 바꾸지 않았습니다.
- **Issues 기능을 켰습니다** (11/24, kyu 요청). JY가 버그 보고서 지침대로 팀 저장소에 이슈를 먼저 올리려 했는데 Issues가 꺼져 있었고, JY 권한으로는 설정을 바꿀 수 없었습니다. `gh api -X PATCH repos/bogop8-star/ghost-alice -F has_issues=true` 로 켰고, 확인 결과 `has_issues: true` 입니다. **저장소는 공개(public)라 이슈를 누구나 볼 수 있습니다.**
- JY가 이슈 4개를 올렸습니다(11/24): [#18](https://github.com/bogop8-star/ghost-alice/issues/18) 읽기만 한 입력은 경로 등록 없이 끝내기(기능 제안), [#19](https://github.com/bogop8-star/ghost-alice/issues/19) Stop 막힘 메시지가 영어 내부 코드뿐, [#20](https://github.com/bogop8-star/ghost-alice/issues/20) `/visibility minimal` 에서도 내부 코드가 보임, [#21](https://github.com/bogop8-star/ghost-alice/issues/21) 도구 없는 질문에 훅 5개·도구마다 훅 3개. 초안 의견(이슈 1은 기능 제안, 빈칸 채우기)이 반영됐고, 간단히 봤을 때 PC 경로나 이메일은 없습니다.
- SK는 PR 없이 브랜치 두 개를 올렸습니다(11/23). kyu가 SK가 PR을 올릴 때까지 기다리기로 했습니다.
  - `sk/repro-kit-result-2026-11-23`: kyu 재현 도구를 SK PC에서 돌린 결과 파일 1개. **SK 설치가 기준 버전과 같음을 확인**(Core `c6019ac`, Autopilot `v0.5.1` `2075768`). 8절의 "sk PC의 Core 버전 확인"은 끝난 것으로 봅니다.
  - `skproject`: SK 자체 분석(세션 461개·추정 $382.82 실행 보고서, 절감 브리핑 PDF와 대본, 검증 요약, 지표, 재현 스크립트)과 Core 코드(`_shared`) 18개 파일 변경. 커밋 18개, 파일 60개. 옛 `main`(PR #1 직후)에서 갈라져 그대로는 합치기 어렵고, Core 변경은 `core/main` 쪽으로 나눠야 합니다. SK 분석도 Stop 차단 441번 중 97.5%가 경로 미등록이라, 우리 측정과 방향이 같습니다.

### A·B 재검토 (11/24 오후, kyu 결정)

**왜 다시 보나**

- JY 방식은 읽고 알려 주는 답을 검토하지 않습니다(0/12).
- 기존 Ghost-ALICE는 검토하도록 설계됐지만 실제로는 1/12였습니다.
- kyu 방식은 12/12 검토합니다. 그래서 kyu 방식 채택을 다시 검토하기로 했습니다.
- 결정은 추가 시험 결과를 보고 합니다. 그때까지 `core/main` 은 JY 방식 그대로 둡니다.

**두 후보**

- A: `core/main` `450e4b3` (JY 방식)
- B: `kyu/core-review-lite` `15b6e2b` (kyu 방식, 닫힌 PR #13 브랜치)
- 측정할 때만 두 후보 모두에 시험 전용 패치를 얹습니다.

**역할**

- JY: 자기 PC에서 A 대 B 비용 비교를 합니다(6케이스 × 3회, Opus). 선택으로 Autopilot 확인(완료 조건 케이스 1개, B에서 3회)도 합니다. 앞서 부탁한 "파일을 바꾼 턴 자동 등록" 구현은 멈춥니다(kyu 방식에 이미 있음).
- SK: 함정 케이스 10개를 약한 모델(Haiku, 필요하면 Sonnet)로 A 대 B 각 3회 돌립니다. 검토가 틀린 답을 잡는지 봅니다. SK 실제 설치는 `df903bc` 라 반드시 시험용 홈에서 합니다.
- 각자 자기 PC 안에서 A 대 B로 비교하고, PC끼리 숫자를 직접 비교하지 않습니다.

**결정 기준** (`TESTING.md` 6절, 시험 전 합의)

- SK 시험에서 A는 틀렸는데 B가 검토로 고친 실행이 있으면 kyu 방식 채택을 제안합니다.
- A와 B가 같은 만큼 틀리거나 모두 맞히면 JY 방식을 유지합니다.
- JY 시험에서 B가 30% 넘게 비싸면 다시 논의합니다.

**메시지와 안내서**

- 안내서: 팀 저장소 `main` 의 `project-docs/reports/kyu/evidence/2026-11-24/TESTING.md`
- JY·SK 요청 메시지는 대화에서 만들었고 kyu가 보냅니다. **실제로 보냈는지는 kyu에게 확인합니다.**
- JY에게는 그보다 앞서 "파일을 바꾼 턴 자동 등록 + PowerShell 읽기 명령" 요청 메시지를 보냈습니다. 이번 메시지가 그 구현을 멈춘다고 알립니다.

### 최종 결과물 (11/24, kyu PC에만 있음, 팀 저장소에 올리기는 kyu가 보류)

- `C:\Users\N-\hook-monitor\final\2026-11-24-final-report.md`: 최종 보고서(Windows 검증, 비용 측정, 개선안 비교, 함정 케이스, 팀 결정, Autopilot, 한계, 다음 단계. JY·SK 자료 포함)
- `C:\Users\N-\hook-monitor\final\2026-11-24-aidall-submission.md`: AidALL 제출 정리 초안.
  - B1~B3 바로 낼 수 있음: cp949 인코딩(Core), Windows 실행 폴더 복구 안내 없음(Autopilot), CRLF 완료 문구(Autopilot)
  - C1~C4 최신 버전으로 다시 재현 필요
  - 이미 해결된 것 1건
  - 개선 제안 P1~P4
  - 제출 전 할 일
  - **아직 아무것도 제출하지 않았습니다.**
- 발표 자료 15장: https://claude.ai/artifact/1PFVpXjsZETa5NpPukT5c3 (kyu만 볼 수 있음, 공유는 kyu가 Share 메뉴에서). 발표자 노트 포함, PPTX·PDF로 내려받을 수 있습니다.
  - 내용이 많은 "AidALL 전달 사항"과 "한계" 슬라이드는 화면으로 확인하지 않았습니다.
  - A·B 재검토 결과가 나오면 "결정" 슬라이드를 고쳐야 합니다.

### 시험 환경 (`C:\Users\N-\ga-test\`, 실제 설치와 분리)

- 실제 설치본은 매 단계 전후로 `guard\guard.py` 지문(파일 921개)을 비교했고, 그대로입니다. 마지막 확인 파일은 `guard\after-jy-kyu13-batch.json` 입니다.
- 시험용 Core(`src\core` 의 worktree, 모두 기준 `c6019ac` + 시험 전용 입력 확정 패치 `8f3fb7e`):

  | 폴더 | 브랜치 | 내용 |
  | --- | --- | --- |
  | `src\core` | `test/sdk-origin` | BASE |
  | `src\core-imp` | `test/imp-v3` | IMP~IMP3b 측정판 |
  | `src\core-jy` | `test/jy` | PR #15 |
  | `src\core-kyu13` | `test/kyu13` | PR #13 최신판 |

- 시험용 홈은 세 개입니다. 로그인은 kyu가 직접 했고, 자격 증명은 12/17까지입니다.

  | 시험용 홈 | 지금 설치된 Core |
  | --- | --- |
  | `home-off` | Ghost-ALICE 없음 |
  | `home-base` | **JY 방식(`core-jy`)** |
  | `home-imp` | **PR #13 최신판(`core-kyu13`)** |

  BASE를 다시 재려면 `home-base` 에 `src\core` 를 다시 설치합니다. (11/24 오후 바뀐 `install_arm.ps1` 을 시험하려고 `home-base` 에 `core-jy` 를 같은 내용으로 다시 설치했습니다.)
- 도구(`tools\`, 11/24 오후 팀 저장소 증거 폴더와 같은 내용으로 맞춤. 경로는 `GA_TEST_ROOT`·`GA_PERF_DIR` 로 바꿀 수 있고, `run_batch.py --model`, `login_arm.ps1 -Arm <이름>` 을 씁니다):
  - `install_arm.ps1 -Arm <off|base|imp> -Core <Core 폴더> -Addon <Autopilot 저장소 최상위 폴더>`
  - `run_case.py <라벨> <케이스> <회차> [--home off|base|imp] [--suite testbed|testbed2]`
  - `run_batch.py --arms 라벨:홈 ... --repeats N [--suite]`
  - `aggregate.py --arms ... [--out]`
- 자동 실행(`claude -p`)은 입력이 사람 입력으로 확정되지 않아서, 시험용 Core에 `GHOST_ALICE_TEST_ACCEPT_SDK_ORIGIN=1` 패치를 넣었습니다. PR 대상이 아닙니다.

### Langfuse relay 중복 저장 수정 (11/24 저녁)

**증상.** 이 세션 Langfuse 기록에서 실제 모델 호출은 1,200개였는데 `llm_call` 은 4,001개였습니다. 비용과 토큰 합계가 약 3.3배 크게 보였습니다. 3절의 "약 70% 큼"은 11/19 일부 구간 기준이고, 그 뒤로 더 커졌습니다.

**원인.** `perf/lf_dupes.py` 로 확인했습니다.

- 메시지마다 한 개는 지금 파일의 위치와 맞고, 나머지 2,797개는 지금 파일에 없는 위치를 가리킵니다. 대부분 11/18~11/19의 오래된 메시지입니다.
- 데스크톱 앱이 대화 기록 파일을 더 짧게 다시 쓰면, relay가 `size < offset` 으로 보고 처음부터 다시 읽습니다.
- 그런데 기록 ID(spanId)를 "파일 경로 + 줄 시작 바이트 위치"로 만들었습니다. 다시 쓴 파일에서는 위치가 바뀌므로, 이미 보낸 메시지가 새 ID로 또 들어갔습니다. 다시 쓸 때마다 사본이 하나씩 늘었고, 메시지당 최대 5개였습니다.

**수정.** `hook-monitor/langfuse_relay.py` 를 고쳤습니다.

- `llm_call` 은 `회원|세션|message_id` 로 ID를 만듭니다.
- 대화 내용 기록(질문, 답, 도구 입출력)은 `세션|줄 uuid|블록 번호` 로 ID를 만듭니다. `message_id` 나 `uuid` 가 없는 줄만 예전처럼 위치를 씁니다.
- 파일이 다시 써져 처음부터 읽어도 ID가 같아서 Langfuse가 하나로 합칩니다.
- 시험: "파일을 짧게 다시 쓴 뒤 다시 읽기"를 재현하는 테스트 `test_rewritten_transcript_resends_with_the_same_ids` 를 먼저 만들었습니다. 고치기 전에는 실패했고 고친 뒤에는 통과했습니다. `test_langfuse_relay.py`, `test_ga_status.py` 39개 모두 통과합니다.
- relay를 다시 켰습니다(11/24 17:47, 프로세스 35232). 이 세션 기록 끝까지 따라잡은 것도 확인했습니다.

**남은 점**

- 이미 Langfuse에 들어간 중복은 지우지 않았습니다. 11/24 17:47 이전 기록으로 비용을 계산할 때는 `message_id` 로 중복을 빼야 합니다. 세션별 중복 정도는 `python perf/lf_dupes.py <세션 ID>` 로 봅니다(읽기 전용, 키는 출력하지 않음).
- 고치기 전에 보낸 줄은 옛 방식 ID입니다. 다음에 파일이 한 번 더 다시 써지면 그 줄들이 새 방식 ID로 한 번 더 들어갈 수 있습니다. 그 뒤로는 늘지 않습니다.
- JY·SK에게 고친 `langfuse_relay.py` 와 `perf/lf_dupes.py` 를 보내는 메시지를 대화에서 만들었고, kyu가 보냅니다. `hook-monitor` 는 git 저장소가 아니라 파일로 전달합니다. 받은 사람은 relay 창 닫기, 파일 교체, `start_relay.cmd` 다시 실행 순서로 적용합니다. 실제로 보냈는지와 적용했는지는 확인이 필요합니다.
- 위 두 점은 11/25 새 프로젝트로 옮기면서 정리됐습니다(아래 절). 팀원에게 보낼 파일은 11/25 수정까지 들어간 **최신** `langfuse_relay.py` 입니다.

### 새 Langfuse 프로젝트로 옮겨 다시 쌓기 (11/25)

**왜 옮겼나.** 옛 프로젝트 "My Project"에는 이미 중복이 많이 들어가 있었습니다(이 세션만 `llm_call` 4,001개, 실제 1,200개). 중복을 하나씩 지우려면 옛 ID를 모두 계산해야 합니다. 그래서 대시보드 숫자를 그대로 믿을 수 있게 새 프로젝트에 처음부터 다시 쌓았습니다. 옛 프로젝트에 다시 쌓을 이유는 없습니다.

**키 바꾸기.** kyu가 Langfuse 화면에서 새 프로젝트 "ghost alice project"와 키를 만들었습니다. `~/.ghost-alice/secrets.env` 의 `TEAM` 키 값만 새 키로 바꿨고, 옛 키는 지웠습니다. `LANGFUSE_TARGETS=TEAM`, `LANGFUSE_MEMBER=kyu` 는 그대로입니다. 키 값은 대화나 문서에 넣지 않습니다.

**훅·도구 기록 ID도 내용 기반으로 고침.** 10절 수정 뒤에도 훅 기록(`strict-hook-output.jsonl`)과 도구 기록(`io-trace.jsonl`)은 ID가 "파일 경로 + 바이트 위치"였습니다. 로그가 다시 써지거나 옮겨지거나 처음부터 다시 읽히면 중복될 수 있었습니다.

- 이제 줄 내용의 해시(`_row_digest`, 정렬한 JSON의 SHA-256 앞 32자)로 ID를 만듭니다.
- 같은 내용의 줄이 연달아 나오면(같은 도구를 1초 안에 두 번 호출) 반복 번호를 붙여 따로 남깁니다. 커서에 `last_digest`, `repeat` 를 저장합니다.
- 파일이 짧아져 처음부터 다시 읽을 때 이 두 값도 초기화합니다. 이 초기화가 커서 값을 읽기 전에 먼저 일어나도록 순서를 고쳤습니다.
- 테스트 `test_rewritten_hook_and_tool_logs_resend_with_the_same_ids` 를 추가했습니다. `test_langfuse_relay.py` 30개가 모두 통과합니다. 고치기 전 파일은 대화 임시 폴더에 `langfuse_relay.before-hookids.py` 로 남겼습니다(재부팅·정리 때 사라질 수 있음).

**비우고 다시 보내기 (11/25 11:17~11:30).**

1. relay를 껐습니다.
2. 새 프로젝트에 먼저 들어간 kyu 세션 4개(기록 19,224개)를 `DELETE /api/public/traces` 로 지웠습니다. 남은 기록이 0개인 것을 두 번 확인했습니다.
3. `~/.ghost-alice/langfuse-relay/state.json` 을 백업하고 `TEAM` 진행 위치를 처음으로 되돌렸습니다. 백업은 `state.json.before-new-project-20261125`(새 프로젝트로 옮기기 전)와 `state.json.before-resend-ids-20261125`(다시 보내기 전) 두 개입니다.
4. 11:21에 relay를 다시 켰습니다(프로세스 4212). 약 3분 만에 파일 96개를 다 보냈습니다.

**확인 결과 (이 세션 `95c6673a`, 11:26~11:30에 세 번 같은 값).**

| 항목 | 결과 |
|---|---|
| 모델 호출 `llm_call` | 1,302개 = 실제 메시지 1,302개, 중복 0 |
| 전체 기록 | 12,338개, 모두 다른 ID |
| 훅 기록 | 5,596개 모두 새 방식 ID와 일치, 옛 ID 0개 |

보낸 직후(11:25)에는 같은 ID가 두 번씩 보였지만 2분쯤 뒤 Langfuse가 하나로 합쳤습니다. 숫자는 보낸 뒤 몇 분 지나서 확인해야 합니다.

**알아 둘 점**

- 새 프로젝트에는 지금 kyu 기록만 있습니다. JY·SK는 새 키와 최신 relay 파일을 받아 적용해야 새 프로젝트에 쌓입니다. kyu가 메시지와 키를 따로 보냅니다.
- 팀원이 옮기기 전에 `LANGFUSE_MEMBER` 이름을 정해야 합니다. 나중에 이름을 바꾸면 ID가 달라져 중복이 생깁니다.
- 기록을 다시 보내야 할 때는 relay를 끄고, 해당 Langfuse 기록을 지우고, `state.json` 을 백업한 뒤 커서를 지우고, 다시 켭니다. 지우지 않고 다시 보내도 같은 ID라 합쳐지지만, 고치기 전 방식 ID가 남아 있으면 그것은 합쳐지지 않습니다.
- 확인 도구: `python perf/lf_dupes.py <세션 ID>`(모델 호출 중복 수, 읽기 전용, 키 출력 안 함).

### 이 세션에서 고친 것·배운 것

- 측정판 개선은 안내문을 줄이다가 규칙 세 개를 빠뜨렸고, receipt 형식도 깨뜨렸습니다. CI 테스트가 잡았고, PR #13에서 원래대로 되돌렸습니다. **문구를 줄일 때는 규칙이 빠지지 않았는지 기존 테스트로 확인해야 합니다.**
- "검토 실행 횟수"만으로는 검증 구멍(검토 뒤 답을 고쳐 쓰는 일)이 보이지 않았습니다. 그래서 집계에 "검토받은 답 그대로 전달" 지표를 넣었습니다.
- PR #12 보고서의 "Autopilot이 한 번도 기록하지 못함"은 틀린 말이라 고쳤습니다. 그런 기록은 측정한 범위에서만 없었습니다.
- 처음 쓴 "PR #13은 -38%"는 측정판 기준이었습니다. 최신판으로 다시 재니 -28%여서 고쳤습니다.
- 패치 파일과 시험 자료는 Windows에서 CRLF로 받아지면 결과가 달라집니다. 패치는 `git apply` 가 실패하고, 시험 자료는 바이트가 측정 때와 달라집니다. 그래서 증거 폴더 `.gitattributes` 로 막았습니다.
- **이 세션의 입력 확정 막힘 원인 (11/24 확인, 원장과 대화 기록은 읽기만 함).**
  - 16:14(KST)에 보조 에이전트(백그라운드 Agent, 팀원 보고서 요약)의 결과 보고가 들어왔습니다. 약 1만 자였고, Claude Code는 이것을 `queued_command`(`commandMode: prompt`, `origin.kind: "peer"`)로 대화에 넣었습니다.
  - 입력 훅이 이 보고를 원장 `pending_native_inputs` 맨 앞에 올렸습니다.
  - Core `native_input_actor`(`_shared/native_transcript.py`)는 `human` 과 알림만 알아봅니다. `peer` 는 `None` 이 됩니다.
  - 기준 버전 `reconcile_native_inputs`(`session-intent-analyzer/scripts/session_intent_ledger.py`)는 맨 앞이 판정되지 않으면 `break` 합니다. 그래서 뒤의 kyu 입력 19개가 모두 대기했습니다. 대기 목록은 20개이고, 바로 다음 입력 "한국어로해"는 `human` 으로 정상 판정됩니다.
  - 그 결과 응답 경로 등록이 `route-binding` 으로 거절되고, Stop 훅이 매번 `route-unavailable` 을 냈습니다.
  - 원장은 손으로 고치지 않았습니다. 새 세션은 이 막힘을 이어받지 않습니다.
  - **기준 버전에서는 백그라운드 보조 에이전트를 쓰지 않는 것이 안전합니다.** 팀원에게도 알릴 만합니다.
  - AidALL 최신(`5730668`)은 뒤에 사람 입력이 확인되면 앞 입력을 넘기므로 풀릴 가능성이 높습니다. 실제로 확인하지는 않았습니다. AidALL 제출 초안 C5로 넣었습니다.
- Langfuse relay는 재부팅하면 멈춥니다. `start_relay.cmd` 로 다시 켜면 꺼져 있던 동안의 기록도 이어서 보냅니다(파일별 읽은 위치를 저장).

### 남은 일

1. **A·B 재검토 결과 기다리기.** JY(비용 비교)와 SK(약한 모델 함정 시험)의 결과 보고서가 올라오면, `TESTING.md` 6절 기준으로 JY 방식 유지인지 kyu 방식 채택인지 정합니다. kyu 방식을 채택하면 할 일이 세 가지입니다. PR #13 브랜치를 `core/main` 위로 옮겨 PR로 올리고, 보고서·발표 자료의 결정 부분을 고치고, 인수인계 문서도 고칩니다.
2. JY·SK 요청 메시지를 kyu가 보냈는지 확인합니다. 둘 다 PR #25 합치기 전에 만든 메시지라 "합치기 전이면 `kyu/test-kit-ab` 브랜치" 문구는 빼고 보내라고 안내했습니다.
3. 최종 보고서와 AidALL 제출 초안을 팀 저장소에 올릴지 정합니다(kyu가 보류).
4. AidALL 제출: 최신 버전을 시험용 홈에 따로 설치해 C1~C5를 다시 재현하고, B1~B3 초안의 빈칸과 개인정보를 확인하고, 누가 낼지 정합니다.
5. PR #16(JY 보고서 추가분), PR #24(SK 이슈)를 검토합니다. SK가 PR #23을 혼자 합친 것은 팀 규칙(팀원 확인 뒤 합침)과 맞지 않아 팀에 알릴지 정합니다.
6. Langfuse 활용 개선: ① relay 중복 저장은 고쳤고, 새 프로젝트 "ghost alice project"에 kyu 기록을 다시 쌓았습니다(위 두 절). 다음은 ② JY·SK에게 새 키와 최신 `langfuse_relay.py`, `perf/lf_dupes.py` 를 보내고 `LANGFUSE_MEMBER` 이름을 먼저 통일하기, ③ 세션 태그(`PC`, `Core` 커밋), ④ 점수로 검증 결과 기록, ⑤ A·B 시험 기록도 Langfuse로 보내기입니다. 보조 에이전트 대화 기록이 빠지는지는 아직 확인하지 않았습니다.
7. Autopilot 효과 측정: 완료 조건이 있는 케이스로 켬·끔을 비교합니다. JY의 Autopilot 확인 케이스를 그대로 쓸 수 있습니다.
8. 기다리는 것: SK의 `skproject` PR, JY 재설치 확인 표.

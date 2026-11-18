# hook-monitor

Claude Code의 새 대화, Ghost-ALICE 훅 이벤트, 사례별 판정을 로컬 브라우저에서 본다. 각 팀원의 컴퓨터에서 따로 실행하며, 브라우저 주소 `127.0.0.1`은 그 컴퓨터에서만 열린다.

## 저장소를 받은 뒤 실행 순서 (Windows)

1. Python 3.11 이상과 Claude Code가 설치돼 있는지 확인한다. 훅 이벤트도 보려면 **호환되는 Ghost-ALICE Core와 Autopilot이 Claude Code에 설치되고 훅이 켜져 있어야 한다.** 이 모니터는 훅을 설치하거나 켜지 않는다.
2. PowerShell을 열고 **받은 `ghost-alice` 저장소 폴더**로 이동한다. 다음 명령의 `<받은 폴더>`를 실제 경로로 바꾼다.

   ```powershell
   cd "<받은 폴더>\ghost-alice"
   ```

3. 아래 한 줄로 모니터를 실행한다. PowerShell은 실행 후 닫아도 된다.

   ```powershell
   Start-Process python -ArgumentList 'hook-monitor/server.py' -WorkingDirectory (Get-Location).Path -WindowStyle Hidden
   ```

4. 브라우저에서 <http://127.0.0.1:8765/>를 연다. 페이지가 열리지 않으면 2~3번의 폴더 위치와 Python 설치를 확인한다. 이미 페이지가 열리면 3번을 다시 실행하지 않는다. 8765번을 다른 프로그램이 쓰고 있으면 3번 전에 `$env:HOOK_MONITOR_PORT = '8766'`처럼 다른 번호를 지정하고, 브라우저 주소의 번호도 같이 바꾼다.
5. 화면의 ‘**1. 사례**’에 사례 ID, 사전 문맥, 사용자 입력, 기대 행동, 실패 조건을 한 줄씩 입력하고 ‘**사례 저장**’을 누른다.
6. Claude Code에서 **2번과 같은 저장소 폴더**를 열고 새 채팅을 시작한다. 필요한 사전 문맥을 제공하고, 모니터에 적은 ‘사용자 입력’ 문장을 보낸다. 모니터의 ‘**2. Claude Code 대화 기록**’에 새 세션이 자동으로 나타난다. 여러 세션이 보이면 ‘실시간 세션’에서 방금 시작한 세션을 선택한다. ‘**3. 실제 답변·도구 호출**’에는 고른 세션에서 사용자가 보낸 말, Claude의 답변, Claude가 부른 도구 이름이 순서대로 나온다(최근 300개).
7. Claude Code의 답변이 끝나면 모니터의 ‘**4. 실패 조건 판정**’에서 각 조건을 선택하고 근거를 적어 ‘**판정 저장**’을 누른다. ‘**6. 저장된 결과 다시 보기**’에서 저장한 사례·대화·훅 이벤트·판정을 다시 확인한다.

같은 Claude Code 채팅을 계속 쓰면서 모니터만 새 구간으로 시작하려면 ‘**지금부터 새로 보기**’를 누른다. 그 뒤 들어온 대화·이벤트만 화면과 새 판정에 들어간다. ‘**전체 기록 다시 보기**’를 누르면 해당 채팅의 전체 기록이 다시 보인다. 이 버튼은 Claude Code의 대화 문맥을 지우지 않는다. 모니터 코드를 바꾼 뒤에는 모니터 서버를 재시작해야 새 구간을 판정에 저장할 수 있다.

각 팀원의 판정과 대화는 자기 컴퓨터의 `hook-monitor/captures/`에 저장된다. 노트북을 다시 켜면 2~4번으로 모니터를 다시 실행한다. Claude Code에서 작업 폴더를 다르게 열면 자동 연결이 안 될 수 있다.

## ‘5. 같은 세션의 훅·원장 · 흐름 해설’ 읽는 법

이 영역은 한 번의 입력(턴)마다 훅이 실제로 실행된 순서를 다섯 단계로 보여 준다.

| 단계 | 실행되는 것 | 여기서 확인할 것 |
| --- | --- | --- |
| ① 입력 접수 | `SessionStart`, `UserPromptSubmit` 훅과 원장의 입력 기록 | 입력이 “사람이 보낸 입력”으로 확정됐는가. 확정되지 않은 입력이 남으면 그 세션에서는 작업 경로 등록이 거부된다. |
| ② 의도·경로 기록 | 에이전트가 원장 명령으로 남긴 목표·완료 기준·작업 경로 | 에이전트가 적은 목표가 내 의도와 같은가. 작업 경로를 등록했는가, 등록이 거부됐는가. |
| ③ 도구 사용 | `PreToolUse`, `PostToolUse` 훅 | 도구를 몇 번 썼는가. Autopilot이 기록을 준비했는가. |
| ④ 답변 종료 점검 | `Stop · completion` 훅 | 답변을 막았는가. 막은 사유 코드와 다시 진행하는 방법. |
| ⑤ 완료 기록 | `Stop · Autopilot` 훅 | 완료 근거가 기록됐는가. 기록하지 못해도 답변은 막지 않는다. |

- 결과는 정상·참고·주의·막힘·훅 오류로 표시한다. 훅은 답변을 막을 때도 종료 코드 0으로 끝나므로, 종료 코드가 아니라 훅이 남긴 판단으로 표시한다.
- 막히거나 주의할 기록마다 카드가 붙는다. 카드는 “왜”, “다시 진행하려면”, “개선 힌트”를 적고, ‘원문 보기’에 Ghost-ALICE가 실제로 남긴 메시지를 그대로 둔다. 해설 문장은 `explain.py` 한 곳에 있으며, 목록에 없는 코드는 ‘해설 미등록’으로 표시하고 원문을 보여 준다.
- 맨 위 네 칸은 지금 상태다: 원장에 기록된 목표와 완료 기준, 입력 대기열, 작업 경로, 경계 계약.
- **경계 계약은 Ghost-ALICE가 내용을 기계로 검사하지 않는다.** Core는 “계약이 필요하다고 표시했으면 계약 ID가 등록됐는가”만 확인한다. 화면은 에이전트가 대화에 선언한 계약문을 보여 주며, 허용·금지 대상과 실제 도구 사용을 맞춰 보는 일은 사람이 한다.
- ‘볼 세션’에서 지난 세션을 고르면 다시 볼 수 있다. 한 번 열어 본 세션은 `captures/timelines/`에 자동 저장되므로 원본 훅 로그가 없어진 뒤에도 ‘저장본’으로 열린다.

모니터가 저장소 폴더 밖에 있으면 실행 전에 `$env:GHOST_ALICE_WORKSPACE`에 Claude Code 작업 폴더의 절대경로를 지정하고 `server.py`의 절대경로로 실행한다. 기록 원장이 작업 폴더의 `.tmp/session-intent` 또는 `작업 폴더/ghost-alice/.tmp/session-intent`가 아닌 곳에 있으면 `$env:GHOST_ALICE_LEDGER_ROOT`에 실제 원장 폴더를 지정한다.

## Langfuse로 보내기

‘6. 저장된 결과 다시 보기’의 ‘**저장된 결과 Langfuse로 보내기**’ 버튼을 누르면 판정을 저장한 세션마다 다음을 Langfuse로 보낸다. 명령줄에서는 `python hook-monitor/langfuse_sync.py`로 같은 작업을 한다.

| 모니터 기록 | Langfuse에서 보이는 곳 |
| --- | --- |
| 사례 (`case.json`) | Datasets → `ghost-alice-benchmark`의 항목 |
| 판정 (`runs.jsonl`) | 세션의 Scores: 조건별 `<사례 ID> · 조건 N`(pass/fail)과 전체 `case-result`, 판정 근거는 comment |
| Ghost-ALICE 훅 흐름과 해설 | 같은 세션의 `Ghost-ALICE · turn N` 트레이스(턴마다 하나). 트레이스의 output에 턴 요약과 단계별 결과가 들어가고, 5번 화면의 각 단계가 관찰 항목 하나가 된다. 막힘·주의 항목의 output에는 화면과 같은 “왜 / 다시 진행하려면 / 개선 힌트 / 원문”이 들어가며 WARNING, 훅 오류는 ERROR 수준이다. 태그는 `ghost-alice:<결과>`(ok, warn, resumed, unresolved, error), 막힘이 있으면 `ghost-alice:block`, 사유 코드별 `ghost-alice:<코드>`(예: `ghost-alice:route-unavailable`)이다. |

판정을 저장하지 않은 세션도 ‘5. 같은 세션의 훅·원장 · 흐름 해설’의 ‘**이 세션의 훅 흐름을 Langfuse로 보내기**’ 버튼으로 훅 흐름만 보낼 수 있다. 명령줄에서는 `python hook-monitor/langfuse_sync.py <세션 ID>`다. 세션이 끝났고 끝나지 않은 마지막 턴까지 보내려면 뒤에 `--final`을 붙인다. 이 경로는 훅 판단과 해설, 훅이 남긴 원문 메시지, 원장 이벤트 종류만 보낸다. 대화 문장, 입력 미리보기, 원장의 의도 요약 문장은 보내지 않는다.

훅 흐름은 Langfuse v4의 OpenTelemetry 수집 주소(`/api/public/otel/v1/traces`)로 보낸다. Langfuse에서 값을 다시 읽는 코드를 추가할 때는 `GET /api/public/v2/observations`를 쓴다. `GET /api/public/traces` 같은 이전 조회 주소는 2026-11-16부터 Langfuse Cloud에서 쓸 수 없다.

Claude Code 대화 자체는 Langfuse Claude Code 플러그인(`langfuse-observability`)이 보낸다. 플러그인과 이 모니터 모두 Claude 세션 ID를 Langfuse 세션 ID로 쓰므로 Sessions 화면에서 대화, 훅 판단, 판정이 한 세션에 모인다. 플러그인을 켜기 전에 진행한 세션은 대화 없이 훅 판단과 판정만 보인다.

키는 환경 변수 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`에서 먼저 찾고, 없으면 작업 폴더의 `.env`에서 읽는다. 보내는 내용에는 사례 원문, 판정 근거, 훅 출력(최대 4000자)이 포함되므로 Langfuse 프로젝트에 접근하는 사람 모두가 볼 수 있다.

### 턴마다 한 번만 보낸다

Langfuse는 트레이스와 관찰 항목을 고칠 수 없는 기록으로 다룬다. 같은 ID로 다시 보내면 덮어쓰지 않고 중복으로 저장되며, 중복은 집계 수치를 부풀린다([Langfuse 설명](https://langfuse.com/faq/all/tracing-data-updates)). 그래서 훅 흐름은 다음 규칙으로 보낸다. 버튼, 명령줄, 자동 전송 모두 같다.

- 끝난 턴만 보낸다. 끝난 턴은 뒤에 다음 턴이 있거나, 답변 종료 점검이 풀리지 않은 막힘 없이 끝난 턴이다. 진행 중인 턴과 막힌 채 멈춘 턴은 기다렸다가, 다음 턴이 시작되거나 세션이 끝날 때 보낸다.
- 한 번 보낸 턴은 다시 보내지 않는다. 보낸 턴은 `captures/langfuse-sent/<세션 ID>.json`에 Langfuse 프로젝트별로 적힌다. 키를 다른 프로젝트 것으로 바꾸면 그 프로젝트에는 끝난 턴을 한 번씩 새로 보낸다.
- 이 파일을 지우면 그 세션을 통째로 다시 보내 Langfuse에 중복이 생긴다. 파일을 읽을 수 없으면 보내지 않고 오류를 낸다.
- 보낸 뒤에 그 턴에 더해진 기록은 올라가지 않는다. Langfuse 쪽 기록을 고칠 방법이 없기 때문이다.
- 사례와 판정(Scores)은 누를 때마다 다시 보낸다. Langfuse가 같은 ID의 점수와 데이터셋 항목은 덮어쓴다.

### User ID

훅 기록에는 대화 기록과 같은 User ID를 붙인다. 환경 변수 `LANGFUSE_USER_ID`, 작업 폴더 `.env`의 `LANGFUSE_USER_ID`, Langfuse 플러그인에 설정한 User ID(`~/.claude/settings.json`의 `pluginConfigs`) 순서로 찾는다. 어디에도 없으면 붙이지 않는다. Langfuse가 사용자로 걸러 볼 수 있도록 트레이스의 모든 관찰 항목에 `langfuse.user.id`로 넣는다.

## 훅 기록 자동 전송

[auto_send.py](auto_send.py)를 Claude Code의 `Stop`, `SessionEnd` 훅으로 등록하면 Claude 답변이 끝날 때마다 그 세션에서 새로 끝난 턴의 훅 흐름이 Langfuse로 올라간다.

- 훅은 입력의 `session_id`와 `hook_event_name`만 읽고 별도 작업을 띄운 뒤 바로 종료 코드 0으로 끝난다. 전송이 실패해도 Claude 답변은 늦어지거나 막히지 않는다.
- 별도 작업은 5초 기다린 뒤 그 세션의 훅 흐름을 직접 만들어 `langfuse_sync.sync_session`으로 보낸다. 5초를 기다리는 이유는 같은 시점에 도는 Ghost-ALICE Stop 훅의 기록까지 담기 위해서다. 모니터가 저장하는 파일(`captures/timelines/`)은 읽기만 하고 쓰지 않으며, 모니터가 꺼져 있어도 동작한다.
- 보내는 규칙은 위 ‘턴마다 한 번만 보낸다’와 같다. `SessionEnd` 때는 세션의 마지막 전송이므로 끝나지 않은 턴도 함께 보낸다.
- 보내는 곳은 버튼과 같다. 환경 변수나 작업 폴더 `.env`의 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`이 가리키는 프로젝트다. 대화 기록과 한 세션에 모이게 하려면 Langfuse 플러그인과 같은 프로젝트의 키를 넣는다.
- 시도마다 `captures/auto-send.log`에 JSON 한 줄이 남는다: 시각, 세션, 성공 여부, 마지막 전송 여부(`final`), 이번에 보낸 턴 수(`traces`)와 기록 수(`observations`), 전에 보내서 건너뛴 턴 수(`skipped`), 아직 끝나지 않아 기다리는 턴 수(`waiting`), 또는 오류.

등록하려면 Claude Code 작업 폴더의 `.claude/settings.local.json`에 다음을 넣는다. 두 군데를 자기 PC의 값으로 바꾼다. `<python 경로>`는 PowerShell에서 `(Get-Command python).Source`로 나오는 경로이고, `<받은 폴더>`는 위 실행 순서 2번의 폴더다. 경로의 `\`는 `/`로 바꿔 적는다. 파일에 이미 `"hooks"`가 있으면 그 안에 `Stop`, `SessionEnd` 항목만 더한다.

```json
"hooks": {
  "Stop": [{"hooks": [{"type": "command", "command": "<python 경로> <받은 폴더>/ghost-alice/hook-monitor/auto_send.py"}]}],
  "SessionEnd": [{"hooks": [{"type": "command", "command": "<python 경로> <받은 폴더>/ghost-alice/hook-monitor/auto_send.py"}]}]
}
```

예: `C:/Users/홍길동/AppData/Local/Programs/Python/Python312/python.exe C:/work/ghost-alice/hook-monitor/auto_send.py`

테스트는 [test_auto_send.py](test_auto_send.py)와 [test_langfuse_send.py](test_langfuse_send.py)에 있다.

## 종료

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*hook-monitor/server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId }
```

모니터는 한 번에 하나만 실행한다. 이미 실행 중일 때 다시 실행하면 새 프로세스는 포트 사용 중 오류를 내고 끝난다. `server.py`, `timeline.py`, `explain.py`, `langfuse_sync.py`를 고친 뒤에는 위 명령으로 종료하고 다시 실행해야 반영된다. `index.html`만 고쳤으면 브라우저 새로 고침으로 충분하다.

## 테스트

해설 문장의 분류, 턴 조립, 저장본 다시 보기, Langfuse로 나가는 내용을 검사한다. 작업 폴더에서 실행한다.

```powershell
$env:PYTHONUTF8 = '1'; python -m unittest discover -s hook-monitor -p "test_*.py"
```

## 저장과 공유

`captures/`에는 사례, 대화, 훅 기록, 판정, 세션별 훅 흐름 저장본(`timelines/`)이 저장된다. 대화 원문과 개인 경로가 포함될 수 있으므로 `.gitignore`로 Git 추적에서 제외한다. 팀에 결과를 공유할 때는 필요한 부분만 검토·익명화해 별도 파일로 올린다. GitHub에 코드를 올려도 각자의 실시간 화면이나 로컬 기록이 자동으로 공유되지는 않는다.

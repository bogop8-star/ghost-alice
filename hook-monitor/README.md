# Ghost-ALICE 사례 모니터

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

4. 브라우저에서 <http://127.0.0.1:8765/>를 연다. 페이지가 열리지 않으면 2~3번의 폴더 위치와 Python 설치를 확인한다. 이미 페이지가 열리면 3번을 다시 실행하지 않는다.
5. 화면의 **‘1. 사례’**에 사례 ID, 사전 문맥, 사용자 입력, 기대 행동, 실패 조건을 한 줄씩 입력하고 **‘사례 저장’**을 누른다.
6. Claude Code에서 **2번과 같은 저장소 폴더**를 열고 새 채팅을 시작한다. 필요한 사전 문맥을 제공하고, 모니터에 적은 ‘사용자 입력’ 문장을 보낸다. 모니터의 **‘2. Claude Code 대화 기록’**에 새 세션이 자동으로 나타난다. 여러 세션이 보이면 ‘실시간 세션’에서 방금 시작한 세션을 선택한다.
7. Claude Code의 답변이 끝나면 모니터의 **‘4. 실패 조건 판정’**에서 각 조건을 선택하고 근거를 적어 **‘판정 저장’**을 누른다. **‘6. 저장된 결과 다시 보기’**에서 저장한 사례·대화·훅 이벤트·판정을 다시 확인한다.

같은 Claude Code 채팅을 계속 쓰면서 모니터만 새 구간으로 시작하려면 **‘지금부터 새로 보기’**를 누른다. 그 뒤 들어온 대화·이벤트만 화면과 새 판정에 들어간다. **‘전체 기록 다시 보기’**를 누르면 해당 채팅의 전체 기록이 다시 보인다. 이 버튼은 Claude Code의 대화 문맥을 지우지 않는다. 모니터 코드를 바꾼 뒤에는 모니터 서버를 재시작해야 새 구간을 판정에 저장할 수 있다.

각 팀원의 판정과 대화는 자기 컴퓨터의 `hook-monitor/captures/`에 저장된다. 노트북을 다시 켜면 2~4번으로 모니터를 다시 실행한다. Claude Code에서 작업 폴더를 다르게 열면 자동 연결이 안 될 수 있다.

모니터가 저장소 폴더 밖에 있으면 실행 전에 `$env:GHOST_ALICE_WORKSPACE`에 Claude Code 작업 폴더의 절대경로를 지정하고 `server.py`의 절대경로로 실행한다. 기록 원장이 작업 폴더의 `.tmp/session-intent` 또는 `작업 폴더/ghost-alice/.tmp/session-intent`가 아닌 곳에 있으면 `$env:GHOST_ALICE_LEDGER_ROOT`에 실제 원장 폴더를 지정한다.

## Langfuse로 보내기

‘6. 저장된 결과 다시 보기’에서 **보낼 Langfuse 프로젝트를 선택한 뒤** ‘저장된 결과 Langfuse로 보내기’를 누른다. 기존 `.env`의 키는 ‘기본 프로젝트’로 표시된다. 새 프로젝트는 그 프로젝트의 Langfuse 주소, Public Key, Secret Key를 화면의 ‘새 Langfuse 프로젝트 등록’에 넣는다. 등록하면 Langfuse에서 확인한 프로젝트 이름이 선택 목록에 나타난다. 키는 이 컴퓨터의 `captures/langfuse-projects.json`에 저장되며 브라우저로 다시 보내지지 않는다.

선택한 프로젝트로 다음을 보낸다. 전송된 항목은 프로젝트별로 `captures/langfuse-sent.json`에 기록해 다음에는 새 항목만 보낸다.

| 모니터 기록 | Langfuse에서 보이는 곳 |
| --- | --- |
| 사례 (`case.json`) | Datasets → `ghost-alice-benchmark`의 항목 |
| 판정 (`runs.jsonl`) | 세션의 Scores: 조건별 `<사례 ID> · 조건 N`(pass/fail)과 전체 `case-result`, 판정 근거는 comment |
| Ghost-ALICE 훅 실행과 판단 | 같은 세션의 `Ghost-ALICE · turn N` 트레이스. 훅마다 span 하나이며 output에 판단(decision)과 이유(reason)가 들어간다. block/deny 판단은 WARNING, 훅 오류는 ERROR 수준으로 표시하고, 차단이 있던 턴에는 `ghost-alice:block` 태그를 붙인다. |

Claude Code 대화 자체는 Langfuse Claude Code 플러그인(`langfuse-observability`)이 보낸다. 플러그인도 **같은 Langfuse 프로젝트의 키로 설정한 경우에만** 대화와 모니터 결과가 그 프로젝트에서 함께 보인다. 다른 프로젝트로 모니터 결과를 보내면 그 프로젝트에는 대화가 자동 복사되지 않는다.

기본 프로젝트 키는 환경 변수 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`에서 먼저 찾고, 없으면 작업 폴더의 `.env`에서 읽는다. 보내는 내용에는 사례 원문, 판정 근거, 훅 출력(최대 4000자)이 포함되므로 선택한 Langfuse 프로젝트에 접근하는 사람 모두가 볼 수 있다.

누가 보냈는지 표시하려면 **각자 자신의 작업 폴더 `.env`**에 `LANGFUSE_MEMBER=이름`을 추가한다. 예: `LANGFUSE_MEMBER=ctale`. 이 값은 선택한 프로젝트와 관계없이 새로 전송하는 사례·점수·훅 기록의 `metadata.member`에 들어간다. 이미 전송한 항목은 중복 방지를 위해 다시 보내지 않으므로 이전 기록에는 소급해서 붙지 않는다. `.env`를 수정한 뒤에는 모니터 서버를 다시 시작할 필요 없이 화면에서 전송하면 된다.

## 종료

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*hook-monitor/server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId }
```

## 저장과 공유

`captures/`에는 사례, 대화, 훅 기록, 판정이 저장된다. 대화 원문과 개인 경로가 포함될 수 있으므로 `.gitignore`로 Git 추적에서 제외한다. 팀에 결과를 공유할 때는 필요한 부분만 검토·익명화해 별도 파일로 올린다. GitHub에 코드를 올려도 각자의 실시간 화면이나 로컬 기록이 자동으로 공유되지는 않는다.

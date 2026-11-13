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

각 팀원의 판정과 대화는 자기 컴퓨터의 `hook-monitor/captures/`에 저장된다. 노트북을 다시 켜면 2~4번으로 모니터를 다시 실행한다. Claude Code에서 작업 폴더를 다르게 열면 자동 연결이 안 될 수 있다.

모니터가 저장소 폴더 밖에 있으면 실행 전에 `$env:GHOST_ALICE_WORKSPACE`에 Claude Code 작업 폴더의 절대경로를 지정하고 `server.py`의 절대경로로 실행한다. 기록 원장이 작업 폴더의 `.tmp/session-intent` 또는 `작업 폴더/ghost-alice/.tmp/session-intent`가 아닌 곳에 있으면 `$env:GHOST_ALICE_LEDGER_ROOT`에 실제 원장 폴더를 지정한다.

## 종료

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*hook-monitor/server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId }
```

## 저장과 공유

`captures/`에는 사례, 대화, 훅 기록, 판정이 저장된다. 대화 원문과 개인 경로가 포함될 수 있으므로 `.gitignore`로 Git 추적에서 제외한다. 팀에 결과를 공유할 때는 필요한 부분만 검토·익명화해 별도 파일로 올린다. GitHub에 코드를 올려도 각자의 실시간 화면이나 로컬 기록이 자동으로 공유되지는 않는다.

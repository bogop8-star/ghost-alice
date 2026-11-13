# Ghost-ALICE 사례 모니터

Claude Code의 새 대화, Ghost-ALICE 훅 이벤트, 사례별 판정을 로컬 브라우저에서 본다. 각 팀원의 컴퓨터에서 따로 실행하며, 브라우저 주소 `127.0.0.1`은 그 컴퓨터에서만 열린다.

## 설치와 실행 (Windows PowerShell)

1. Python 3.11 이상과 Claude Code가 설치된 컴퓨터에 이 폴더를 받는다.
2. PowerShell에서 **Claude Code를 실행할 작업 폴더**로 이동한다.
3. 모니터 코드가 그 작업 폴더의 `hook-monitor` 하위 폴더에 있다면 다음 한 줄을 실행한다.

   ```powershell
   Start-Process python -ArgumentList 'hook-monitor/server.py' -WorkingDirectory (Get-Location).Path -WindowStyle Hidden
   ```

4. 브라우저에서 <http://127.0.0.1:8765/>를 연다. 이미 실행 중이면 다시 시작하지 않는다.

모니터 폴더가 작업 폴더 밖에 있으면, 실행 전에 `$env:GHOST_ALICE_WORKSPACE`에 Claude Code 작업 폴더의 절대경로를 지정하고 `server.py`의 절대경로로 실행한다. 기록 원장이 작업 폴더의 `.tmp/session-intent` 또는 `작업 폴더/ghost-alice/.tmp/session-intent`가 아닌 곳에 있으면 `$env:GHOST_ALICE_LEDGER_ROOT`에 실제 원장 폴더를 지정한다.

## 사용

- '1. 사례'에서 사례 ID, 사전 문맥, 사용자 입력, 기대 행동, 실패 조건을 입력하고 저장한다.
- Claude Code에서 해당 작업 폴더를 열고 새 채팅에 사용자 입력을 보낸다. 모니터가 새 대화를 자동으로 표시한다.
- 답변이 끝나면 조건별로 판정하고 근거를 적어 저장한다. '6. 저장된 결과 다시 보기'에서 저장한 판정을 열 수 있다.
- 훅 이벤트를 보려면 각 팀원의 Claude Code에 Ghost-ALICE 훅이 설치·활성화돼 있어야 한다. 모니터는 훅을 설치하거나 켜지 않는다.

종료 명령:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*hook-monitor/server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId }
```

## 저장과 공유

`captures/`에는 사례, 대화, 훅 기록, 판정이 저장된다. 대화 원문과 개인 경로가 포함될 수 있으므로 `.gitignore`로 Git 추적에서 제외한다. 팀에 결과를 공유할 때는 필요한 부분만 검토·익명화해 별도 파일로 올린다. GitHub에 코드를 올려도 각자의 실시간 화면이나 로컬 기록이 자동으로 공유되지는 않는다.

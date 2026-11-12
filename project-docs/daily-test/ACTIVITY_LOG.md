# 일상 질문 테스트 작업 기록

2026-11-12 사용자 요청("지금부터 실시하는 모든 것은 기록")에 따라, 이 테스트에서 한 일을 시간순으로 남깁니다. 실행 결과 원본은 `results/`에 있습니다.

| 시각(KST) | 수행자 | 한 일 | 결과·근거 |
| --- | --- | --- | --- |
| 21:4x | Claude Code | `questions.json` 작성: 10문항(자동 6, 대화형 4), 문항마다 유형·관찰 포인트·실패 조건 | 이 폴더 `questions.json` |
| 21:4x | Claude Code | Ghost-ALICE 끈 상태 비교 방법 확인: `claude --help`에서 `--safe-mode`가 CLAUDE.md·skills·hooks를 모두 끄는 것을 확인. `--bare`는 구독 로그인(OAuth)을 읽지 않아 제외 | `claude --help` 출력 |
| 21:4x | Claude Code | `run_daily_test.py` 작성: 자동 문항을 켬(on)·끔(off, `--safe-mode`)으로 각각 `claude -p` 실행, 빈 임시 폴더 사용, 켬 실행은 원장 읽기 전용 조회, 결과는 비식별화해 `results/<run_id>.jsonl`에 추가, 실행 요약은 `results/run-log.md` | 이 폴더 `run_daily_test.py` |
| 21:42 | Claude Code | 시험 실행: D08을 끔(off) 모드로 1회. `--safe-mode`가 구독 로그인으로 동작하는지 확인 | 19.5초, 1턴, 오류 0, $0.0584. `results/20261112-214224.jsonl` |
| 21:43 | Claude Code | 본 실행 시작: 자동 6문항(D01·D03·D06·D07·D08·D10) × 켬·끔 = 12회, 모델은 CLI 기본값, 백그라운드 실행 | 결과는 `results/` 새 파일에 기록 중 |
| 21:50 | Claude Code | 본 실행 완료: 12회, 오류 0, $1.8562, 모델 claude-opus-5-5 | `results/20261112-214258.jsonl`, `results/run-log.md` |
| 21:5x | Claude Code | 12개 답변 원문을 읽고 실패 조건으로 채점, 요약 작성 | `results/20261112-214258-summary.md` |
| 21:5x | Claude Code | 주요 결과: D03 켬 모드에서 날씨 답 대신 거버넌스 기록 실패 보고만 나옴(끔은 정상). 켬 6회 모두 원장 대기 상태(O1 재현 6/6). 끔 모드가 공유 기록 규칙도 끄는 비교 조건 한계 기록 | 같은 요약 파일 |
| 21:5x | Claude Code | `observations.md`에 O6(D03) 추가, O1 재현 기록 갱신 | `../observations.md` |
| 11-13 | Claude Code | 사용자 선택("D03 3회 재실행")에 따라 D03을 켬·끔 각 3회 재실행 시작(`run_daily_test.py --ids D03` 3번, 끔은 대조군) | 결과는 `results/`의 새 run 파일 3개 |
| 11-13 08:45 | Claude Code | D03 반복 실행 완료: 6회, 오류 0, $1.2974. 켬 3/3 실패(최종 답이 응답 경로 기록 실패 설명, 2회는 영어), 끔 3/3 통과 | `results/20261113-083949.jsonl`, `-084145.jsonl`, `-084326.jsonl` |
| 11-13 08:5x | Claude Code | 답변 원문 채점, 반복 실행 요약 작성, `observations.md` O6 재현 기록 갱신 | `results/20261113-D03-rerun-summary.md`, `../observations.md` |

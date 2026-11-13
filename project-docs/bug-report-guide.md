# 버그 보고서 작성 지침

팀원이 Claude Code나 Codex에 버그 보고서·이슈 초안을 요청하면, 응답 모델은 원본 저장소(`AidALL/ghost-alice`)의 버그 양식인 [`.github/ISSUE_TEMPLATE/bug_report.yml`](../.github/ISSUE_TEMPLATE/bug_report.yml)의 항목과 순서를 그대로 따릅니다. 양식 파일이 바뀌면 이 문서보다 양식 파일이 우선합니다.

## 본문 구조

GitHub 이슈 양식은 각 항목을 `### <label>` 제목으로 표시합니다. 응답 모델은 초안을 같은 모양으로 씁니다. 제목은 `[bug]: `로 시작하고, 라벨은 `bug`입니다.

~~~markdown
### Platform

Claude Code | Codex | Installer only | Documentation | Other 중 하나

### Operating system and shell

예: Windows 11 / PowerShell 7

### Summary

무엇이 잘못됐는지 한두 문장

### Steps to reproduce

1. 기준 commit과 설치 명령
2. 입력하거나 실행한 내용
3. 관찰한 결과

### Expected behavior

기대한 동작

### Actual behavior

실제로 일어난 동작

### Redacted logs or output

```text
비식별 처리한 doctor 출력, 훅 거부 메시지, 세션 로그 일부
```

### Safety checks

- [x] I removed secrets and private data from this report.
- [x] This is not a security vulnerability report.
~~~

필수 항목은 Platform, Operating system and shell, Summary, Steps to reproduce, Expected behavior, Actual behavior, Safety checks입니다. Redacted logs or output만 선택 항목이며, 증거가 있으면 채웁니다. 응답 모델은 확인하지 못한 항목을 추측으로 채우지 않고 `확인 필요`로 남긴 뒤 팀원에게 물어봅니다.

## 지켜야 할 규칙

- 응답 모델은 토큰, API 키, 이메일, 사용자 이름이 들어간 경로, 개인 프로젝트 내용, 원문 프롬프트를 지우고 씁니다. 예를 들어 `C:\Users\<이름>\`은 `C:\Users\<user>\`로 바꿉니다.
- 응답 모델은 두 Safety checks 항목을 실제로 확인한 경우에만 체크합니다. 보안 취약점이면 공개 이슈 초안을 쓰지 않고 [SECURITY.md](../SECURITY.md)의 비공개 신고 경로를 안내합니다.
- [project-plan.md](project-plan.md)의 수행 방법에 따라, 두 명 이상이 재현하지 못한 사례는 이슈가 아니라 관찰 기록으로 남깁니다. 응답 모델은 재현 여부를 초안 앞에 한 줄로 밝힙니다.
- 이슈는 팀 fork(`bogop8-star/ghost-alice`)에 먼저 올립니다. 응답 모델은 팀원이 명시적으로 요청한 경우에만 `gh issue create`로 이슈를 만들고, 그때도 위 구조의 본문을 `--body-file`로 넘겨 양식 항목을 빠뜨리지 않습니다.

## 설정 확인 방법

팀원은 이 저장소 폴더에서 Claude Code를 새로 열고 다음과 같이 묻습니다.

```text
버그 보고서 작성 지침이 어디에 설정돼 있는지 파일 경로로 알려주고, 빈 버그 보고서 초안을 하나 보여줘.
```

초안이 Platform, Operating system and shell, Summary, Steps to reproduce, Expected behavior, Actual behavior, Redacted logs or output, Safety checks 순서로 나오면 설정이 적용된 것입니다.

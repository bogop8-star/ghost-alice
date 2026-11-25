# Ghost-ALICE·Autopilot 오류 메시지 목록

2026-11-25 · jy

오류 메시지를 알아보기 쉽게 고치기 전에, 어떤 메시지가 있고 실제로 얼마나 나왔는지 모은 목록입니다.

- 코드 기준: Ghost-ALICE Core `core/main` `450e4b3`(JY 방식, 팀 기본), Autopilot `v0.5.1`
- 실제 횟수 기준: 훅 기록 `strict-hook-output.jsonl`
  - 이 PC 실제 설치본: 세션 373개 (2026-11-12 ~ 11-25, Core `c6019ac`)
  - 시험용 홈 A(`450e4b3`): 세션 79개 (11-24 ~ 11-25)
  - 시험용 홈 B(`15b6e2b`): 세션 63개 (11-24)

## 1. 사용자가 보는 곳

오류 메시지는 대부분 Claude가 답을 끝내려 할 때 Stop 훅이 답을 한 번 멈춰 세우면서 나옵니다. Claude Code 화면에는 `Stop hook feedback:` 아래에 영어로 이렇게 뜹니다.

```text
[completion-gate] <사유 코드>: <영어 설명> repair-target: <고칠 대상>
delivery-route: <답 다시 보내는 방법>
<답 다시 보내는 방법 설명>
```

- 한 입력에서 처음 막힐 때는 답을 멈춥니다(아래 표의 "멈춤").
- 같은 입력에서 또 막히면 답은 그대로 내보내고 알림만 붙입니다(아래 표의 "알림"). 알림 문구는 2-3절에 있습니다.
- JY 방식(A, `450e4b3`)은 영어 아래에 한국어 안내 `[사용자 안내] 무엇이 막혔나 · 왜 · 다음에 할 일` 을 붙입니다. 사유 코드 6개에만 맞춤 설명이 있고, 나머지는 "완료 근거 기록이 Ghost-ALICE가 받는 형식과 맞지 않습니다"라는 공통 문구가 나옵니다.

Autopilot의 결과 코드는 훅 기록에만 남고 사용자 화면에는 나오지 않습니다(4절).

## 2. Ghost-ALICE 멈춤 메시지

### 2-1. 사유 코드 전체

"실제 횟수"는 멈춤/알림 횟수입니다. "한국어 안내"는 A에 맞춤 설명이 있는지입니다.

| 사유 코드 | 언제 나오나 (쉬운 말) | 실제 횟수: 이 PC | A | B | 한국어 안내 | 만드는 곳 |
| --- | --- | --- | --- | --- | --- | --- |
| `route-unavailable` (1) | 이번 입력에서 도구를 썼는데 "이번 일이 무슨 일인지" 적은 기록(응답 경로)이 없음 | 299 / 156 | 35 / 18 | 3 / 3 | 있음 | `native_completion.py` 150행 |
| `route-unavailable` (2) | 완료 근거를 내밀었는데 응답 경로가 먼저 등록돼 있지 않음 | (1)과 합산 | | | 있음 | `native_completion.py` 166행 |
| `native-activity-unavailable` | 이번 입력에서 도구를 썼는지 대화 기록으로 확인하지 못함 | 0 | 0 | 0 | 있음 | `native_completion.py` 154행 |
| `response-assessment-required` | 설명형 답인데 답을 근거와 맞춰 본 검토 기록이 없음 | 7 / 20 | 0 / 4 | 1 / 0 | 있음 | `completion_assessment.py` |
| `criterion-unbound` | 답에 적은 완료 근거가 어느 완료 조건에 해당하는지 연결되지 않음 | 18 / 52 | 0 | 0 / 8 | 있음 | `completion_assessment.py` |
| `claim-evidence-unbound` | 답의 일부 문장이 제시한 근거로 뒷받침되지 않음 | 0 | 0 | 0 | 있음 | `native_completion.py` 173행 |
| `assessment-unsupported` | 검토 결과 근거가 부족한 주장이 있음 | 0 | 0 | 0 | 있음 | `native_completion.py` 186행 |
| `assessment-required` | 완료 근거를 검토한 기록이 없거나 찾을 수 없음 | 0 / 2 | 0 | 0 / 7 | 공통 문구 | `completion_assessment.py` |
| `source-changed` | 검토할 때 본 원본 파일이 그 뒤에 바뀜 | 0 | 0 | 0 | 공통 문구 | `native_completion.py` 27행 |
| `source-unavailable` | 검토할 때 본 원본 파일을 다시 읽을 수 없음 | 0 | 0 | 0 | 공통 문구 | `native_completion.py` 29행 |
| `assessment-invalid` | 저장된 검토 기록이 형식이나 대상과 맞지 않음 | 0 | 0 | 0 | 공통 문구 | `completion_assessment.py` |
| `assessment-stale` | 검토 기록이 지금 입력·작업과 더는 맞지 않음 | 0 | 0 | 0 | 공통 문구 | `completion_assessment.py` 552행 |
| `assessment-conflict` | 같은 대상에 바꿀 수 없는 검토 기록이 이미 있음 | 0 | 0 | 0 | 공통 문구 | `completion_assessment.py` |
| `owner-mismatch` | 검토 기록이 다른 세션 것임 | 0 | 0 | 0 | 공통 문구 | `completion_assessment.py` |
| `proof-invalid` | 완료 근거나 확인 시각이 비었거나 형식이 틀림 | 0 | 0 | 0 | 공통 문구 | `completion_assessment.py` |
| `response-unbound` | 검토한 답과 실제 답이 연결되지 않음 | 0 | 0 | 0 | 공통 문구 | `completion_assessment.py` |
| `response-unsupported` | 검토 결과 답 전체가 근거로 뒷받침되지 않음 | 0 | 0 | 0 | 공통 문구 | `completion_assessment.py` |
| `capture-invalid` | Autopilot 기록용 자료가 형식에 맞지 않음 | 0 | 0 | 0 | 공통 문구 | `completion_assessment.py` 422행 |
| `assessment-unavailable` | 검토 기록을 읽다가 알 수 없는 오류가 남 | 0 | 0 | 0 | 공통 문구 | `native_completion.py` 197행 |
| 완료 표시 형식 오류 | `[completion-check]` 블록이 필요하거나 형식이 틀림 (2-2절) | 1 / 11 | 1 / 3 | 8 / 2 | 공통 문구 | `completion_check_validator.py` |
| `response-review-required` | (B 방식에만 있음) 읽고 답한 답을 한 번 검토하게 함 | - | - | 33 / 0 | 없음 | B의 Core |

이 PC에서 실제로 나온 멈춤·알림 566번 가운데 455번(80%)이 `route-unavailable` 이었습니다.

### 2-2. 완료 표시 형식 오류 문구 전체

Claude가 답 끝에 `[completion-check]` 나 `[partial-check]` 블록을 붙였는데 형식이 틀리면, 아래 문구가 사유 코드 자리에 그대로 나옵니다(`completion_check_validator.py`). 여러 개가 한 번에 붙어 나올 수 있습니다.

| # | 문구 | 쉬운 말 |
| --- | --- | --- |
| 1 | The caller requires a [completion-check] block with valid verification evidence, or [partial-check] … | 완료 표시 블록이 꼭 있어야 하는데 없음 |
| 2 | A response must use either [completion-check] or [partial-check], not both … | 두 블록을 같이 씀 |
| 3 | [gate-state] belongs to the opening surface and must not appear after [completion-check]. | 상태 블록을 맨 앞이 아니라 뒤에 씀 |
| 4 | [completion-check] must not contain duplicate … sections. | 같은 항목을 두 번 씀 |
| 5 | [completion-check] must include non-empty claim-evidence-map. | 주장과 근거 표가 비었음 |
| 6 | [partial-check] must declare nonempty, unique acceptance-criteria IDs. | 완료 조건 번호가 없거나 겹침 |
| 7 | [partial-check] requires scope: partial. | `scope: partial` 줄이 없음 |
| 8 | Every claim-evidence-map entry must include a non-empty claim. | 주장이 빈 줄이 있음 |
| 8-1 | Every claim-evidence-map entry must begin with an explicit claim. | 줄이 주장(claim)으로 시작하지 않음 |
| 8-2 | Claim-evidence-map entries must not contain duplicate fields. | 한 줄에 같은 항목을 두 번 씀 |
| 9 | Every claim-evidence-map entry must reference an acceptance-criteria criterion id. | 주장이 어느 완료 조건인지 안 적음 |
| 10 | Every claim-evidence-map entry must include evidence. | 근거가 빈 줄이 있음 |
| 11 | Every claim-evidence-map entry must include verdict: pass \| fail. | 통과/실패 판정이 없음 |
| 12 | Invalid verdict value in claim-evidence-map. … | 판정을 pass, fail 말고 다른 말로 씀 |
| 13 | Evidence entries cannot contain an 'unverified' verdict. … | 판정에 "확인 안 됨"을 씀 |
| 14 | [partial-check] requires nonempty unverified entries as '- criterion-id: reason' … | 못 끝낸 조건 목록 형식이 틀림 |
| 15 | Every [partial-check] criterion must have a verdict or an explicit unverified reason. | 판정도 이유도 없는 조건이 있음 |
| 16 | [completion-check] must include an unverified section. | "확인 안 된 것" 칸이 없음 |
| 17 | A finalized [completion-check] requires the unverified section to be 'none'. … | 끝났다면서 "확인 안 된 것"이 남아 있음 |

### 2-3. 두 번째로 막힐 때 붙는 알림 문구

같은 입력에서 두 번째로 막히면 답을 멈추지 않고 아래 알림을 붙입니다(`claude_stop_verification_hook.py` 144~153행). 이 PC에서 241번 나왔습니다.

| 고칠 대상 | 알림 문구 |
| --- | --- |
| 응답 경로 | `[completion-gate] Current work routing remains unresolved: <사유>` |
| 응답 검토 | `[completion-gate] Internal response review remains unresolved: <사유>` |
| 그 밖 | `[completion-gate] Core has not accepted the submitted completion proof after one retry. Remaining defect: <사유> …` |

### 2-4. 멈춤 메시지 끝에 붙는 안내 줄

모든 멈춤 메시지 끝에 Claude에게 주는 안내 두 줄이 붙습니다(`response_delivery.py`). 사용자에게는 뜻이 잘 안 보이는 부분입니다.

- `repair-target:` 고칠 대상. `response_route`(응답 경로), `response_review`(응답 검토), `completion_metadata`(완료 기록), `source_status`(원본 상태) 넷 중 하나
- `delivery-route:` 고친 뒤 답을 어떻게 다시 보낼지. 아래 넷 중 하나

| 값 | 뜻 |
| --- | --- |
| `preserve_answer_and_patch_metadata` | 답은 이미 보였으니 다시 쓰지 말고 고친 것만 말하라 |
| `corrected_complete_answer` | 바뀐 주장을 넣어 답 전체를 다시 내라 |
| `assembled_complete_payload` | 남겨 둔 답과 고친 것을 한 번에 합쳐 내라 |
| `resolve_host_delivery` | 답이 보였는지 상황을 보고 정하라 |

### 2-5. A 방식의 한국어 안내 문구

A(`450e4b3`)는 영어 멈춤 메시지 바로 아래에 한국어 안내 한 줄을 붙입니다(`claude_stop_verification_hook.py` 158~177행). 위 표들의 "쉬운 말" 칸은 이 목록을 만들며 풀어 쓴 설명이고, 화면에 실제로 나오는 한국어는 이 절의 문구뿐입니다.

처음 막힐 때:

```text
[사용자 안내] 무엇이 막혔나: Ghost-ALICE가 이번 답변을 끝내기 전에 한 번 멈췄습니다. 왜: <아래 설명> 다음에 할 일: 사용자가 할 일은 없습니다. 어시스턴트가 기록을 채운 뒤 이어서 답하고, 앞서 나온 답변 내용은 그대로 유효합니다.
```

두 번째로 막힐 때(답은 나가고 알림만 붙음):

```text
[사용자 안내] 무엇이 남았나: 답변은 그대로 나갔고, Ghost-ALICE 기록 하나가 채워지지 않았습니다. 왜: <아래 설명> 다음에 할 일: 사용자가 할 일은 없습니다. 답변을 그대로 쓰셔도 됩니다.
```

"왜:" 자리에 들어가는 설명:

| 사유 코드 | 왜: |
| --- | --- |
| `route-unavailable` | 이번 입력에서 파일을 바꾸거나 명령을 실행했는데, 그 작업의 목적을 적은 기록(response-route)이 없습니다. |
| `native-activity-unavailable` | 이번 입력에서 도구를 썼는지 대화 기록으로 확인하지 못했습니다. |
| `criterion-unbound` | 답변에 적힌 완료 근거가 어느 완료 조건에 해당하는지 연결되지 않았습니다. |
| `response-assessment-required` | 답변 내용을 근거와 대조한 검토 기록이 없습니다. |
| `claim-evidence-unbound` | 답변의 일부 문장이 제시한 근거로 뒷받침되지 않습니다. |
| `assessment-unsupported` | 검토 결과 답변의 주장 중 근거가 부족한 것이 있습니다. |
| 그 밖의 코드 전부(완료 표시 형식 오류 포함) | 완료 근거 기록이 Ghost-ALICE가 받는 형식과 맞지 않습니다. |

## 3. 그 밖의 Ghost-ALICE 메시지

| 나오는 때 | 문구 | 이 PC 실제 횟수 |
| --- | --- | --- |
| 입력할 때(UserPromptSubmit, `pending-merge-prompt`) | `Ghost-ALICE agent visibility profile set to minimal. Hook execution and strict session log…` | 25 |

이 밖에 설치 점검(`doctor`)과 업데이트 충돌(merge-companion) 메시지가 있지만, 시험과 일상 사용 기록에서는 나오지 않았습니다.

## 4. Autopilot 결과 코드

Autopilot은 답이 끝날 때마다(Stop, `adapter-autopilot-mode-continue`) 완료 기록 결과를 훅 기록에 남깁니다. `systemMessage` 가 비어 있어 사용자 화면에는 나오지 않습니다.

### 4-1. 실제로 나온 코드

| 코드 | 뜻 (쉬운 말) | 이 PC | A | B |
| --- | --- | --- | --- | --- |
| `skipped` | 기록할 작업이 없어 건너뜀 | 633 | 41 | 37 |
| `recording-unavailable` | 완료 기록을 남기지 못함 | 433 | 62 | 67 |
| `completion-body-invalid` | 완료 기록에 쓸 답·근거가 형식에 맞지 않음 | 307 | 61 | 65 |
| `authority-unavailable` | 사람이 승인한 입력인지 확인하지 못함 | 256 | 0 | 0 |
| `route-unavailable` | Ghost-ALICE 응답 경로가 없음 | 197 | 53 | 6 |
| `no-current-execution` | 지금 실행 중인 작업이 등록돼 있지 않음 | 112 | 5 | 31 |
| `v2-unit-state` | 작업 단위 상태로 완료를 확인함 | 87 | 18 | 17 |
| `applied` | 완료 기록을 반영함 | 68 | 24 | 39 |
| `dispatched` | 다음 작업을 넘겨줌 | 5 | 5 | 10 |

### 4-2. 코드에 있는 오류 코드 전체

Autopilot `v0.5.1` 의 `addons/autopilot-mode/skill/adapters/` 에 들어 있는 실패·상태 코드입니다. 위 표에 없는 것은 기록에서 한 번도 나오지 않았습니다.

`acceptance-criterion-evidence-invalidated` `application-incompatible` `approval-projection-invalid` `assessment-invalid` `assessment-required` `authority-mismatch` `authority-missing` `authority-unavailable` `autopilot-off` `capture-ambiguous` `capture-authority-mismatch` `capture-owner-mismatch` `claim-evidence-invalid` `completion-body-invalid` `contract-invalid` `core-assessment-incompatible` `core-publication-blocked` `core-route-api-unavailable` `core-route-incompatible` `correction-invalid` `correction-stale` `criterion-ambiguous` `criterion-mismatch` `criterion-unbound` `dependency-invalid` `dependency-mismatch` `dependency-mutated` `derived-target-unwritable` `evidence-ambiguous` `evidence-unbound` `input-stale` `met-evidence-incompatible` `missing-decision` `no-current-execution` `no-current-unmet-criteria` `origin-receipt-incompatible` `origin-receipt-missing` `origin-stale` `origin-unbound` `owner-invalid` `owner-mismatch` `pending-adapter` `proof-invalid` `provider-capability-missing` `publication-conflict` `publication-coverage-invalid` `publication-incompatible` `publication-superseded` `publication-tampered` `receipt-coverage-invalid` `receipt-derived` `receipt-incompatible` `receipt-invalid` `receipt-missing` `receipt-owner-mismatch` `receipt-stale` `recording-error` `recording-unavailable` `recovery-diagnostic` `recovery-incompatible` `recovery-partial` `request-unbound` `response-no-publication` `retained-dependency-unavailable` `retained-proof-unavailable` `retained-proof-unsupported` `run-owner-mismatch` `target-invalid` `target-mismatch` `target-stale` `task-applied` `task-dispatched` `task-proof-invalidated` `time-invalid` `time-order-ambiguous` `unbound-legacy-approval` `unbound-work-unit` `unit-incompatible` `unmigrated-legacy-diagnostic`

## 5. 고칠 때 먼저 볼 것

- 사용자가 실제로 가장 많이 본 메시지는 `route-unavailable` 입니다(이 PC 455번, 80%). 이것부터 쉽게 바꾸면 효과가 가장 큽니다.
- 그다음은 `criterion-unbound`(70번), `response-assessment-required`(27번), 완료 표시 형식 오류(12번)입니다.
- 끝에 붙는 `repair-target`, `delivery-route` 두 줄은 Claude에게 주는 지시라 사용자에게는 뜻이 없습니다. 사용자 화면에서 숨기거나 한국어 안내로 바꿀 후보입니다.

## 6. 확인하지 못한 것

- 사유 코드의 "언제 나오나"는 코드와 영어 설명을 읽고 정리한 것입니다. 실제로 나오지 않은 코드는 그 상황을 재현해 보지 않았습니다.
- 이 PC 실제 설치본의 기록은 Core `c6019ac` 에서 나온 것이라, A(`450e4b3`)에서 읽기만 한 답을 막지 않게 바뀐 뒤의 횟수와 다릅니다.
- 설치 점검(`doctor`)·업데이트 충돌(merge-companion) 메시지는 문구를 다 뽑지 않았습니다.
- Autopilot 코드는 이름만 모았고, 코드마다 쉬운 설명은 실제로 나온 9개에만 붙였습니다.

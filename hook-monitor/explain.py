"""Plain-Korean explanations for Ghost-ALICE hook, ledger and CLI records.

This module owns the meaning of each record so the local monitor and the Langfuse sync say the same thing.
Every function is pure: it takes one source record and returns one explained item (a dict, see `_item`).

The wording follows Ghost-ALICE Core and Autopilot 0.5.1:
- Stop gate issues: ghost-alice/_shared/native_completion.py (`assess_native_completion`)
- block once per turn, then notify: ghost-alice/_shared/claude_stop_verification_hook.py (`RETRIES_PER_TURN`)
- answer delivery after a block: ghost-alice/_shared/response_delivery.py
- route registration errors: ghost-alice/_shared/response_route.py
- Autopilot recording statuses: ghost-alice-autopilot/.../adapters/autopilot_intent_recovery.py
A code missing from the tables below is still shown, with its original text and `known: False`.

Dependencies: Python 3.11+ standard library only.
"""
import json
import re

MAX_RAW = 4000

# The five stages follow the order in which Claude Code fires the hooks for one user input.
STAGES = [
    {'key': 'intake', 'label': '① 입력 접수', 'hooks': 'SessionStart · UserPromptSubmit',
     'what': '입력을 받으면 원문은 저장하지 않고 지문(해시)과 글자 수만 원장에 임시 기록합니다. '
             '다음 도구 호출 직전이나 답변 종료 때 "사람이 보낸 입력"으로 확정합니다.'},
    {'key': 'route', 'label': '② 의도·경로 기록', 'hooks': '에이전트가 원장 명령으로 기록',
     'what': '에이전트가 목표·제약·완료 기준을 원장에 적고, 이번 입력에 대한 작업 경로(response-route)를 등록합니다. '
             '경계 계약이 필요하면 계약 ID를 함께 등록합니다.'},
    {'key': 'tool', 'label': '③ 도구 사용', 'hooks': 'PreToolUse · PostToolUse',
     'what': '도구를 부를 때마다 점검 안내와 Autopilot 준비가 실행되고, 끝나면 사용 내역을 감사 로그에 남깁니다. '
             '이 단계의 훅은 안내와 기록만 하며 경계 계약 내용과 도구 호출을 대조하지 않습니다.'},
    {'key': 'stop', 'label': '④ 답변 종료 점검', 'hooks': 'Stop · completion',
     'what': '답변을 끝내도 되는지 Core가 판단합니다. 답변을 막는 곳은 여기입니다. '
             '같은 턴에서는 한 번만 막고, 두 번째부터는 알림만 남기고 내보냅니다.'},
    {'key': 'record', 'label': '⑤ 완료 기록', 'hooks': 'Stop · Autopilot',
     'what': 'Autopilot이 검토를 통과한 완료 근거를 기록합니다. 기록하지 못해도 답변을 막지는 않습니다.'},
]
STAGE_LABEL = {s['key']: s['label'] for s in STAGES}

LEVELS = ('none', 'ok', 'info', 'warn', 'block', 'error')
LEVEL_LABEL = {'none': '실행 안 됨', 'ok': '정상', 'info': '참고', 'warn': '주의', 'block': '막힘', 'error': '훅 오류'}


def _cut(value, limit=MAX_RAW):
    value = '' if value is None else str(value)
    return value if len(value) <= limit else value[:limit] + ' …(잘림)'


def _item(ts, source, stage, name, level, title, *, code=None, why='', resume='', improve='', raw='', known=True, **extra):
    """One explained record. `raw` keeps the original text so the Korean wording can always be checked."""
    return {'ts': ts, 'source': source, 'stage': stage, 'name': name, 'level': level, 'code': code, 'title': title,
            'why': why, 'resume': resume, 'improve': improve, 'raw': _cut(raw), 'known': known, **extra}


# ---- Stop gate (Stop · completion) ------------------------------------------------------------

GATE_MARKER = '[completion-gate]'
_NOTICE_PREFIXES = ('Current work routing remains unresolved: ', 'Internal response review remains unresolved: ',
                    'Core has not accepted the submitted completion proof after one retry. Remaining defect: ')
_LEADING_CODE = re.compile(r'([a-z]+(?:-[a-z0-9]+)+): ')
_REVIEW_PROCEDURE = ('절차는 verification-before-completion/references/autopilot-publication.md의 '
                     '"Prepare and record the response review" 절에 있습니다.')

GATE = {
    'route-unavailable': {
        'title': '작업 경로가 등록되지 않았습니다',
        'why': '이번 입력에서 에이전트가 도구를 썼는데, "이 입력으로 어떤 작업을 어떤 목적으로 하는지"를 원장에 등록(response-route)하지 않았습니다. '
               '경로가 없으면 Core는 이 답변이 어떤 작업과 완료 기준에 대한 것인지 연결할 수 없습니다. '
               '새 입력이 들어올 때마다 이전 경로는 만료되므로 입력마다 다시 등록해야 합니다.',
        'resume': '에이전트가 task-router 절차로 response_route.py에 경로를 등록하면 다음 종료 점검에서 통과합니다. '
                  '이미 한 작업을 다시 할 필요는 없습니다.',
        'improve': '에이전트가 도구를 쓰기 전에 경로 등록 단계를 건너뛴 것입니다. 이 턴의 "② 의도·경로 기록"이 비어 있는지, '
                   '등록을 시도했다가 거부(route-binding)됐는지 확인하세요. 거부됐다면 원인은 "① 입력 접수"의 확정 대기 입력입니다.',
    },
    'native-activity-unavailable': {
        'title': '이번 턴에 도구를 썼는지 확인하지 못했습니다',
        'why': 'Core가 Claude Code 대화 기록에서 이번 턴의 도구 사용 여부를 읽지 못했습니다. 도구를 쓰지 않았다는 증거로 보지 않기 때문에 막습니다.',
        'resume': '작업 경로를 등록하면 통과합니다. 계속 반복되면 대화 기록 파일과 세션 연결(세션 ID)을 확인하세요.',
        'improve': '데스크톱 앱에서 대화 도중 세션 ID가 바뀌면 생길 수 있습니다. 같은 턴의 "① 입력 접수" 기록과 세션 ID를 대조하세요.',
    },
    'response-assessment-required': {
        'title': '답변 검토 기록이 없습니다',
        'why': '이 답변은 "설명" 목적으로 등록됐습니다. 설명 답변은 에이전트가 답변 전체를 원본 자료와 대조한 검토 기록을 Core에 남겨야 하는데, '
               '그 기록이 없거나 기록한 문장과 실제 답변이 다릅니다.',
        'resume': 'completion_assessment.py의 prepare-response로 검토 후보를 만들고 record-response로 주장별 판단과 전체 판단을 기록하면 통과합니다. '
                  + _REVIEW_PROCEDURE,
        'improve': '검토를 기록한 뒤 답변 문장을 바꾸면 본문이 달라져 다시 막힙니다. 기록한 문장 그대로 답했는지 확인하세요.',
    },
    'assessment-required': {
        'title': '완료 주장에 대한 검토 기록이 없습니다',
        'why': '답변에 완료·성공을 주장하는 블록이 있는데, 그 주장을 원본 근거와 대조한 검토 기록이 Core에 없습니다.',
        'resume': '에이전트가 completion_assessment.py로 주장별 판단과 전체 판단을 기록하면 통과합니다. ' + _REVIEW_PROCEDURE,
        'improve': '에이전트가 verification-before-completion 절차 없이 완료를 선언했는지 확인하세요.',
    },
    'assessment-unavailable': {
        'title': '검토 기록을 읽지 못했습니다',
        'why': 'Core가 이 답변의 검토 기록을 찾거나 읽는 중에 실패했습니다.',
        'resume': '원문 메시지를 확인하고, 검토 기록을 다시 남깁니다. ' + _REVIEW_PROCEDURE,
        'improve': '원장 DB 접근 오류인지, 검토를 아예 기록하지 않은 것인지 원문으로 구분하세요.',
    },
    'assessment-unsupported': {
        'title': '검토 결과 일부 주장이 근거로 뒷받침되지 않습니다',
        'why': '에이전트가 스스로 기록한 검토에서 "지원됨"이 아닌 주장이 있습니다. Core는 모든 주장이 지원될 때만 완료 제출을 받습니다.',
        'resume': '뒷받침되지 않는 주장을 고치거나 빼고, 바뀐 답변으로 검토를 다시 기록합니다.',
        'improve': '근거 없이 완료를 주장한 사례입니다. 어떤 주장이 지원되지 않았는지 대화에서 확인하세요.',
    },
    'claim-evidence-unbound': {
        'title': '근거와 연결되지 않은 문장이 있습니다',
        'why': '완료 주장 블록 밖의 설명 문장이 기록된 근거 범위에 들어 있지 않습니다.',
        'resume': '답변 전체(블록 밖 문장 포함)를 원본 자료와 대조해 검토를 기록합니다. 작업을 다시 실행할 필요는 없습니다. ' + _REVIEW_PROCEDURE,
        'improve': '완료 블록에 없는 내용을 본문에서 추가로 주장했는지 확인하세요.',
    },
    'source-changed': {
        'title': '검토에 쓴 원본 자료가 그 뒤에 바뀌었습니다',
        'why': '검토를 기록할 때 근거로 삼은 파일이나 출력이 이후에 수정됐습니다. 바뀐 자료로는 이전 검토를 인정하지 않습니다.',
        'resume': '바뀐 자료를 다시 확인하고 그 자료에 대한 검토만 새로 기록합니다.',
        'improve': '검토를 기록한 뒤 같은 파일을 또 고쳤는지 확인하세요. 수정을 끝낸 뒤 검토하는 순서가 맞습니다.',
    },
    'source-unavailable': {
        'title': '검토에 쓴 원본 자료를 찾을 수 없습니다',
        'why': '검토에서 근거로 지정한 파일이나 출력이 지금은 없습니다.',
        'resume': '자료의 올바른 위치로 검토를 다시 기록하거나, 사라진 자료에 기대는 주장을 뺍니다.',
        'improve': '임시 폴더의 파일을 근거로 지정했는지 확인하세요.',
    },
}
_DELIVERY = {
    'preserve_answer_and_patch_metadata': '앞서 한 답변은 그대로 두고 빠진 기록만 보완하면 됩니다.',
    'corrected_complete_answer': '바뀐 주장을 반영한 전체 답변을 다시 내야 합니다.',
    'assembled_complete_payload': '앞선 답변과 보완 내용을 합쳐 한 번에 다시 답해야 합니다.',
    'resolve_host_delivery': '앞선 답변이 화면에 보였으면 보완만 하고, 보이지 않았으면 답변을 한 번 더 포함합니다.',
}
_REPAIR_TARGET = {
    'response_route': '작업 경로 등록', 'response_review': '답변 검토 기록', 'completion_metadata': '완료 보고 블록',
    'source_status': '원본 자료 상태', 'runtime_records': '실행 기록',
}


def issue_code(text):
    """Return the issue code that starts a Core issue string, or None when the issue is a plain sentence."""
    text = str(text or '').strip()
    if text.startswith(GATE_MARKER):
        text = text[len(GATE_MARKER):].lstrip()
    for prefix in _NOTICE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    match = _LEADING_CODE.match(text)
    return match.group(1) if match else None


def _gate(base, text, blocking):
    code = issue_code(text)
    entry = GATE.get(code)
    target = re.search(r'repair-target: (\S+)', text)
    delivery = re.search(r'delivery-route: (\S+)', text)
    extra = {'repair_target': target.group(1) if target else None, 'delivery_route': delivery.group(1) if delivery else None}
    if entry is None:
        label = f'해설이 아직 없는 코드: {code}' if code else '완료 보고의 형식이나 근거에 문제가 있습니다'
        entry = {'title': label,
                 'why': '이 사유는 해설 목록에 없습니다. 아래 원문이 Core가 에이전트에게 준 설명입니다.',
                 'resume': '원문이 요구하는 항목을 보완하면 다음 종료 점검에서 다시 판단합니다.',
                 'improve': '반복해서 나오면 hook-monitor/explain.py의 GATE 표에 이 코드의 해설을 추가하세요.'}
    resume = entry['resume']
    if delivery and delivery.group(1) in _DELIVERY:
        resume += ' ' + _DELIVERY[delivery.group(1)]
    if blocking:
        title, why, level = '답변 종료를 막았습니다: ' + entry['title'], entry['why'], 'block'
    else:
        title, level = '알림만 남기고 답변을 내보냈습니다: ' + entry['title'], 'warn'
        why = entry['why'] + ' 이 턴에서 이미 한 번 막았기 때문에 이번에는 막지 않았습니다(턴당 1회). 문제는 풀리지 않은 채 남아 있습니다.'
    return _item(**base, level=level, title=title, code=code, why=why, resume=resume, improve=entry['improve'],
                 raw=text, known=code in GATE, **extra)


# ---- Autopilot recording statuses -------------------------------------------------------------

_IDENTITY = {'title': 'Autopilot이 세션 식별 정보를 확인하지 못했습니다',
             'why': 'Autopilot이 받은 플랫폼·세션 ID·원장 위치가 원장의 기록과 맞지 않거나 빠져 있습니다.',
             'resume': '훅 설치 설정(~/.claude/settings.json)의 원장 위치와 실제 원장 폴더가 같은지 확인합니다.',
             'improve': '작업 폴더를 바꿔 열었거나 대화 도중 세션 ID가 바뀐 경우에 나타납니다.'}
_COMPAT = {'title': 'Core와 Autopilot이 서로의 기록을 읽지 못했습니다',
           'why': 'Autopilot이 Core의 경로·평가 기능을 불러오거나 기록하는 데 실패했습니다.',
           'resume': '원문의 오류 내용을 확인합니다. 설치된 Core와 Autopilot 버전이 서로 맞는지 점검합니다.',
           'improve': 'Core 0.5.1과 Autopilot 0.5.1 조합에서만 확인된 설치입니다. 버전을 올렸다면 호환성을 먼저 확인하세요.'}
RECORDING = {
    'prepared': {'level': 'ok', 'title': 'Autopilot이 완료 기록을 준비했습니다'},
    'current-admitted-execution': {'level': 'ok', 'title': 'Autopilot이 현재 실행 작업을 기록 대상으로 골랐습니다'},
    'v2-unit-state': {'level': 'ok', 'title': 'Autopilot이 작업 단위별 완료 상태를 확인했습니다'},
    'response-no-publication': {'level': 'ok', 'title': '이번 답변은 완료 제출이 아니어서 기록할 것이 없습니다'},
    'no-current-execution': {'level': 'ok', 'title': '선택된 실행 작업이 없어 기록할 것이 없습니다'},
    'no-current-unmet-criteria': {'level': 'ok', 'title': '남은 미충족 완료 기준이 없어 기록할 것이 없습니다'},
    'awaiting-current-route': {
        'level': 'info', 'title': 'Autopilot이 작업 경로 등록을 기다리고 있습니다',
        'why': '아직 이번 입력의 작업 경로가 없어서 Autopilot이 완료 기록 준비를 미뤘습니다. 도구 호출은 막지 않습니다.',
        'resume': '경로가 등록되면 다음 도구 호출부터 자동으로 준비됩니다.',
        'improve': '이 상태로 턴이 끝나면 "④ 답변 종료 점검"에서 route-unavailable로 막힙니다. 경로 등록이 도구 사용보다 늦은 순서 문제입니다.'},
    'autopilot-off': {'level': 'info', 'title': 'Autopilot이 일시 정지 상태입니다',
                      'why': '이 세션의 Autopilot 실행이 멈춰 있어 완료 기록과 자동 진행을 하지 않습니다.',
                      'resume': '사용자가 Autopilot을 다시 켜면 기록이 재개됩니다.', 'improve': ''},
    'core-assessment-incompatible': {
        'level': 'warn', 'title': '현재 입력이 원장에서 확정되지 않아 Autopilot이 기록하지 못했습니다',
        'why': 'Autopilot은 Core의 평가가 "원장의 최신 입력"과 일치할 때만 사용합니다. Core는 확정 대기 중인 입력이 하나라도 남아 있으면 '
               '현재 입력을 확정되지 않은 것으로 취급하므로(session_intent_ledger.py의 _canonical_input_bound) 둘이 어긋납니다. '
               '같은 이유로 작업 경로 등록과 답변 검토 기록도 거부됩니다.',
        'resume': '"① 입력 접수"에서 대기 중인 입력이 확정(native-input-resolved)돼야 풀립니다. 대기열이 계속 남는 세션은 그대로는 풀리지 않으며, '
                  '새 채팅은 빈 대기열로 시작합니다.',
        'improve': '어떤 입력 뒤부터 대기열이 쌓였는지는 그 턴의 안내 문장에 입력 종류와 함께 표시됩니다. 지금까지 확인된 종류는 '
                   '서브에이전트 완료 보고 같은 다른 에이전트의 메시지, 슬래시 명령, 작업 도중 보낸 메시지, 데스크톱 앱 알림입니다.'},
    'completion-body-invalid': {
        'level': 'warn', 'title': 'Core가 답변에서 문제를 찾아 Autopilot이 완료를 기록하지 않았습니다',
        'why': '종료 점검에서 Core가 지적한 문제가 풀리지 않은 답변이라 완료 근거로 기록하지 않았습니다.',
        'resume': '아래 원인 코드의 문제를 풀고 다시 답하면 기록됩니다.',
        'improve': '같은 턴의 "④ 답변 종료 점검" 해설이 근본 원인입니다.'},
    'claim-evidence-invalid': {
        'level': 'warn', 'title': '완료 주장의 근거 표기에 문제가 있어 Autopilot이 기록하지 않았습니다',
        'why': '답변의 완료 주장 블록이 근거와 올바르게 연결되지 않았습니다.',
        'resume': '원문이 가리키는 주장과 근거의 연결을 고쳐 다시 답합니다.',
        'improve': '완료 블록의 criterion·claim·evidence 항목이 실제 근거와 맞는지 확인하세요.'},
    'route-missing': {
        'level': 'warn', 'title': '작업 경로가 없어 Autopilot이 완료를 기록하지 못했습니다',
        'why': '완료를 제출했지만 이번 입력의 작업 경로가 등록돼 있지 않습니다.',
        'resume': '작업 경로를 등록한 뒤 다시 제출합니다.', 'improve': '"② 의도·경로 기록" 단계가 빠졌는지 확인하세요.'},
    'route-stale': {
        'level': 'warn', 'title': '작업 경로가 만료돼 Autopilot이 완료를 기록하지 못했습니다',
        'why': '경로를 등록한 뒤 새 입력이 들어와 그 경로가 만료됐습니다.',
        'resume': '현재 입력으로 작업 경로를 다시 등록합니다.', 'improve': '새 입력마다 경로를 다시 등록하는지 확인하세요.'},
    'core-publication-blocked': {
        'level': 'warn', 'title': 'Core가 이 답변의 완료 기록을 허용하지 않았습니다',
        'why': 'Core의 판단 결과가 "기록 준비"가 아니어서 Autopilot이 기록을 진행하지 않았습니다.',
        'resume': '원문의 판단 사유를 확인합니다.', 'improve': ''},
    'v1-multiple-work-units': {
        'level': 'warn', 'title': '실행 작업을 둘 이상 선택해 기록하지 못했습니다',
        'why': '이 기록 방식은 한 번에 실행 작업 하나만 받습니다.',
        'resume': '작업 경로에서 실행 작업을 하나만 선택해 다시 등록합니다.', 'improve': ''},
    'derived-target-unwritable': {
        'level': 'warn', 'title': 'Autopilot 기록 폴더에 쓸 수 없습니다',
        'why': 'Autopilot이 세션별 기록 폴더(~/.ghost-alice/autopilot/sessions/…)에 쓰지 못했습니다.',
        'resume': '폴더 권한과 디스크 상태를 확인합니다.', 'improve': ''},
    'capture-failure': {
        'level': 'warn', 'title': 'Autopilot이 도구 호출의 출처를 기록하지 못했습니다',
        'why': '출처 기록 중 오류가 났습니다. 도구 호출 자체는 막지 않습니다.',
        'resume': '원문의 오류 내용을 확인합니다.', 'improve': ''},
    'unbound-work-unit': {
        'level': 'warn', 'title': '기록할 작업 단위가 원장과 연결돼 있지 않습니다',
        'why': 'Autopilot이 받은 작업 단위가 현재 작업 경로의 것과 다릅니다.',
        'resume': '현재 입력으로 작업 경로를 다시 등록합니다.', 'improve': ''},
    **{code: dict(_IDENTITY, level='warn') for code in ('authority-missing', 'authority-mismatch', 'authority-unavailable', 'run-owner-mismatch')},
    **{code: dict(_COMPAT, level='warn') for code in ('core-route-api-unavailable', 'core-route-incompatible', 'core-route-recording-failed')},
}


def _recording(base, record):
    status, reason = record.get('status'), record.get('reason')
    code = reason or status
    entry = RECORDING.get(code)
    known = entry is not None
    if entry is None:
        unavailable = status == 'recording-unavailable'
        entry = {'level': 'warn' if unavailable else 'ok',
                 'title': f'Autopilot 기록 상태: {status}' + (f' ({reason})' if reason else ''),
                 'why': '이 상태는 해설 목록에 없습니다. 원문을 확인하세요.' if unavailable else '',
                 'resume': '', 'improve': 'hook-monitor/explain.py의 RECORDING 표에 해설을 추가하세요.' if unavailable else ''}
    title = entry['title']
    unit = record.get('work_unit_id')
    if unit:
        title += f' (작업 단위: {unit})'
    if code == 'v2-unit-state' and isinstance(record.get('units'), list):
        title += f' ({len(record["units"])}개)'
    cause = issue_code(record.get('detail'))
    why = entry.get('why', '')
    if cause:
        cause_title = GATE.get(cause, {}).get('title')
        why += f' 원인 코드: {cause}' + (f' ({cause_title})' if cause_title else '') + '.'
    compact = {k: record[k] for k in ('status', 'reason', 'detail', 'work_unit_id', 'criterion_ids', 'error_type') if k in record}
    return _item(**base, level=entry['level'], title=title, code=code, why=why, resume=entry.get('resume', ''),
                 improve=entry.get('improve', ''), raw='' if entry['level'] == 'ok' else json.dumps(compact, ensure_ascii=False),
                 known=known, cause_code=cause)


# ---- hooks ------------------------------------------------------------------------------------

ROUTINE = {
    'session-start': ('새 채팅을 시작하며 보류 중인 스킬 병합이 있는지 점검했습니다', ''),
    'pending-merge-prompt': ('입력을 받으며 보류 중인 스킬 병합을 다시 확인했습니다', ''),
    'session-intent': ('입력을 접수하고 처리 순서 안내를 에이전트에게 전달했습니다',
                       '원문은 저장하지 않습니다. 지문(해시)과 글자 수만 원장에 임시 기록합니다.'),
    'tool-checkpoint': ('도구 호출 전 점검을 실행했습니다',
                        '이 훅은 점검 안내만 합니다(입력마다 한 번 표시). 경계 계약의 허용·금지 대상과 도구 호출을 대조하지는 않습니다.'),
    'adapter-autopilot-mode-prepare-origin': ('Autopilot이 도구 호출의 출처를 확인했습니다', ''),
    'io-trace': ('도구 사용 내역을 감사 로그에 남겼습니다', ''),
    'completion': ('답변 종료 점검을 통과했습니다', ''),
    'adapter-autopilot-mode-continue': ('Autopilot이 답변 종료 뒤 처리를 확인했습니다', ''),
}


def _hook_stage(event, hook_id):
    if event in ('SessionStart', 'UserPromptSubmit'):
        return 'intake'
    if event == 'Stop':
        return 'stop' if hook_id == 'completion' else 'record'
    return 'tool'


def _failed(exit_code):
    return str(exit_code).strip() not in ('0', '', 'None')


def explain_hook(row):
    """Explain one row of strict-hook-output.jsonl."""
    event, hook_id = str(row.get('event') or ''), str(row.get('hook_id') or '')
    base = {'ts': row.get('ts'), 'source': 'hook', 'stage': _hook_stage(event, hook_id), 'name': f'{event} · {hook_id}'}
    try:
        duration = float(row.get('observed_duration_s') or 0)
    except (TypeError, ValueError):
        duration = 0.0
    base['duration_s'] = duration
    stdout = row.get('stdout') or ''
    if _failed(row.get('exit_code')):
        return _item(**base, level='error', title=f'훅 실행이 실패했습니다 (종료 코드 {row.get("exit_code")})',
                     why='훅 프로그램이 판단을 내리기 전에 오류로 끝났습니다. 이 단계의 점검은 수행되지 않은 것으로 봐야 합니다.',
                     resume='아래 원문(오류 출력)의 첫 줄이 원인입니다. 훅 설치 상태는 Ghost-ALICE 설치 진단(install --doctor)으로 확인합니다.',
                     improve='경로 표기나 한글 인코딩 문제로 훅이 거부되는 경우가 Windows에서 확인됐습니다(Windows-ghost-alice-fixes.md).',
                     raw=(row.get('stderr') or '') + ('\n' + stdout if stdout.strip() else ''))
    try:
        out = json.loads(stdout)
    except ValueError:
        out = None
    if not isinstance(out, dict):
        out = {}
    specific = out.get('hookSpecificOutput') if isinstance(out.get('hookSpecificOutput'), dict) else {}
    decision = str(out.get('decision') or specific.get('permissionDecision') or '').lower()
    reason = str(out.get('reason') or specific.get('permissionDecisionReason') or '')
    if decision in ('block', 'deny'):
        if hook_id == 'completion':
            return _gate(base, reason, blocking=True)
        if base['stage'] == 'tool':
            return _item(**base, level='block', title='도구 호출을 거부했습니다', code=issue_code(reason),
                         why='훅이 이 도구 호출을 허용하지 않았습니다. 거부된 호출은 실행되지 않았습니다. 이유는 아래 원문에 있습니다.',
                         resume='허용 범위 안의 다른 방법을 쓰거나, 범위를 넓혀야 하면 사용자의 승인을 받아야 합니다.',
                         improve='거부 뒤에 에이전트가 같은 일을 다른 도구로 우회했는지 다음 도구 호출에서 확인하세요.', raw=reason)
        return _item(**base, level='block', title='훅이 진행을 막았습니다', code=issue_code(reason),
                     why='이 훅의 차단은 해설 목록에 없습니다. 아래 원문이 훅이 에이전트에게 준 설명입니다.',
                     resume='원문이 요구하는 조치를 하면 다시 진행됩니다.', improve='', raw=reason, known=False)
    message = str(out.get('systemMessage') or '')
    if hook_id == 'completion' and GATE_MARKER in message:
        return _gate(base, message, blocking=False)
    record = out.get('completion_recording')
    if isinstance(record, dict):
        return _recording(base, record)
    merge = out.get('ghostAlicePendingMergeCheck')
    if isinstance(merge, dict) and isinstance(merge.get('undecided_count'), int) and merge['undecided_count'] > 0:
        return _item(**base, level='warn', title=f'결정하지 않은 스킬 병합이 {merge["undecided_count"]}건 있습니다', code='pending-merge',
                     why='스킬 업데이트 때 사용자가 고친 내용과 새 버전이 달라, 어느 쪽을 쓸지 결정이 필요합니다.',
                     resume='merge-companion 절차로 병합·폐기·보류를 정합니다. 보류해도 다른 작업은 계속할 수 있습니다.',
                     improve='', raw=message)
    title, note = ROUTINE.get(hook_id, (f'{hook_id} 훅이 실행됐습니다', ''))
    if hook_id == 'tool-checkpoint' and (message or specific.get('additionalContext')):
        title = '도구 호출 전 점검 안내를 에이전트에게 표시했습니다'
    return _item(**base, level='ok', title=title, why=note, known=hook_id in ROUTINE)


# ---- ledger events ----------------------------------------------------------------------------

DELTA_KEYS = {'current_goal': '목표', 'user_intent_summary': '의도 요약', 'constraints': '제약', 'non_goals': '하지 않을 일',
              'decisions': '결정', 'open_questions': '열린 질문', 'acceptance_criteria': '완료 기준',
              'conduct_feedback': '행동 교정', 'consumer_hints': '참고 정보', 'risk_flags': '위험 표시', 'latest_scope': '작업 범위'}


def _local_changes(changes):
    """Short readable lines of what the agent wrote into the ledger. Shown locally only, never sent to Langfuse."""
    lines = []
    if not isinstance(changes, dict):
        return lines
    for key, change in changes.items():
        after = change.get('after') if isinstance(change, dict) else change
        label = DELTA_KEYS.get(key, key)
        if isinstance(after, str) and after:
            lines.append(f'{label}: {after}')
        elif isinstance(after, list):
            for entry in after[:12]:
                if isinstance(entry, dict):
                    text = entry.get('summary') or entry.get('id') or ''
                    prefix = f'{entry["id"]} · ' if entry.get('id') and entry.get('summary') else ''
                    lines.append(f'{label}: {prefix}{text}')
                elif entry:
                    lines.append(f'{label}: {entry}')
    return [_cut(line, 300) for line in lines]


def explain_ledger(event):
    """Explain one event of the intent ledger (table intent_events of ghost-state.sqlite3)."""
    kind = str(event.get('event') or '')
    base = {'ts': event.get('ts'), 'source': 'ledger', 'name': f'원장 · {kind}', 'code': kind, 'event': kind}
    if kind == 'native-input-staged':
        chars = event.get('input_char_count')
        return _item(**base, stage='intake', level='ok', title='입력을 임시 접수했습니다' + (f' ({chars}자)' if chars is not None else ''),
                     why='아직 "사람이 보낸 입력"으로 확정되기 전입니다. 확정은 다음 도구 호출 직전이나 답변 종료 때 이뤄집니다.')
    if kind == 'native-input-resolved':
        actor = event.get('actor')
        if actor == 'human':
            return _item(**base, stage='intake', level='ok', title='입력을 사람이 보낸 것으로 확정했습니다')
        return _item(**base, stage='intake', level='info', title=f'입력을 "{actor}"(으)로 판단했습니다',
                     why='사람이 보낸 입력이 아니면 기준 입력을 바꾸지 않고 이전 입력과 작업 경로를 유지합니다.')
    if kind == 'user-input-observed':
        return _item(**base, stage='intake', level='ok', title='확정된 입력을 원장의 기준 입력으로 기록했습니다',
                     why='기준 입력이 바뀌면 이전 작업 경로는 만료됩니다. 이번 입력에서 도구를 쓰려면 작업 경로를 새로 등록해야 합니다.')
    if kind == 'intent-updated':
        names = [DELTA_KEYS.get(k, k) for k in event.get('delta_keys') or []]
        return _item(**base, stage='route', level='info', title='에이전트가 의도를 원장에 기록했습니다' + (': ' + ', '.join(names) if names else ''),
                     why='에이전트가 이해한 목표와 조건입니다. 내 의도와 다르면 여기서부터 어긋난 것입니다.',
                     local_detail=_local_changes(event.get('semantic_changes')))
    if kind == 'response-route-recorded':
        units = event.get('selected_work_unit_ids') or []
        count = len(event.get('selected_criteria') or [])
        scope = f'작업 단위: {", ".join(map(str, units))} · 완료 기준 {count}개' if units else '선택한 실행 작업 없음'
        return _item(**base, stage='route', level='info', title=f'작업 경로를 등록했습니다 ({scope})',
                     why='이 시점부터 Core가 이번 입력의 답변을 이 작업과 완료 기준에 연결합니다.')
    if kind == 'acceptance-criterion-met':
        criterion = event.get('criterion_id') or event.get('id') or ''
        return _item(**base, stage='record', level='info', title=f'완료 기준 충족을 기록했습니다 {criterion}'.strip(),
                     why='검토를 통과한 근거로 이 완료 기준이 충족 상태가 됐습니다.')
    if kind == 'acceptance-criterion-evidence-invalidated':
        return _item(**base, stage='record', level='warn', title='충족으로 기록했던 완료 기준의 근거가 무효가 됐습니다',
                     why='완료 기준의 문장이 바뀌었거나 승인이 철회돼 이전 근거를 더는 인정하지 않습니다.',
                     resume='바뀐 기준에 맞춰 다시 검증하고 근거를 새로 기록합니다.', improve='')
    return _item(**base, stage='route', level='ok', title=f'원장 이벤트: {kind}', known=False)


# ---- ledger commands refused (typed CLI errors found in the conversation) -----------------------

_PENDING_HINT = ('대기 입력이 계속 남는다면 Ghost-ALICE가 그 입력을 누가 보냈는지 인식하지 못한 것입니다. '
                 '"① 입력 접수"에서 "임시 접수"만 있고 "확정"이 없는 입력을 찾으세요.')
CLI = {
    'route-binding': {
        'title': '작업 경로 등록이 거부됐습니다: 현재 입력과 묶을 수 없습니다',
        'why': '작업 경로는 원장의 "확정된 최신 입력"에만 묶을 수 있습니다. 입력이 아직 확정되지 않았거나(확정 대기 입력이 남아 있음) '
               '등록에 쓴 입력 ID가 최신이 아닙니다.',
        'resume': 'session_intent_ledger.py --read-state로 latest_input_event_id와 pending_native_inputs를 확인합니다. 대기 입력이 없으면 '
                  '최신 ID로 다시 등록합니다. 대기 입력이 남아 있으면 그 입력이 확정되기 전에는 등록할 수 없습니다.',
        'improve': _PENDING_HINT},
    'route-schema': {
        'title': '작업 경로 등록이 거부됐습니다: 등록 내용이 규칙에 맞지 않습니다',
        'why': '등록하려는 경로의 형식이나 선택한 작업·완료 기준이 Core의 규칙과 맞지 않습니다.',
        'resume': '원문 메시지가 가리키는 항목을 고쳐 다시 등록합니다.',
        'improve': '에이전트가 등록 형식을 반복해서 틀리면 task-router 절차를 끝까지 읽지 않은 것입니다.'},
}
_CLI_HINTS = (
    ('boundary_ref', '경계 계약이 필요하다고 표시했는데 계약 ID(--boundary-ref)를 주지 않았습니다.'),
    ('admitted owned criterion', '실행 작업을 선택했는데 그 작업에 묶인 승인된 완료 기준이 원장에 없습니다. '
                                 '먼저 완료 기준을 work_unit_id, contract_revision, admitted: true와 함께 기록해야 합니다.'),
    ('canonical SQLite intake provenance', '현재 입력이 원장에서 확정되지 않았습니다(확정 대기 입력이 남아 있음).'),
)


def explain_cli(code, message, ts):
    """Explain a typed error ({"error": code, "message": ...}) returned by a Ghost-ALICE ledger command."""
    entry = CLI.get(code)
    known = entry is not None
    if entry is None:
        entry = {'title': f'원장 명령이 거부됐습니다 ({code})', 'why': '이 오류 코드는 해설 목록에 없습니다. 원문을 확인하세요.',
                 'resume': '원문 메시지가 요구하는 조건을 맞춰 다시 실행합니다.',
                 'improve': 'hook-monitor/explain.py의 CLI 표에 해설을 추가하세요.'}
    why = entry['why']
    for needle, hint in _CLI_HINTS:
        if needle in str(message):
            why += ' ' + hint
    return _item(ts=ts, source='cli', stage='route', name=f'원장 명령 · {code}', level='block', title=entry['title'], code=code,
                 why=why, resume=entry['resume'], improve=entry['improve'], raw=message, known=known)

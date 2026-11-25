"""Native transcript boundaries shared by intake and completion consumers.

Dependencies: Python standard library. Native metadata, never message wording,
identifies the actor. Unresolved transport never becomes user authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path


def read_entries(path_value, session=None):
    if not isinstance(path_value, str) or not Path(path_value).is_absolute():
        return []
    try:
        lines = Path(path_value).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and (session is None or row.get('sessionId') == session):
            entries.append(row)
    return entries


def is_task_notification(entry):
    message = entry.get('attachment') if entry.get('type') == 'attachment' else entry
    if not isinstance(message, dict):
        return False
    origin = message.get('origin')
    native_origin = (isinstance(origin, dict) and origin.get('kind') == 'task-notification'
                     and origin.get('producer') == 'session-task')
    return native_origin and (
        (entry.get('type') == 'user' and entry.get('promptSource') == 'system'
         and entry.get('turnOrigin') == 'task_notification')
        or (entry.get('type') == 'attachment' and message.get('type') == 'queued_command'
            and message.get('commandMode') == 'task-notification'))


def is_actual_user_prompt(entry):
    if entry.get('type') != 'user' or entry.get('isMeta') or is_task_notification(entry):
        return False
    message = entry.get('message')
    if not isinstance(message, dict) or message.get('role') != 'user':
        return False
    content = message.get('content')
    items = content if isinstance(content, list) else [content]
    return bool(content) and not any(isinstance(item, dict) and item.get('type') == 'tool_result'
                                     for item in items)


# Local fix 2026-11-24. Tools that cannot change files, and shell commands made only of
# read commands or Ghost-ALICE's own record scripts. The rule is an allowlist: a command, an
# option or a shell form that is not known to be read-only counts as work.
_READ_ONLY_TOOLS = {'Read', 'Glob', 'Grep', 'LS', 'NotebookRead', 'Skill', 'ToolSearch'}
_RECORD_SCRIPTS = ('session_intent_ledger.py', 'response_route.py', 'completion_assessment.py')
_READ_COMMANDS = {'cat', 'head', 'tail', 'ls', 'dir', 'grep', 'rg', 'wc', 'pwd', 'cd', 'echo', 'printf', 'type', 'sort', 'uniq',
                  'cut', 'nl', 'file', 'stat', 'test', 'true', 'od', 'tr', 'basename', 'dirname', 'get-content', 'gc', 'get-childitem', 'gci',
                  'select-string', 'sls', 'select-object', 'measure-object', 'test-path', 'get-item', 'write-output'}
_READ_GIT = {'rev-parse', 'status', 'log', 'diff', 'show', 'ls-files'}
# Options that make an otherwise read-only command write a file or run another program.
_WRITING_OPTIONS = {
    'sort': ('-o', '--output', '--compress-program'),
    'find': ('-delete', '-exec', '-execdir', '-ok', '-okdir', '-fprint', '-fprint0', '-fprintf', '-fls'),
    'git': ('--output', '--ext-diff', '--textconv'),
    'rg': ('--pre', '--hostname-bin'),
    'file': ('-C', '--compile'),
}
_SED_PRINT = re.compile(r'(\d+|\$)(,(\d+|\$))?p')
_PYTHON = re.compile(r'(^|[\\/])(python3?|py)(\.exe)?$|^\$\{?py(thon)?\}?$', re.I)
_LITERAL = re.compile(r'Q\d+|S|-?\d+(\.\d+)?')
_ASSIGNMENT = re.compile(r'\$?[A-Za-z_][A-Za-z0-9_:]*=\S*')
# PowerShell. Cmdlets that only read or shape what they are given, the .NET members that only
# read, and the words an expression is made of. A script block or a parenthesised part is
# judged as commands of its own, so `ForEach-Object { Remove-Item $_ }` is still work.
_PS_READ_COMMANDS = {'where-object', 'where', '?', 'foreach-object', '%', 'resolve-path', 'sort-object', 'group-object',
                     'select', 'measure', 'format-table', 'ft', 'format-list', 'fl', 'out-string', 'out-null', 'out-host',
                     'write-host', 'join-path', 'split-path', 'get-location', 'gl', 'get-filehash', 'get-date',
                     'convertfrom-json', 'convertto-json', 'convertfrom-csv', 'convertto-csv', 'import-csv',
                     'compare-object', 'get-unique', 'get-itemproperty', 'get-member'}
_PS_KEYWORDS = {'if', 'elseif', 'else', 'while', 'foreach', 'return', 'try', 'finally'}
_PS_STATIC = re.compile(
    r'\[(?:system\.)?(?:io\.file\]::(?:readall(?:bytes|text|lines)|readlines|exists)'
    r'|io\.directory\]::(?:getfiles|getdirectories|enumeratefiles|exists)'
    r'|io\.path\]::(?:getfilename|getfilenamewithoutextension|getextension|getdirectoryname|getfullpath|combine|join)'
    r'|text\.encoding\]::\w+|(?:string|math|convert|regex|char|int|datetime)\]::\w+)', re.I)
_PS_PURE_METHODS = {'split', 'trim', 'trimend', 'trimstart', 'substring', 'tostring', 'toupper', 'tolower', 'contains',
                    'startswith', 'endswith', 'indexof', 'lastindexof', 'padleft', 'padright', 'gettype', 'getstring',
                    'getbytes', 'count'}
_PS_ASSIGN = {'=', '+=', '-=', '*=', '/='}
_PS_OPERATOR = re.compile(r'-(?:[ci]?(?:eq|ne|gt|ge|lt|le|like|notlike|match|notmatch|replace|split|join|contains'
                          r'|notcontains|in|notin)|and|or|not|xor|is|isnot|as|f|band|bor)|[+\-*/%,]|\.\.', re.I)
_PS_TOKEN = re.compile(r'[@!,]*(?:\[[\w.]+(?:\[\])?\])*(?:S|Q\d+|\$[\w:]+|-?\d+(?:\.\d+)?(?:kb|mb|gb)?)?'
                       r'(?:\[[-\w$.:,]*\])*(?:\.\w+(?:\[[-\w$.:,]*\])*)*,?', re.I)


def _read_only_call(call):
    name, data = call.get('name'), call.get('input')
    if name in _READ_ONLY_TOOLS:
        return True
    if name not in {'Bash', 'PowerShell'} or not isinstance(data, dict) or not isinstance(data.get('command'), str):
        return False
    return _read_only_command(data['command'], name == 'PowerShell')


def _read_only_command(command, powershell=False):
    # A command substitution is a command of its own: each innermost $( … ) is judged by the
    # same rules, then stands in the outer command as a plain word.
    for _ in range(20):
        inner = re.search(r'\$\(([^()]*)\)', command)
        if inner is None:
            break
        if not _read_only_command(inner.group(1), powershell):
            return False
        command = command[:inner.start()] + 'S' + command[inner.end():]
    # Quoted text is data (a grep pattern, a label). It is set aside while the commands are
    # read and looked up again where a command treats it as a script (sed, awk).
    quoted = []

    def keep(match):
        quoted.append(match.group(0)[1:-1])
        return f' Q{len(quoted) - 1} '

    # A backtick inside PowerShell double quotes is an escape ("`n"); in sh it runs a command.
    plain = re.sub(r'"(?:[^"`]|`.)*"|\'[^\']*\'' if powershell else r'"[^"`]*"|\'[^\']*\'', keep, command, flags=re.S)
    # Discarding or merging streams is not a write.
    plain = re.sub(r'\d?>\s*(/dev/null|\$null|&\d)', ' ', plain)
    if powershell:
        plain = _PS_STATIC.sub('S', plain)
    # Backticks, unresolved or process substitution and method calls can run anything.
    if '`' in plain or '$(' in plain or '<(' in plain or '>(' in plain:
        return False
    methods = re.findall(r'\.\s*([A-Za-z_]\w*)\s*\(', plain)
    if methods and not (powershell and all(method.lower() in _PS_PURE_METHODS for method in methods)):
        return False
    if powershell:
        # The call operator runs whatever its operand names.
        if re.search(r'(?<!&)&(?!&)', plain):
            return False
        plain = re.sub(r'(\$[\w:]+)\s*([+\-*/]?=)', r'\1 \2 ', plain)
        # A script block or a parenthesised part holds commands of its own.
        plain = re.sub(r'[{}()]', ';', plain)

    def text(word):
        match = re.fullmatch(r'Q(\d+)', word)
        return quoted[int(match.group(1))] if match else word

    for segment in re.split(r'&&|\|\||[;|&\n]', plain):
        words = segment.replace('(', ' ').replace(')', ' ').split()
        while words and words[0] in {'do', 'then', 'else'}:
            words = words[1:]
        if not words or words[0] in {'for', 'done', 'fi'}:
            continue
        if powershell:
            while words and words[0].lower() in _PS_KEYWORDS:
                words = words[1:]
            if words[:1] and words[0].startswith('$') and words[1:2] and words[1].lower() == 'in':
                words = words[2:]                     # foreach ($item in <command>)
            if not words:
                continue
            if words[1:2] and words[1] in _PS_ASSIGN:
                if not re.fullmatch(r'\$[\w:]+', words[0]):
                    return False                      # setting a property or an element changes its owner
                words[1] = '='
        # A leading assignment only sets a variable; the command after it is still judged.
        if words[0].startswith('$') and words[1:2] == ['=']:
            words = words[2:]
        else:
            while words and _ASSIGNMENT.fullmatch(words[0]):
                words = words[1:]
        if not words or (len(words) == 1 and _LITERAL.fullmatch(words[0])):
            continue
        if powershell:
            if any(word in _PS_ASSIGN for word in words):
                return False
            # An expression reads values; every word in it has to be a value or an operator.
            if _PS_TOKEN.fullmatch(words[0]) or _PS_OPERATOR.fullmatch(words[0]):
                if all(_PS_TOKEN.fullmatch(word) or _PS_OPERATOR.fullmatch(word) for word in words):
                    continue
                return False
        head = text(words[0])
        # Ghost-ALICE's own record scripts keep the ledger; they are not the user's work.
        if _PYTHON.search(head) and any(text(word).replace('\\', '/').split('/')[-1] in _RECORD_SCRIPTS for word in words[1:]):
            continue
        # Output redirection to a file is a write.
        if '>' in segment:
            return False
        head = head.lower()
        arguments = [word for word in words[1:] if not word.startswith('-')]
        if '::' in segment:
            return False
        if powershell and head in {'foreach-object', '%'} and any(
                word.lower() not in {'-begin', '-process', '-end'} for word in words[1:]):
            return False                              # ForEach-Object <member> calls that member
        if any(word.split('=')[0] == option or (len(option) == 2 and word.startswith(option) and not word.startswith('--'))
               for option in _WRITING_OPTIONS.get(head, ()) for word in words[1:]):
            return False
        if head == 'awk':
            # An awk program can write files and run commands; only a program that does neither is read-only.
            if any(re.search(r'>|\||system|getline|close\s*\(', text(word)) for word in words[1:]):
                return False
        elif head == 'sed':
            # Only printing a line range is read-only: sed -n 3p, sed -n '1,5p'.
            options = [word for word in words[1:] if word.startswith('-')]
            if options != ['-n'] or not arguments or not _SED_PRINT.fullmatch(text(arguments[0])):
                return False
        elif head == 'uniq':
            if len(arguments) > 1:                    # uniq INPUT OUTPUT writes OUTPUT
                return False
        elif head == 'git':
            if words[1:2] == [] or words[1] not in _READ_GIT:
                return False
        elif head not in _READ_COMMANDS and head != 'find' and not (powershell and head in _PS_READ_COMMANDS):
            return False
    return True


def native_tool_activity(platform, session_id, native_input, *, input_observation=None):
    """Observe calls after the current human input; unavailable evidence is not absence.

    This establishes native activity only. It neither judges the response's
    meaning nor substitutes for the current Core route or authenticated review.
    """
    def result(status, reason):
        return dict(status=status, reason=reason)

    data = native_input if isinstance(native_input, dict) else {}
    if (platform not in {'claude', 'codex'} or not isinstance(session_id, str) or not session_id
            or (data.get('session_id') or data.get('sessionId')) != session_id):
        return result('unavailable', 'native-owner-mismatch')
    path = data.get('transcript_path') or data.get('transcriptPath')
    if not isinstance(path, str) or not Path(path).is_absolute():
        return result('unavailable', 'native-transcript-path-missing')
    try:
        rows = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    except (OSError, ValueError, UnicodeError):
        return result('unavailable', 'native-transcript-unreadable')
    if not rows or any(not isinstance(row, dict) for row in rows):
        return result('unavailable', 'native-transcript-invalid')
    if platform == 'codex':
        owners = [row.get('payload', {}).get('id') for row in rows
                  if row.get('type') == 'session_meta' and isinstance(row.get('payload'), dict)]
        if not owners or any(owner != session_id for owner in owners):
            return result('unavailable', 'native-transcript-owner-mismatch')
        turn_id = data.get('turn_id')
        contexts = [row['payload'].get('turn_id') for row in rows
                    if row.get('type') == 'turn_context' and isinstance(row.get('payload'), dict)]
        if not isinstance(turn_id, str) or not turn_id or not contexts or contexts[-1] != turn_id:
            return result('unavailable', 'native-turn-unavailable')
        # A host turn can contain several human inputs. Native actor metadata
        # locates the latest human message; the ledger observation binds its
        # content to this input independently of tool or hook message wording.
        human = None
        for index, row in enumerate(rows):
            payload = row.get('payload')
            if (row.get('type') != 'response_item' or not isinstance(payload, dict)
                    or payload.get('type') != 'message' or payload.get('role') != 'user'):
                continue
            metadata = payload.get('internal_chat_message_metadata_passthrough')
            if (isinstance(metadata, dict) and metadata.get('turn_id') == turn_id
                    and isinstance(metadata.get('content_item_kinds'), list)
                    and 'user.text' in metadata['content_item_kinds']):
                human = (index, payload)
        if human is None:
            return result('unavailable', 'native-user-boundary-unavailable')
        content = human[1].get('content')
        texts = [part.get('text') for part in content
                 if isinstance(part, dict) and part.get('type') == 'input_text'] if isinstance(content, list) else []
        if not texts or any(not isinstance(text, str) for text in texts):
            return result('unavailable', 'native-user-text-unavailable')
        text = ''.join(texts)
        if (not isinstance(input_observation, dict)
                or input_observation.get('input_char_count') != len(text)
                or input_observation.get('input_digest') != 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()):
            return result('unavailable', 'native-input-observation-mismatch')
        active_turn = turn_id
        for row in rows[human[0] + 1:]:
            payload = row.get('payload')
            if not isinstance(payload, dict):
                continue
            if row.get('type') == 'turn_context':
                active_turn = payload.get('turn_id')
            if (row.get('type') != 'response_item'
                    or payload.get('type') not in {'custom_tool_call', 'function_call'}):
                continue
            metadata = payload.get('internal_chat_message_metadata_passthrough')
            event_turn = metadata.get('turn_id') if isinstance(metadata, dict) else None
            if event_turn == turn_id:
                return result('observed', 'current-input-tool-call')
            if active_turn == turn_id and event_turn is None:
                return result('unavailable', 'native-tool-turn-unavailable')
        return result('absent', 'current-input-has-no-tool-call')
    owned = [row for row in rows if row.get('sessionId') == session_id and not row.get('isSidechain')]
    for index in range(len(owned) - 1, -1, -1):
        if is_actual_user_prompt(owned[index]):
            calls = []
            for row in owned[index + 1:]:
                message = row.get('message')
                if (row.get('type') != 'assistant' or not isinstance(message, dict)
                        or message.get('role') != 'assistant'):
                    continue
                content = message.get('content')
                calls += [item for item in content if isinstance(item, dict)
                          and item.get('type') == 'tool_use'] if isinstance(content, list) else []
            if calls:
                # Local fix 2026-11-24: an input that only read files (or kept Ghost-ALICE's own
                # records) is reported separately so completion does not demand a route for it.
                observed = result('observed', 'current-turn-tool-call')
                observed['read_only'] = all(_read_only_call(call) for call in calls)
                return observed
            return result('absent', 'current-turn-has-no-tool-call')
    return result('unavailable', 'native-user-boundary-unavailable')


def capture_append_boundary(path_value):
    """Capture an immutable prefix, not a timing guess about the pending row."""
    if not isinstance(path_value, str) or not Path(path_value).is_absolute():
        return None
    path = Path(path_value).resolve()
    try:
        with path.open('rb') as stream:
            identity = os.fstat(stream.fileno())
            content = stream.read()
    except FileNotFoundError:
        return dict(path=str(path), device=None, inode=None, offset=0,
                    prefix_digest=hashlib.sha256(b'').hexdigest())
    except OSError:
        return None
    # An incomplete final line was not committed; inspect it after its newline arrives.
    offset = content.rfind(b'\n') + 1
    return dict(path=str(path), device=identity.st_dev, inode=identity.st_ino, offset=offset,
                prefix_digest=hashlib.sha256(content[:offset]).hexdigest())


def native_input_actor(entry):
    """Require positive host origin; message wording supplies no actor evidence."""
    if entry.get('isMeta') or entry.get('isSidechain'):
        return None
    if is_task_notification(entry):
        return 'notification'
    origin = entry.get('origin')
    if (is_actual_user_prompt(entry) and isinstance(origin, dict) and origin.get('kind') == 'human'
            and entry.get('promptSource') != 'system' and entry.get('turnOrigin') in (None, 'human')):
        return 'human'
    if is_queued_human_prompt(entry):
        return 'human'
    return None


def is_queued_human_prompt(entry):
    """A mid-turn human message is a queued_command attachment carrying its own human origin."""
    attachment = entry.get('attachment') if entry.get('type') == 'attachment' else None
    if not isinstance(attachment, dict):
        return False
    origin = attachment.get('origin')
    return (attachment.get('type') == 'queued_command' and attachment.get('commandMode') == 'prompt'
            and isinstance(origin, dict) and origin.get('kind') == 'human' and attachment.get('humanTurn') is True)


def _input_text(entry):
    if entry.get('type') == 'attachment':
        attachment = entry.get('attachment')
        return attachment.get('prompt') if isinstance(attachment, dict) else None
    message = entry.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    if isinstance(content, list):
        texts = [item.get('text') for item in content if isinstance(item, dict) and item.get('type') == 'text']
        # Claude Code joins text blocks with '\n' in the UserPromptSubmit prompt the digest was taken from.
        return '\n'.join(texts) if texts and all(isinstance(text, str) for text in texts) else None
    return content if isinstance(content, str) else None


def resolve_staged_input(observation, session_id, cursors):
    """Return one native actor/row locator, or leave the transport unresolved.

    A digest correlates content within an authenticated append window; it does
    not classify content. Exact native origin supplies the actor independently.
    """
    boundary = observation.get('transcript_boundary')
    if not isinstance(boundary, dict):
        return None
    try:
        with Path(boundary['path']).open('rb') as stream:
            identity = os.fstat(stream.fileno())
            if boundary['inode'] is not None and (identity.st_dev, identity.st_ino) != (boundary['device'], boundary['inode']):
                return None
            prefix = stream.read(boundary['offset'])
            if len(prefix) != boundary['offset'] or hashlib.sha256(prefix).hexdigest() != boundary['prefix_digest']:
                return None
            cursor_key = hashlib.sha256(json.dumps([boundary['path'], identity.st_dev, identity.st_ino]).encode()).hexdigest()
            start = max(boundary['offset'], cursors.get(cursor_key, 0))
            if start > identity.st_size:
                return None
            stream.seek(start)
            content = stream.read()
    except (OSError, KeyError, TypeError, ValueError):
        return None
    matches = []
    offset = start
    for line in content.splitlines(keepends=True):
        row_start = offset
        offset += len(line)
        if not line.endswith(b'\n'):
            break
        try:
            entry = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if (not isinstance(entry, dict) or entry.get('sessionId') != session_id
                or entry.get('isMeta') or entry.get('isSidechain')):
            continue
        if entry.get('type') not in ('user', 'attachment'):
            continue
        # promptId belongs to a native prompt grain and may repeat. It is only
        # an additional correlation constraint, never observation identity.
        native_id = entry.get('promptId')
        if native_id is not None and native_id != observation.get('native_prompt_id'):
            continue
        text = _input_text(entry)
        if text is None:
            continue
        # The transcript keeps block edge newlines; Claude Code trims the UserPromptSubmit prompt.
        if not any(len(candidate) == observation['input_char_count']
                   and 'sha256:' + hashlib.sha256(candidate.encode('utf-8')).hexdigest() == observation['input_digest']
                   for candidate in {text, text.strip(), text.rstrip()}):
            continue
        matches.append(dict(actor=native_input_actor(entry), cursor_key=cursor_key,
                            start_offset=row_start, end_offset=offset))
    return matches[0] if len(matches) == 1 and matches[0]['actor'] is not None else None

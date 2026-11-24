"""IMP v3: one-command response review that keeps both judgments.

Baseline review costs the model a skill load, a reference read, four file
writes and two Core commands. This module keeps the same Core records and the
same two judgments (each claim against its source, then the whole answer) but
moves the bookkeeping into Core:

- The Stop guard saves the exact blocked answer (``save_pending``), so the
  model does not copy the answer into a file.
- Sources are this turn's own tool calls and results, read from the native
  transcript and snapshotted by Core, so the model does not copy sources.
- Each claim names a verbatim ``evidence`` excerpt; Core checks that the
  excerpt really occurs in one of those sources and binds that source. This is
  a mechanical check the baseline review does not have.

Usage (the Stop block prints the exact command):
    python quick_review.py --root R --session S <<'JSON'
    {"claims": [{"claim": "...", "evidence": "...", "verdict": "supported", "rationale": "..."}],
     "response": {"verdict": "supported", "rationale": "..."}}
    JSON
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

VERDICTS = {'supported', 'unsupported', 'unavailable'}


class QuickReviewError(ValueError):
    pass


def _dir(root, session):
    path = Path(root) / 'quick-review' / session
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_pending(source, text, transcript_path):
    """Called by the Stop guard when it blocks for response review."""
    root, session = source.get('GHOST_ALICE_SESSION_INTENT_ROOT'), source.get('GHOST_ALICE_SESSION_ID')
    if not (isinstance(root, str) and Path(root).is_absolute() and session and transcript_path):
        return None
    path = _dir(root, session) / 'pending.json'
    path.write_text(json.dumps(dict(text=text, transcript_path=str(transcript_path)), ensure_ascii=False),
                    encoding='utf-8')
    return path


def _squash(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def _result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(item.get('text', '') for item in content if isinstance(item, dict))
    return ''


def turn_sources(transcript_path):
    """[(label, text)] for every tool call after the current human input: input + result."""
    from native_transcript import is_actual_user_prompt
    rows = [json.loads(line) for line in Path(transcript_path).read_text(encoding='utf-8').splitlines()
            if line.strip()]
    rows = [row for row in rows if isinstance(row, dict) and not row.get('isSidechain')]
    start = max((i for i, row in enumerate(rows) if is_actual_user_prompt(row)), default=-1)
    calls, results = {}, {}
    for row in rows[start + 1:]:
        for block in (row.get('message') or {}).get('content') or []:
            if not isinstance(block, dict):
                continue
            if row.get('type') == 'assistant' and block.get('type') == 'tool_use':
                calls[block['id']] = block
            elif row.get('type') == 'user' and block.get('type') == 'tool_result':
                results[block.get('tool_use_id')] = _result_text(block.get('content'))
    sources = []
    for tool_id, call in calls.items():
        # The review command itself is never evidence (no self-citation on a retry).
        if tool_id not in results or 'quick_review' in json.dumps(call.get('input'), ensure_ascii=False):
            continue
        text = (f"tool: {call.get('name')}\ninput: {json.dumps(call.get('input'), ensure_ascii=False)}\n"
                f"result:\n{results[tool_id]}\n")
        sources.append((tool_id, text))
    return sources


def _locate(claim, answer):
    """Exact claim span in the answer; whitespace differences are tolerated."""
    if claim in answer:
        return claim
    words = claim.split()
    if not words:
        return None
    match = re.search(r'\s+'.join(re.escape(w) for w in words), answer)
    return match.group(0) if match else None


def review_once(source, review):
    from completion_assessment import prepare_response_review, record_response_review
    root, session = source['GHOST_ALICE_SESSION_INTENT_ROOT'], source['GHOST_ALICE_SESSION_ID']
    if not (isinstance(review, dict) and isinstance(review.get('claims'), list) and review['claims']
            and isinstance(review.get('response'), dict)):
        raise QuickReviewError('input needs a non-empty "claims" list and a "response" judgment')
    pending_path = _dir(root, session) / 'pending.json'
    if not pending_path.is_file():
        raise QuickReviewError('no blocked answer is waiting for review in this session')
    pending = json.loads(pending_path.read_text(encoding='utf-8'))
    answer = pending['text']

    folder = _dir(root, session)
    files = []
    for tool_id, text in turn_sources(pending['transcript_path']):
        raw = text.encode('utf-8')
        path = folder / f"src-{hashlib.sha256(raw).hexdigest()[:16]}.txt"
        if not path.is_file():
            path.write_bytes(raw)
        files.append((str(path), text))

    statements, evidence_files, problems = [], [], []
    for index, item in enumerate(review['claims'], 1):
        claim, evidence = item.get('claim'), item.get('evidence') or []
        excerpts = [evidence] if isinstance(evidence, str) else evidence
        excerpts = [e for e in excerpts if isinstance(e, str) and _squash(e)]
        if item.get('verdict') not in VERDICTS or not str(item.get('rationale') or '').strip():
            problems.append(f'claim {index}: verdict must be one of {sorted(VERDICTS)} with a rationale')
            continue
        span = _locate(claim or '', answer)
        if span is None:
            problems.append(f'claim {index}: not found in the answer: {claim!r}')
            continue
        hits, missing = [], []
        for excerpt in excerpts:
            found = [path for path, text in files if _squash(excerpt) in _squash(text)]
            hits += [path for path in found if path not in hits]
            if not found:
                missing.append(excerpt)
        if item['verdict'] != 'unavailable' and (missing or not hits):
            problems.append(f'claim {index}: evidence is not a verbatim excerpt of this turn\'s tool calls or '
                            f'results: {missing or excerpts!r}')
            continue
        statements.append(span)
        evidence_files.append(hits)
    response = review['response']
    if response.get('verdict') not in VERDICTS or not str(response.get('rationale') or '').strip():
        problems.append('response: verdict and rationale are required')
    if len(set(statements)) != len(statements):
        problems.append('claims must be distinct statements')
    if problems:
        raise QuickReviewError('; '.join(problems))

    used = sorted({path for hits in evidence_files for path in hits}) or [files[0][0]] if files else []
    if not used:
        raise QuickReviewError('this turn has no tool results to review against')
    candidate = prepare_response_review(source, response_text=answer, source_paths=used,
                                        claim_statements=statements)
    ids = {s['locator']: s['source_id'] for s in candidate['sources']}
    claims = [dict(binding_id=binding['binding_id'], verdict=item['verdict'],
                   source_ids=sorted({ids[p] for p in hits}), rationale=item['rationale'])
              for binding, item, hits in zip(candidate['bindings'], review['claims'], evidence_files)]
    whole = dict(binding_id=candidate['response_binding']['binding_id'], verdict=response['verdict'],
                 source_ids=sorted(ids.values()), rationale=response['rationale'])
    result = record_response_review(source, candidate['candidate_reference'], dict(claims=claims, response=whole))
    if result.get('status') == 'reviewed':
        pending_path.unlink(missing_ok=True)
    return result


def report(result):
    """CLI output. A reviewed answer is printed verbatim so the model re-delivers the exact reviewed bytes."""
    if result.get('status') != 'reviewed' or not isinstance(result.get('response_text'), str):
        return json.dumps(dict(status=result.get('status')), ensure_ascii=False)
    from auto_route import strip_purpose_line
    return ('status: reviewed\nYour final message must be exactly the text between the markers '
            '(copy it character for character; no rewording, nothing before or after):\n'
            f'<<<ANSWER\n{strip_purpose_line(result["response_text"]).strip()}\nANSWER>>>')


def command(root, session):
    py = Path(sys.executable).as_posix()
    here = Path(__file__).resolve().as_posix()
    return f'"{py}" "{here}" --root \'{root}\' --session {session}'


def block_reason(source):
    """Self-contained repair text for the Stop block (no skill or reference needed)."""
    root, session = source['GHOST_ALICE_SESSION_INTENT_ROOT'], source['GHOST_ALICE_SESSION_ID']
    return (
        'response-review-required: before this explanation is delivered, review it against this turn\'s '
        'own tool results in ONE Bash call (no skill or reference needed; Core already holds the answer and the sources):\n'
        f"{command(root, session)} <<'JSON'\n"
        '{"claims": [{"claim": "<exact sentence from your answer>", "evidence": ["<verbatim excerpt of a tool '
        'call or result>", ...], "verdict": "supported|unsupported|unavailable", "rationale": "<why>"}],\n'
        ' "response": {"verdict": "supported|unsupported", "rationale": "<does the whole answer fulfil the request '
        'without overstating?>"}}\nJSON\n'
        'List every factual claim. Each evidence excerpt is copied character for character from one command or '
        'its output (short, no paraphrase, no "->" or added words); give several excerpts for a claim that '
        'combines outputs. If the command reports a problem, fix the JSON and run it again. '
        'On success the command prints the reviewed answer: deliver exactly that text as your final message, '
        'character for character (no rewording, nothing added). If a claim is unsupported, say so instead.'
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', required=True)
    ap.add_argument('--session', required=True)
    args = ap.parse_args()
    source = dict(os.environ, GHOST_ALICE_SESSION_INTENT_ROOT=args.root, GHOST_ALICE_PLATFORM='claude',
                  GHOST_ALICE_SESSION_ID=args.session)
    try:
        result = review_once(source, json.loads(sys.stdin.read()))
    except (QuickReviewError, ValueError, OSError) as exc:
        print(json.dumps(dict(status='rejected', reason=getattr(exc, 'reason', 'quick-review'), detail=str(exc)),
                         ensure_ascii=False))
        return 1
    print(report(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

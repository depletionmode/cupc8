"""Codex second opinion for the CPL review pack (tools/cpl_review_pack.py).

    python3 tools/cpl_codex.py list                     # the open part types and their prompts
    python3 tools/cpl_codex.py run [--jobs 4] [--only C7272 ...]   # ask Codex, once per type
    (the pack's `build` then merges build/cpl-review-pack/codex-answers.json)

One question per UNIQUE (LCSC, KiCad footprint, package rotation correction)
among the parts the automatic checks left open (auto 'human' or 'bad'), not per
designator. Only facts go into the prompt (LCSC number, package, pad/pin data
of JLC's EasyEDA record, what our footprint does, what the checks could not
decide): no repo files, no secrets. Codex runs read-only from a scratch
directory outside the repo.

Codex is a language model giving a second opinion. It is NOT a datasheet
check, it does not look at JLC's preview, and it can be wrong. The pack shows
its answer as a distinct 'AUTO-VERIFIED (CODEX)' badge, never the tool badge.

Pure functions (classify, parse_answer, open_types) are unit-tested in
test/test_cpl_autochecks.py.
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import re
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PACK = os.path.join(ROOT, 'build', 'cpl-review-pack')
ANSWERS = os.path.join(PACK, 'codex-answers.json')
SCRATCH = '/tmp/claude-1000/-home-depmod-code-cupc8/5c66b0bc-3cde-4cbe-94c0-0355e82c5b48/scratchpad/codex'
MODEL = 'gpt-6-astra medium'
VERDICTS = ('fine', 'check', 'problem')


def type_key(lcsc, fpid, correction):
    return '%s|%s|%s' % (lcsc, fpid, correction)


def open_types(autos):
    """{type_key: {'lcsc', 'fpid', 'parts': [(board, ref, facts, entry)]}} for
    every part the automatic checks did not verify."""
    types = {}
    for board, refs in autos.items():
        for ref, entry in refs.items():
            if entry['auto'] == 'verified':
                continue
            facts = entry['facts']
            key = type_key(entry['lcsc'], facts['fpid'], facts['correction'])
            group = types.setdefault(key, {'lcsc': entry['lcsc'], 'fpid': facts['fpid'], 'parts': []})
            group['parts'].append((board, ref, facts, entry))
    return types


def easyeda_record(lcsc):
    with open(os.path.join(ROOT, 'hw', 'parts', 'easyeda', lcsc + '.yaml')) as handle:
        return yaml.safe_load(handle)


def summarise_pads(record):
    pads = record['pads']
    pins = {str(k): str(v) for k, v in record['pins'].items()}
    if len(pads) <= 24:
        return 'EasyEDA pads (number, x, y up, mm, at rotation 0): %s. Symbol pin names: %s.' % (
            '; '.join('%s (%.2f, %.2f)' % (n, x, y) for n, x, y in pads), ', '.join('%s=%s' % kv for kv in pins.items()))
    first = [p for p in pads if str(p[0]) in ('1', 'A1', 'B1')][:3]
    xs = [p[1] for p in pads]
    ys = [p[2] for p in pads]
    return ('EasyEDA footprint has %d pads spanning x %.1f..%.1f, y %.1f..%.1f mm (y up, rotation 0); pin-1-type pads: %s. Symbol pin names: %s ...'
            % (len(pads), min(xs), max(xs), min(ys), max(ys), '; '.join('%s (%.2f, %.2f)' % tuple(p) for p in first),
               ', '.join('%s=%s' % kv for kv in list(pins.items())[:6])))


EXTRA_QUESTION = {
    # the iCE40 mismatch: David's wording
    'C1521989': ('Also: JLC EasyEDA symbol pin NAMES differ from ours on 120 of 144 pins vs JLC symbol (e.g. pin 1 is IOL_1A in JLC\'s symbol, IOL_2A in ours) but pad geometry matches JLC\'s footprint exactly and our names match the Lattice HX4K TQ144 pinout: is that a real assembly risk? '
                 'Also its pin-1 corner and numbering direction: LQFP/TQFP-144, pin 1 dot at which corner in the standard TQ144 drawing, numbering counterclockwise seen from the top? Compare with what our footprint does and report any disagreement. Our footprint drawn at 0 deg (seen from the top, checked by code): pad 1 is at the lower-left corner, on the bottom edge at its left end, and the numbers run counterclockwise (pad 2 to its right, pad 37 at the right edge bottom end going up). One board places it at 0 deg, the other at 270 deg (the placed positions above differ for that reason).'),
}


def placements(group):
    """Where the key pad is for each distinct placement angle (the sheet's 'where' is seen as placed, not at 0 deg)."""
    seen = {}
    for _, _, facts, _ in group['parts']:
        seen.setdefault(facts['cpl_rot'], facts['where'])
    return ' | '.join('as placed at CPL %.0f deg: %s' % (rot, where) for rot, where in sorted(seen.items()))


def build_prompt(group):
    record = easyeda_record(group['lcsc'])
    facts = group['parts'][0][2]
    rotations = sorted({p[2]['cpl_rot'] for p in group['parts']})
    open_checks = []
    for _, _, _, entry in group['parts'][:1]:
        for check in entry['checks']:
            if check['status'] in ('unknown', 'fail'):
                open_checks.append('%s %s: %s' % (check['name'], check['status'].upper(), check['detail']))
    lines = [
        'Briefly answer (be concise, max ~250 words). PCB assembly at JLCPCB. Review of pick-and-place (CPL) rotation and pin 1 / polarity for a part our automatic checks could not settle. Facts:',
        '',
        'Part: LCSC %s, %s, JLC package %s. Our KiCad footprint: %s, pad-1/key pad as drawn: %s. JLC EasyEDA footprint: %s.'
        % (group['lcsc'], facts['value'], record.get('jlc_package', '?'), facts['footprint'], placements(group), record['easyeda_footprint']),
        'Our CPL rotation: %s deg (KiCad placement angle %s, package correction in our JLC rotation table: %s).'
        % (', '.join('%.0f' % r for r in rotations), ', '.join('%.0f' % r for r in sorted({p[2]['kicad_rot'] for p in group['parts']})), facts['correction']),
        summarise_pads(record),
        'Our pad geometry matches the EasyEDA footprint pad for pad after that rotation (checked by code).',
        'Checks that could not decide: ' + ' | '.join(open_checks),
        '',
        'Questions: is there a known JLC assembly rotation/polarity/pin-1 pitfall for this part or package (a correction other than 0 that our table lacks, mirrored or 180 deg placement, wrong pin-1 in the JLC library)? Does our placement look right for its pin-1 (or polarity)? What should the human check in JLC\'s preview?',
        EXTRA_QUESTION.get(group['lcsc'], ''),
        '',
        'Cite JLC or manufacturer sources (links) where you can; say plainly if you found none. Begin with one line exactly of the form "VERDICT: fine", "VERDICT: check" (probably fine, but one thing must be confirmed in JLC\'s preview) or "VERDICT: problem" (you believe something is wrong or contradicts our data). Then one line "LOOK AT: ..." with the one thing to look at, then the short reasoning.',
    ]
    return '\n'.join(lines)


def parse_answer(text):
    """{'verdict', 'summary', 'look_at', 'sources'} from Codex's answer; verdict
    'unanswered' when there is no usable VERDICT line."""
    text = (text or '').strip()
    verdict = re.search(r'^\W*VERDICT\W*:?\s*\**\s*(fine|check|problem)\b', text, re.I | re.M)
    look = re.search(r'^\W*LOOK AT\W*:?\s*\**\s*(.+)$', text, re.I | re.M)
    body = re.sub(r'^\W*(VERDICT|LOOK AT)\b.*$', '', text, flags=re.I | re.M).strip()
    return {'verdict': verdict.group(1).lower() if verdict else 'unanswered',
            'summary': body,
            'look_at': look.group(1).strip() if look else '',
            'sources': sorted(set(re.findall(r'https?://[^\s)\]>*"]+', text)))}


def classify(tool_auto, codex, resolution=None):
    """The pack class of a part: 'resolved' only when David's tools/cpl_resolutions.yaml
    has an entry for it (`resolution`, already validated by load_resolutions); that is
    the one way a tool mismatch ('bad') stops being open. Otherwise 'codex-verified'
    only when the tool checks left it open ('human'), and Codex answered fine or
    check. A tool mismatch is never overruled by a language model; an unanswered or
    problem verdict leaves the part with the human."""
    if resolution:
        return 'resolved'
    if tool_auto == 'human' and codex and codex.get('verdict') in ('fine', 'check'):
        return 'codex-verified'
    return tool_auto


def load_resolutions(path):
    """{'board/ref': {verdict, justification, by, date}} from `path`. Raises ValueError
    for an entry with no justification, no `by`/`date`, or a verdict other than 'fine':
    a resolution is never silent."""
    if not os.path.exists(path):
        return {}
    with open(path) as handle:
        entries = yaml.safe_load(handle) or {}
    for key, entry in entries.items():
        entry = entry or {}
        if not re.fullmatch(r'[a-z0-9_]+/[A-Za-z0-9_]+', str(key)):
            raise ValueError('%s: key must be board/ref' % key)
        if entry.get('verdict') != 'fine':
            raise ValueError('%s: verdict must be "fine"' % key)
        for field in ('justification', 'by', 'date'):
            if not str(entry.get(field) or '').strip():
                raise ValueError('%s: %s is required and must not be empty' % (key, field))
        entry['justification'] = ' '.join(str(entry['justification']).split())
        entry['date'] = str(entry['date'])
    return entries


def load_answers():
    if os.path.exists(ANSWERS):
        with open(ANSWERS) as handle:
            return json.load(handle)
    return {}


def ask(key, group, answers_out):
    """Run one Codex call (niced, read-only, stdin closed) and return its answer record."""
    lcsc = group['lcsc']
    prompt = build_prompt(group)
    os.makedirs(SCRATCH, exist_ok=True)
    out_file = os.path.join(SCRATCH, 'out-%s.txt' % lcsc)
    if os.path.exists(out_file):
        os.remove(out_file)
    with open(os.path.join(SCRATCH, 'run-%s.log' % lcsc), 'w') as log:
        try:
            subprocess.run(['nice', '-n', '19', 'timeout', '300', 'codex', 'exec', '--skip-git-repo-check', '-s', 'read-only',
                            '-m', 'gpt-6-astra', '-c', 'model_reasoning_effort=medium', '-o', out_file, prompt],
                           cwd=SCRATCH, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=330)
        except subprocess.TimeoutExpired:
            pass
    text = open(out_file).read() if os.path.exists(out_file) else ''
    answer = parse_answer(text)
    answer.update({'model': MODEL, 'timestamp': datetime.datetime.now().isoformat(timespec='seconds'),
                   'prompt': prompt, 'raw': text})
    return key, answer


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('list', 'run'))
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--only', nargs='*', default=None, help='LCSC numbers to (re)ask')
    args = parser.parse_args()
    with open(os.path.join(PACK, 'auto-checks.json')) as handle:
        autos = json.load(handle)
    types = open_types(autos)
    answers = load_answers()
    todo = {k: g for k, g in types.items() if (args.only is None and k not in answers) or (args.only and g['lcsc'] in args.only)}
    if args.command == 'list':
        for key, group in types.items():
            print('%s  %d parts  %s' % (key, len(group['parts']), 'answered' if key in answers else 'TO ASK'))
        if todo:
            print(build_prompt(next(iter(todo.values()))))
        return
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        for key, answer in pool.map(lambda item: ask(item[0], item[1], None), todo.items()):
            answers[key] = answer
            print('%s -> %s' % (key, answer['verdict']), flush=True)
            with open(ANSWERS, 'w') as handle:
                json.dump(answers, handle, indent=1)
                handle.write('\n')


if __name__ == '__main__':
    main()

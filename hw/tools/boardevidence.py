"""Content-addressed provenance for completed board pipelines.

Receipts certify which inputs produced which files, not whether a check that
is absent from the pipeline passed. Moving a build between worktrees is safe
only when its input hashes still match. No timestamp or Git HEAD shortcuts.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GERBER_SUFFIXES = {'.gbr', '.gtl', '.gbl', '.gts', '.gbs', '.gtp', '.gbp',
                   '.gto', '.gbo', '.gm1', '.g1', '.g2', '.g3', '.g4'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(board, root=ROOT):
    paths = [root / 'hw' / 'boards' / (board + '.py'),
             root / 'hw' / 'boards' / 'rp2040card.py', root / 'hw' / 'pins.yaml']
    if board == 'main':
        paths.extend(root / 'hw' / 'boards' / name for name in
                     ('main_power_reinforce.py', 'main_power_trial5.py',
                      'main_power_input_trial.py'))
    for directory in ('hw/tools', 'hw/lib', 'hw/parts'):
        paths.extend(p for p in (root / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    return {str(p.relative_to(root)): digest(p) for p in sorted(set(paths))}


def artifacts(out):
    return {str(p.relative_to(out)): digest(p) for p in sorted(out.rglob('*'))
            if p.is_file() and p.name not in ('evidence.json', 'cpl-review.json')
            and (p.suffix in {'.kicad_pcb', '.kicad_sch', '.kicad_pro', '.net', '.json', '.csv', '.drl', '.png'} | GERBER_SUFFIXES
                 or p.parent.name == 'fab')}


def record(board, out, before, boards, root=ROOT):
    out = Path(out)
    if before != inputs(board, root):
        raise ValueError('board inputs changed during pipeline; rebuild')
    payload = dict(version=1, board=board, boards=boards, inputs=before, artifacts=artifacts(out))
    temporary = out / 'evidence.json.tmp'
    temporary.write_text(json.dumps(payload, indent=2) + '\n')
    temporary.replace(out / 'evidence.json')


def validate(board, out, root=ROOT):
    out = Path(out)
    evidence = json.loads((out / 'evidence.json').read_text())
    if evidence.get('version') != 1 or evidence.get('board') != board:
        raise ValueError('wrong board or unsupported evidence version')
    if evidence.get('inputs') != inputs(board, root):
        raise ValueError('stale board evidence: source inputs differ; rebuild')
    if evidence.get('artifacts') != artifacts(out):
        raise ValueError('changed or missing board artifacts; rebuild')
    required = [board + ext for ext in ('.kicad_sch', '.kicad_pcb', '.kicad_pro', '.net')]
    required += ['erc.json', 'drc.json', 'fab/bom.csv', 'fab/cpl.csv', 'fab/order.json',
                 board + '-top.png', board + '-bottom.png']
    for name in required:
        if not (out / name).is_file() or not (out / name).stat().st_size:
            raise ValueError('missing or empty artifact: ' + name)
    if not any(p.stat().st_size for p in (out / 'fab').iterdir() if p.suffix in GERBER_SUFFIXES):
        raise ValueError('missing or empty Gerber artifact')
    if not any(p.stat().st_size for p in (out / 'fab').glob('*.drl')):
        raise ValueError('missing or empty drill artifact')
    if type(evidence.get('boards')) is not int or evidence['boards'] < 1:
        raise ValueError('missing assembly quantity')
    return evidence

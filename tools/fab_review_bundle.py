#!/usr/bin/env python3
"""Regenerate unsigned board images and CPL review overlays from valid receipts."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw' / 'tools'))
import boardevidence  # noqa: E402
import cploverlay  # noqa: E402

BOARDS = ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_bundle(names, destination):
    images = destination / 'board-pngs' / 'current'
    overlays = destination / 'fab-overlays' / 'current'
    images.mkdir(parents=True, exist_ok=True)
    overlays.mkdir(parents=True, exist_ok=True)
    for name in names:
        board = ROOT / 'build' / 'hw' / name
        boardevidence.validate(name, board)
        for side in ('top', 'bottom'):
            source = board / f'{name}-{side}.png'
            shutil.copyfile(source, images / source.name)
        cploverlay.render(board, overlays)
        reviewed = {str(path.relative_to(board)): digest(path) for path in (
            board / 'fab' / 'bom.csv', board / 'fab' / 'cpl.csv',
            board / f'{name}.kicad_pcb', board / f'{name}-top.png')}
        template = {'board': name, 'reviewer': '', 'reviewed_at': '',
                    'result': 'pending', 'notes': '', 'sha256': reviewed}
        (overlays / name / f'{name}-cpl-review-template.json').write_text(
            json.dumps(template, indent=2) + '\n')
        print(name, 'receipt valid; images and unsigned CPL review ready')
    (images / 'README.txt').write_text(
        'Current receipt-bound board renders. The top and bottom images are visual aids; '
        'Gerber and CPL signoff remains separate.\n')
    (overlays / 'README.txt').write_text(
        'Unsigned CPL review bundle. Blue circles are placement centres; red arrows show '
        'numeric CPL rotation, not physical pin 1. Compare every designator, pin 1, '
        'polarized part and rotation with its footprint, BOM and manufacturer drawing. '
        'After human review, fill a copy of each template and place it at '
        'build/hw/<board>/fab/cpl-review.json. Rebuilds invalidate old hashes. '
        'A template or overlay is never signoff.\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boards', nargs='*', choices=BOARDS, default=BOARDS)
    parser.add_argument('--destination', type=Path, default=ROOT / 'build')
    args = parser.parse_args()
    build_bundle(args.boards, args.destination.resolve())


if __name__ == '__main__':
    main()

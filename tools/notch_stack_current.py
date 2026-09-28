#!/usr/bin/env python3
"""Measure the seven current card key-notch stacks from receipt-bound artifacts."""

import argparse
import json
from pathlib import Path
import sys

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw/tools'))
import boardevidence  # noqa: E402
import fabcheck  # noqa: E402
import gerberdrc  # noqa: E402

CARDS = ('cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system')
RULE_MM = .30
CEM_NOTCH_MIN_MM = 1.84
CEM_FINGER_MIN_MM = .65
CURRENT_PITCH_MAX_MM = 3.01  # hw/mech/fit.py allows 3.00 +/- 0.01


def clearance(left_center, right_center, left_width, right_width,
              left_wall, right_wall):
    return (left_wall - (left_center + left_width / 2),
            (right_center - right_width / 2) - right_wall)


def required_gap(notch_width, left_width, right_width, rule=RULE_MM):
    """Necessary center gap for both wall clearances to meet the rule."""
    return notch_width + (left_width + right_width) / 2 + 2 * rule


def vertical_segments(path):
    position = None
    mode = 'G01'
    result = []
    for line in path.read_text().splitlines():
        if line in ('G01*', 'G02*', 'G03*'):
            mode = line[:-1]
        elif move := gerberdrc.PROFILE_MOVE.fullmatch(line):
            position = (int(move[1]) / 1e6, int(move[2]) / 1e6)
        elif draw := gerberdrc.PROFILE_DRAW.fullmatch(line):
            target = (int(draw[1]) / 1e6, int(draw[2]) / 1e6)
            if mode == 'G01' and position[0] == target[0]:
                result.append((position[0], min(position[1], target[1]),
                               max(position[1], target[1])))
            position = target
    return result


def inspect(build):
    name = build.name
    evidence = boardevidence.validate(name, build)
    board, _ = fabcheck.export_parity(build, build / 'fab')
    ref = 'J2' if name == 'system' else 'J1'
    footprint = board.FindFootprintByReference(ref)
    if footprint is None:
        raise ValueError(f'{name}: missing card edge {ref}')
    pads = {}
    for pad in footprint.Pads():
        if pad.GetNumber() in ('A11', 'B11', 'A12', 'B12'):
            pos, size = pad.GetPosition(), pad.GetSize()
            pads[pad.GetNumber()] = (pcbnew.ToMM(pos.x), -pcbnew.ToMM(pos.y),
                                     pcbnew.ToMM(size.x), pcbnew.ToMM(size.y))
    if set(pads) != {'A11', 'B11', 'A12', 'B12'}:
        raise ValueError(f'{name}: incomplete key-adjacent pads')
    outline = build / 'fab' / f'{name}-Edge_Cuts.gm1'
    engine = gerberdrc.Geometry()
    try:
        gerberdrc.profile_segments(outline, engine)
    finally:
        engine.close()
    rows = []
    segments = vertical_segments(outline)
    for face in ('A', 'B'):
        left = pads[face + '11']
        right = pads[face + '12']
        if left[0] >= right[0]:
            raise ValueError(f'{name}: reversed key-adjacent fingers')
        span_low = min(left[1]-left[3]/2, right[1]-right[3]/2)
        span_high = max(left[1]+left[3]/2, right[1]+right[3]/2)
        walls = sorted({x for x, low, high in segments
                        if left[0] < x < right[0] and low <= span_low and high >= span_high})
        if len(walls) != 2:
            raise ValueError(f'{name} {face}: expected two straight notch walls across pads, got {walls}')
        gaps = clearance(left[0], right[0], left[2], right[2], *walls)
        rows.append({'face': face, 'centers_mm': [left[0], right[0]],
                     'widths_mm': [left[2], right[2]],
                     'walls_mm': walls, 'notch_mm': round(walls[1]-walls[0], 3),
                     'clearance_mm': [round(value, 3) for value in gaps]})
    return {'board': name, 'receipt_sha256': boardevidence.digest(build / 'evidence.json'),
            'pcb_sha256': evidence['artifacts'][f'{name}.kicad_pcb'],
            'outline_sha256': evidence['artifacts'][f'fab/{outline.name}'],
            'faces': rows,
            'current_rule_mm': RULE_MM,
            'best_fixed_pitch_clearance_mm': round(
                (CURRENT_PITCH_MAX_MM-CEM_NOTCH_MIN_MM-CEM_FINGER_MIN_MM)/2, 3),
            'minimum_gap_for_CEM_minimums_mm': round(
                required_gap(CEM_NOTCH_MIN_MM, CEM_FINGER_MIN_MM,
                             CEM_FINGER_MIN_MM), 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cards', nargs='*', choices=CARDS, default=CARDS)
    args = parser.parse_args()
    for name in args.cards:
        print(json.dumps(inspect(ROOT / 'build/hw' / name)))


if __name__ == '__main__':
    main()

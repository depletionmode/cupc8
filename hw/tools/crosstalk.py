#!/usr/bin/env python3
"""Screen routed straight tracks for long, close same-layer parallel runs.

This is a geometric warning gate, not an analog crosstalk simulation. All
nets are included (including differential pairs and power); review findings
with the analog SI results. No implicit exemptions. Arcs fail closed.
"""
import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    net: str
    layer: str
    start: tuple
    end: tuple
    width: float


def parallel_runs(segments, max_gap=.2, min_length=10):
    """Merge collinear pieces before comparing copper edges, in mm."""
    lines = defaultdict(list)
    for s in segments:
        dx, dy = s.end[0] - s.start[0], s.end[1] - s.start[1]
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        ux, uy = dx / length, dy / length
        if ux < -1e-9 or (abs(ux) < 1e-9 and uy < 0):
            ux, uy = -ux, -uy
        ux, uy = round(ux, 8), round(uy, 8)
        offset = round(-uy * s.start[0] + ux * s.start[1], 6)
        ends = sorted(ux * p[0] + uy * p[1] for p in (s.start, s.end))
        lines[s.layer, ux, uy, s.net, offset, s.width].append(ends)
    directions = defaultdict(list)
    for (layer, ux, uy, net, offset, width), intervals in lines.items():
        merged = []
        for lo, hi in sorted(intervals):
            if merged and lo <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        for lo, hi in merged:
            directions[layer, ux, uy].append((offset, net, width, lo, hi))
    findings = []
    for (layer, ux, uy), tracks in directions.items():
        tracks.sort()
        for i, a in enumerate(tracks):
            for b in tracks[i + 1:]:
                if a[1] == b[1]:
                    continue
                gap = b[0] - a[0] - (a[2] + b[2]) / 2
                overlap = min(a[4], b[4]) - max(a[3], b[3])
                if gap < max_gap - 1e-6 and overlap > min_length + 1e-6:
                    lo, hi = max(a[3], b[3]), min(a[4], b[4])
                    findings.append(dict(layer=layer, nets=[a[1], b[1]],
                        gap_mm=round(gap, 6), length_mm=round(overlap, 6),
                        start_mm=[round(ux*lo-uy*a[0], 6), round(uy*lo+ux*a[0], 6)],
                        end_mm=[round(ux*hi-uy*a[0], 6), round(uy*hi+ux*a[0], 6)]))
    return findings


def read_board(path):
    if not path.is_file():
        raise ValueError('missing routed board: %s' % path)
    from kicadgen import parse
    tree = parse(path.read_text())
    if tree[0] != 'kicad_pcb':
        raise ValueError('not a KiCad PCB')
    nets = {}
    for item in tree[1:]:
        if isinstance(item, list) and item[0] == 'net':
            nets[item[1]] = item[2]
    segments = []
    for item in tree[1:]:
        if not isinstance(item, list):
            continue
        if item[0] == 'arc':
            raise ValueError('unsupported curved track; cannot certify parallel-run screening')
        if item[0] != 'segment':
            continue
        fields = {x[0]: x[1:] for x in item[1:] if isinstance(x, list)}
        raw_net = fields['net'][0]
        # KiCad 10 stores the net name directly; older formats use net ids.
        net = nets.get(raw_net, raw_net)
        if not net or net == '0':
            raise ValueError('routed track has no assigned net')
        segments.append(Segment(net, fields['layer'][0],
            tuple(map(float, fields['start'])), tuple(map(float, fields['end'])),
            float(fields['width'][0])))
    if not segments:
        raise ValueError('no routed tracks')
    return segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    findings = parallel_runs(read_board(args.board))
    report = dict(board=str(args.board), sha256=hashlib.sha256(args.board.read_bytes()).hexdigest(),
                  max_gap_mm=.2, min_length_mm=10, findings=findings)
    result = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(result)
    print(result, end='')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())

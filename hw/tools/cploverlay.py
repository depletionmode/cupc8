#!/usr/bin/env python3
"""Render a machine-generated top-side CPL overlay; never sign a review receipt."""
import argparse
import csv
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import subprocess

import pcbnew
import gerberdrc


VIEWBOX = re.compile(r'viewBox="0\.0000 0\.0000 ([\d.]+) ([\d.]+)"')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def millimetres(value):
    if not value.endswith('mm'):
        raise ValueError('CPL coordinate lacks mm unit: ' + value)
    number = float(value[:-2])
    if not math.isfinite(number):
        raise ValueError('non-finite CPL coordinate')
    return number


def render(board_dir, output_root):
    name = board_dir.name
    pcb = board_dir / (name + '.kicad_pcb')
    cpl = board_dir / 'fab/cpl.csv'
    edge = board_dir / 'fab' / (name + '-Edge_Cuts.gm1')
    for path in (pcb, cpl, edge):
        if not path.is_file():
            raise ValueError('missing overlay input: ' + str(path))
    board = pcbnew.LoadBoard(str(pcb))
    footprints = {footprint.GetReference(): footprint for footprint in board.GetFootprints()}
    rows = list(csv.DictReader(cpl.open(newline='')))
    if not rows:
        raise ValueError(name + ': empty CPL')
    if len({row['Designator'] for row in rows}) != len(rows):
        raise ValueError(name + ': duplicate CPL designator')

    geometry = gerberdrc.Geometry()
    try:
        segments = gerberdrc.profile_segments(edge, geometry)
    finally:
        geometry.close()
    left = min(bounds[0] for _, bounds in segments)
    top = max(bounds[3] for _, bounds in segments)  # Gerber Y-up, SVG Y-down

    destination = output_root / name
    destination.mkdir(parents=True, exist_ok=True)
    svg = destination / (name + '-cpl-overlay.svg')
    png = destination / (name + '-cpl-overlay.png')
    subprocess.run(['kicad-cli', 'pcb', 'export', 'svg', '--layers',
                    'F.Fab,F.SilkS,Edge.Cuts', '--sketch-pads-on-fab-layers',
                    '--mode-single', '--page-size-mode', '2', '--exclude-drawing-sheet',
                    '-o', str(svg), str(pcb)], check=True, capture_output=True, text=True)
    source = svg.read_text()
    if not VIEWBOX.search(source) or '</svg>' not in source:
        raise ValueError(name + ': unexpected KiCad SVG format')
    # KiCad's board-area SVG translates the Edge.Cuts minimum X and maximum
    # Gerber Y to (0, 0). Verify a straight plotted edge before markers.
    first_bounds = segments[0][1]
    x0, y0, x1, y1 = first_bounds
    if abs(y1-y0) < 1e-8:
        a, b = (x0-left, top-y0), (x1-left, top-y1)
    elif abs(x1-x0) < 1e-8:
        a, b = (x0-left, top-y1), (x1-left, top-y0)
    else:
        raise ValueError(name + ': first outline segment is not straight')
    forward = 'M%.4f %.4f\nL%.4f %.4f' % (*a, *b)
    reverse = 'M%.4f %.4f\nL%.4f %.4f' % (*b, *a)
    if forward not in source and reverse not in source:
        raise ValueError(name + ': SVG origin does not align with plotted Edge.Cuts')

    marks = []
    for row in sorted(rows, key=lambda item: item['Designator']):
        ref = row['Designator']
        if row['Layer'] != 'Top' or ref not in footprints:
            raise ValueError(name + ': unsupported CPL layer or missing footprint: ' + ref)
        cx, cy = millimetres(row['Mid X']), millimetres(row['Mid Y'])
        rotation = float(row['Rotation'])
        if not math.isfinite(rotation):
            raise ValueError(name + ': non-finite CPL rotation for ' + ref)
        footprint = footprints[ref]
        position = footprint.GetPosition()
        if abs(cx-pcbnew.ToMM(position.x)) > .01 or abs(cy+pcbnew.ToMM(position.y)) > .01:
            raise ValueError(name + ': CPL placement differs from PCB footprint: ' + ref)
        x, y = cx-left, top-cy
        title = escape('%s — CPL (%.3f, %.3f) mm, Top, %.1f°; rotation arrow is not pin 1' %
                       (ref, cx, cy, rotation))
        label = escape(ref)
        marks.append(
            '<g id="cpl-%s"><title>%s</title>'
            '<circle cx="%.4f" cy="%.4f" r="0.42" fill="none" stroke="#0088ff" stroke-width="0.11"/>'
            '<g transform="rotate(%.4f %.4f %.4f)">'
            '<path d="M%.4f %.4f L%.4f %.4f M%.4f %.4f L%.4f %.4f L%.4f %.4f" '
            'fill="none" stroke="#e00000" stroke-width="0.13"/></g>'
            '<text x="%.4f" y="%.4f" font-size="0.82" font-family="sans-serif" '
            'fill="#c00000" stroke="white" stroke-width="0.20" '
            'paint-order="stroke fill">%s</text></g>' %
            (escape(ref, quote=True), title, x, y, -rotation, x, y,
             x, y, x+1.05, y, x+.78, y-.17, x+1.05, y, x+.78, y+.17,
             x+.48, y-.48, label))
    legend = ('<g id="cpl-legend"><title>Machine-generated placement overlay; human review pending</title>'
              '<rect x="0.25" y="0.25" width="28" height="2.2" fill="white" fill-opacity="0.9"/>'
              '<text x="0.55" y="1.65" font-size="1.0" font-family="sans-serif" fill="#b00000">'
              '%s: %d Top CPL centres; arrows show CPL rotation; review pending</text></g>' %
              (escape(name), len(rows)))
    svg.write_text(source.replace('</svg>', '<g id="cpl-overlay">' + legend + ''.join(marks) + '</g></svg>'))
    subprocess.run(['rsvg-convert', '-w', '2600', '-b', 'white', '-o', str(png), str(svg)],
                   check=True, capture_output=True, text=True)
    inputs = {str(path.relative_to(board_dir)): sha256(path) for path in (pcb, cpl, edge)}
    manifest = {'board': name, 'placements': len(rows), 'review_status': 'pending_human_review',
                'source_sha256': inputs,
                'overlay_sha256': {svg.name: sha256(svg), png.name: sha256(png)}}
    (destination / (name + '-cpl-overlay.json')).write_text(json.dumps(manifest, indent=2) + '\n')
    return png


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board_dirs', nargs='+', type=Path)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    for board_dir in args.board_dirs:
        print(render(board_dir.resolve(), args.output_root.resolve()))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Report which plotted filled-region widths have a conclusive proof."""

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw/tools'))
import boardevidence  # noqa: E402
import gerberdrc  # noqa: E402

BOARDS = ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system')


def analyze_layer(path, minimum, *, silk=False):
    """Return proven isolated passes and explicit deferrals, never a global pass."""
    engine = gerberdrc.Geometry()
    try:
        regions = []
        objects = gerberdrc.plotted_copper(
            path, engine, require_net=not silk,
            extra_function='Legend' if silk else None,
            allow_empty=silk, minimum_track=minimum,
            filled_regions=regions)
        gerberdrc.check_isolated_filled_width(path, engine, objects, regions, minimum)
        gerberdrc.check_isolated_filled_necks(path, engine, objects, regions, minimum)
        gerberdrc.check_connected_filled_necks(path, engine, objects, regions, minimum)
        result = {'filled_regions': len(regions), 'isolated_exact_pass': 0,
                  'touching_other_ink': 0, 'nonorthogonal_or_complex': 0,
                  'hole_or_repaired': 0}
        rule_grid = Decimal(str(minimum)) * 2000000
        for net, shape, bounds, line, points in regions:
            if not engine.simple_hole_free_polygon(shape):
                result['hole_or_repaired'] += 1
                continue
            span = gerberdrc.orthogonal_region_min_span(points)
            if span is None:
                result['nonorthogonal_or_complex'] += 1
                continue
            x0, y0, x1, y1 = bounds
            touching = any(
                other != shape and other_net == net and
                not (x1 < a0 or a1 < x0 or y1 < b0 or b1 < y0) and
                engine.distance(shape, other) == 0
                for other_net, other, (a0, b0, a1, b1) in objects)
            if touching:
                result['touching_other_ink'] += 1
            elif span < rule_grid:
                # The same isolated-region checker above must have rejected it.
                raise AssertionError(f'{path.name}:{line}: isolated narrow span escaped DRC')
            else:
                result['isolated_exact_pass'] += 1
        result['deferred'] = (result['filled_regions'] - result['isolated_exact_pass'])
        result['complete_for_filled_regions'] = result['deferred'] == 0
        return result
    finally:
        engine.close()


def board_check(build):
    receipt = boardevidence.validate(build.name, build)
    board = pcbnew.LoadBoard(str(build / (build.name + '.kicad_pcb')))
    fab = build / 'fab'
    copper = sorted(path for path in fab.iterdir()
                    if path.suffix.lower() in ('.gtl', '.gbl', '.g1', '.g2', '.g3', '.g4'))
    silk = sorted(path for path in fab.iterdir()
                  if path.suffix.lower() in ('.gto', '.gbo'))
    if len(copper) != board.GetCopperLayerCount() or len(silk) != 2:
        raise ValueError(f'{build.name}: incomplete plotted copper or silk layer set')
    settings = board.GetDesignSettings()
    copper_min = pcbnew.ToMM(settings.m_TrackMinWidth)
    silk_min = pcbnew.ToMM(settings.m_MinSilkTextThickness)
    if copper_min <= 0 or silk_min <= 0:
        raise ValueError(f'{build.name}: positive minimum widths required')
    layers = {path.name: analyze_layer(path, copper_min) for path in copper}
    layers.update({path.name: analyze_layer(path, silk_min, silk=True) for path in silk})
    return {'board': build.name,
            'receipt_sha256': boardevidence.digest(build / 'evidence.json'),
            'copper_rule_mm': copper_min, 'silk_ink_rule_mm': silk_min,
            'layers': layers,
            'complete_for_filled_regions': all(
                row['complete_for_filled_regions'] for row in layers.values()),
            'gerber_sha256': {f'fab/{name}': receipt['artifacts'][f'fab/{name}']
                              for name in layers}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boards', nargs='*', choices=BOARDS, default=BOARDS)
    parser.add_argument('--require-complete', action='store_true',
                        help='exit nonzero when any filled region lacks a complete proof')
    args = parser.parse_args()
    incomplete = []
    for name in args.boards:
        result = board_check(ROOT / 'build/hw' / name)
        print(json.dumps(result))
        if not result['complete_for_filled_regions']:
            incomplete.append(name)
    if args.require_complete and incomplete:
        raise SystemExit('filled-region proof incomplete: ' + ', '.join(incomplete))


if __name__ == '__main__':
    main()

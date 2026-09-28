#!/usr/bin/env python3
"""Check plotted copper and Excellon cuts lie inside the plotted board profile."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw/tools'))
import boardevidence  # noqa: E402
import fabcheck  # noqa: E402
import gerberdrc  # noqa: E402

BOARDS = ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system')


def profile_polygon(path, geometry):
    """Reconstruct one closed board perimeter from unordered Gerber segments."""
    gerberdrc.profile_segments(path, geometry)  # strict syntax and file-role check
    edges = []
    position = None
    mode = 'G01'
    for line in path.read_text().splitlines():
        if line in ('G01*', 'G02*', 'G03*'):
            mode = line[:-1]
        elif move := gerberdrc.PROFILE_MOVE.fullmatch(line):
            position = (int(move[1]) / 1e6, int(move[2]) / 1e6)
        elif draw := gerberdrc.PROFILE_DRAW.fullmatch(line):
            target = (int(draw[1]) / 1e6, int(draw[2]) / 1e6)
            if mode == 'G01':
                points = (position, target)
            else:
                points, _ = gerberdrc.arc_points(
                    position, target, (int(draw[3]) / 1e6, int(draw[4]) / 1e6), mode)
            edges.append(tuple(points))
            position = target
    if len(edges) < 3:
        raise ValueError(f'{path.name}: profile has fewer than three edges')
    adjacency = defaultdict(list)
    for index, points in enumerate(edges):
        adjacency[points[0]].append((index, False))
        adjacency[points[-1]].append((index, True))
    if any(len(items) != 2 for items in adjacency.values()):
        raise ValueError(f'{path.name}: plotted profile is open or branched')
    ordered = list(edges[0])
    used = {0}
    while len(used) < len(edges):
        endpoint = ordered[-1]
        following = [(index, reverse) for index, reverse in adjacency[endpoint]
                     if index not in used]
        if len(following) != 1:
            raise ValueError(f'{path.name}: plotted profile has multiple contours')
        index, reverse = following[0]
        points = edges[index][::-1] if reverse else edges[index]
        ordered.extend(points[1:])
        used.add(index)
    if ordered[-1] != ordered[0]:
        raise ValueError(f'{path.name}: plotted profile does not close')
    shape = geometry.wkt(gerberdrc.polygon(ordered))
    return shape


def check(copper_paths, outline, cuts):
    """Return counts; reject any plotted copper or drill cut outside profile."""
    engine = gerberdrc.Geometry()
    try:
        profile = profile_polygon(Path(outline), engine)
        copper_count = 0
        for path in copper_paths:
            for net, shape, _ in gerberdrc.plotted_copper(Path(path), engine):
                if not engine.covers(profile, shape):
                    raise ValueError(f'{Path(path).name}: {net} plotted copper outside board profile')
                copper_count += 1
        drill_count = 0
        for cut, count in cuts.items():
            if len(cut) == 3:
                x, y, diameter = cut
                primitive = engine.wkt(f'POINT ({x:.9f} {y:.9f})')
            elif len(cut) == 6 and cut[0] == 'slot':
                _, x0, y0, x1, y1, diameter = cut
                primitive = engine.wkt(
                    f'LINESTRING ({x0:.9f} {y0:.9f}, {x1:.9f} {y1:.9f})')
            else:
                raise ValueError(f'unsupported plotted cut: {cut!r}')
            shape = engine.buffer(primitive, diameter / 2)
            if not engine.covers(profile, shape):
                raise ValueError(f'{Path(outline).name}: Excellon cut outside board profile: {cut!r}')
            drill_count += count
        if not copper_count or not drill_count:
            raise ValueError('profile containment requires copper and Excellon cuts')
        return {'copper_features': copper_count, 'drill_cuts': drill_count}
    finally:
        engine.close()


def board_check(build):
    name = build.name
    receipt = boardevidence.validate(name, build)
    fab = build / 'fab'
    copper = sorted(path for path in fab.iterdir()
                    if path.suffix.lower() in ('.gtl', '.gbl', '.g1', '.g2', '.g3', '.g4'))
    outlines = sorted(fab.glob('*.gm1'))
    if len(outlines) != 1:
        raise ValueError(f'{name}: expected one plotted profile')
    cuts = sum((fabcheck.drill_hits(path) for path in sorted(fab.glob('*.drl'))),
               Counter())
    counts = check(copper, outlines[0], cuts)
    return {'board': name, 'receipt_sha256': boardevidence.digest(build / 'evidence.json'),
            'outline_sha256': receipt['artifacts'][f'fab/{outlines[0].name}'], **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boards', nargs='*', choices=BOARDS, default=BOARDS)
    args = parser.parse_args()
    for name in args.boards:
        print(json.dumps(board_check(ROOT / 'build/hw' / name)))


if __name__ == '__main__':
    main()

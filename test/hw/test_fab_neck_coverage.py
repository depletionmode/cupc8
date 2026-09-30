#!/usr/bin/env python3
"""Focused filled-region neck proof and boundary reuse regressions."""

from pathlib import Path
import sys
import tempfile
import numpy
import math

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from fab_neck_coverage import analyze_layer, ProofGeometry, corner_caps, covering_corner_caps, ring_vertices  # noqa: E402


def dumbbell(width):
    low = 1500000 - width // 2
    high = low + width
    points = [(1000000, 1000000), (1500000, 1000000),
              (1500000, low), (2000000, low), (2000000, 1000000),
              (2500000, 1000000), (2500000, 2000000),
              (2000000, 2000000), (2000000, high),
              (1500000, high), (1500000, 2000000),
              (1000000, 2000000), (1000000, 1000000)]
    return 'G36*\n' + ''.join(f'X{x}Y{y}D{"02" if i == 0 else "01"}*\n'
                              for i, (x, y) in enumerate(points)) + 'G37*\n'


def plot(region, silk=False):
    file_function = 'Legend,Top' if silk else 'Copper,L1,Top'
    net = '' if silk else '%TO.N,/A*%\n'
    return (f'%TF.FileFunction,{file_function}*%\n'
            '%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n%MOMM*%\n'
            '%LPD*%\n%ADD10C,0.200000*%\nD10*\n' + net + region + 'M02*\n')


def expect_failure(action, expected):
    try:
        action()
    except ValueError as error:
        if expected not in str(error):
            raise AssertionError(f'wrong failure: {error}') from error
    else:
        raise AssertionError(f'{expected} was accepted')


def main():
    with tempfile.TemporaryDirectory(prefix='cupc8-neck-test-') as directory:
        root = Path(directory)
        copper = root / 'test-F_Cu.gtl'
        silk = root / 'test-F_Silkscreen.gto'
        for path, is_silk in ((copper, False), (silk, True)):
            path.write_text(plot(dumbbell(100000), is_silk))
            good = analyze_layer(path, .1, silk=is_silk)
            assert good['filled_regions'] == 1 and good['orthogonal_certificates'] == 1
            assert good['proved'] == 1 and good['complete_for_filled_regions']
            path.write_text(plot(dumbbell(80000), is_silk))
            bad = analyze_layer(path, .1, silk=is_silk)
            assert not bad['complete_for_filled_regions']
            assert any(row['kind'] == 'pinch' and abs(row['width_mm'] - .08) < 1e-6
                       for row in bad['failures'])
        # An acute terminal tip remains unproved under the corner rule.
        sloped = ('G36*\nX1000000Y1000000D02*\nX2000000Y1000000D01*\n'
                  'X2200000Y1800000D01*\nX1000000Y1800000D01*\n'
                  'X1000000Y1000000D01*\nG37*\n')
        copper.write_text(plot(sloped))
        acute = analyze_layer(copper, .1)
        assert acute['filled_regions'] == 1
        assert acute['orthogonal_certificates'] == 0
        assert not acute['complete_for_filled_regions']
        # A nonorthogonal region covered by wider plotted ink exercises the
        # union certificate without using the isolated orthogonal shortcut.
        beveled = ('G36*\nX1000000Y1000000D02*\nX2000000Y1000000D01*\n'
                   'X2200000Y1200000D01*\nX2200000Y1800000D01*\n'
                   'X2000000Y2000000D01*\nX1000000Y2000000D01*\n'
                   'X1000000Y1000000D01*\nG37*\n')
        copper.write_text(plot(beveled))
        standalone = analyze_layer(copper, .1)
        assert standalone['orthogonal_certificates'] == 0
        assert standalone['proved'] == 1 and standalone['complete_for_filled_regions']
        copper.write_text(plot(beveled).replace('M02*',
            '%ADD11C,3.000000*%\nD11*\nX1500000Y1500000D03*\nM02*'))
        complex_result = analyze_layer(copper, .1)
        assert complex_result['orthogonal_certificates'] == 0
        assert complex_result['proved'] == 1 and complex_result['complete_for_filled_regions']
    engine = ProofGeometry()
    try:
        shape = engine.wkt('POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))')
        point = engine.wkt('POINT (0.5 0.5)')
        boundary = engine.boundary(shape)
        retained = len(engine.shapes)
        for _ in range(1000):
            assert engine.boundary(shape) == boundary
            assert engine.distance(point, engine.boundary(shape)) == .5
        assert len(engine.shapes) == retained
        # A certified cap reaches residue whose box excludes the corner.
        vertices = ring_vertices(engine, [shape])
        prepared = engine.prepare(shape)
        radius = .05 / math.cos(math.pi / (4 * 128))
        box = (.01, .01, .02, .02)
        residue = engine.wkt('POLYGON ((.01 .01,.02 .01,.02 .02,.01 .02,.01 .01))')
        assert not corner_caps(engine, prepared, vertices, box, radius)
        caps = covering_corner_caps(engine, prepared, vertices, box, radius)
        assert any(engine.covers(cap, residue) for cap in caps)
        # Nearly pi by acos, but exactly opposite unit vectors: never emit NaN.
        straight = (numpy.array([[.5, .5]]), numpy.array([[1.5, 2.5]]),
                    numpy.array([[-.5, -1.5]]))
        assert not corner_caps(engine, prepared, straight, (0, 0, 1, 1), radius)
    finally:
        engine.close()
    assert not engine._boundaries
    print('filled necks: orthogonal/complex pass; 80 um copper/silk necks and acute tips fail; boundary reused')


if __name__ == '__main__':
    main()

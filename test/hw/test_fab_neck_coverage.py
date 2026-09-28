#!/usr/bin/env python3
"""Focused filled-region neck proof and deferral regressions."""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from fab_neck_coverage import analyze_layer  # noqa: E402


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
            assert good['filled_regions'] == 1 and good['isolated_exact_pass'] == 1
            assert good['deferred'] == 0 and good['complete_for_filled_regions']
            path.write_text(plot(dumbbell(80000), is_silk))
            expect_failure(lambda: analyze_layer(path, .1, silk=is_silk),
                           'isolated filled region has a 0.080000 mm span')
        # A nonorthogonal shape wider than the rule is not declared proved by
        # the exact orthogonal certificate, even when no witness finds a fault.
        sloped = ('G36*\nX1000000Y1000000D02*\nX2000000Y1000000D01*\n'
                  'X2200000Y1800000D01*\nX1000000Y1800000D01*\n'
                  'X1000000Y1000000D01*\nG37*\n')
        copper.write_text(plot(sloped))
        deferred = analyze_layer(copper, .1)
        assert deferred['filled_regions'] == 1
        assert deferred['isolated_exact_pass'] == 0
        assert deferred['nonorthogonal_or_complex'] == 1
        assert not deferred['complete_for_filled_regions']
    print('filled necks: exact orthogonal pass; 80 um copper/silk necks fail; sloped region defers')


if __name__ == '__main__':
    main()

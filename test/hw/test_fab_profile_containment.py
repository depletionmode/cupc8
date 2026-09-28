#!/usr/bin/env python3
"""Focused plotted-profile containment regressions."""

from collections import Counter
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from fab_profile_containment import check  # noqa: E402


PROFILE = '''%TF.FileFunction,Profile,NP*%
%FSLAX46Y46*%
%MOMM*%
%LPD*%
%ADD10C,0.100000*%
D10*
X0Y0D02*
X10000000Y0D01*
X10000000Y0D02*
X10000000Y10000000D01*
X10000000Y10000000D02*
X0Y10000000D01*
X0Y10000000D02*
X0Y0D01*
M02*
'''


def copper(x):
    return '''%TF.FileFunction,Copper,L1,Top*%
%TF.FilePolarity,Positive*%
%FSLAX46Y46*%
%MOMM*%
%LPD*%
%TA.AperFunction,Conductor*%
%ADD10C,0.200000*%
%TD*%
D10*
%TO.N,/A*%
X{x}Y5000000D03*
%TD*%%
M02*
'''.replace('X{x}', f'X{x}').replace('%TD*%%', '%TD*%')


def expect_failure(action, message):
    try:
        action()
    except ValueError as error:
        if message not in str(error):
            raise AssertionError(f'wrong failure: {error}') from error
    else:
        raise AssertionError(f'{message} was accepted')


def main():
    with tempfile.TemporaryDirectory(prefix='cupc8-profile-test-') as directory:
        root = Path(directory)
        edge = root / 'board-Edge_Cuts.gm1'
        copper_path = root / 'board-F_Cu.gtl'
        edge.write_text(PROFILE)
        copper_path.write_text(copper(5000000))
        assert check([copper_path], edge, Counter({(2., 2., .3): 1})) == {
            'copper_features': 1, 'drill_cuts': 1}
        copper_path.write_text(copper(11000000))
        expect_failure(lambda: check([copper_path], edge, Counter({(2., 2., .3): 1})),
                       'plotted copper outside board profile')
        copper_path.write_text(copper(5000000))
        expect_failure(lambda: check([copper_path], edge, Counter({(11., 2., .3): 1})),
                       'Excellon cut outside board profile')
        expect_failure(lambda: check([copper_path], edge,
                                     Counter({('slot', 9.8, 4., 10.2, 4., .3): 1})),
                       'Excellon cut outside board profile')
        edge.write_text(PROFILE.replace('X0Y0D01*\nM02*', 'M02*'))
        expect_failure(lambda: check([copper_path], edge, Counter({(2., 2., .3): 1})),
                       'plotted profile is open or branched')
    print('profile containment: inside passes; outside copper, round drill, slot, and open profile fail')


if __name__ == '__main__':
    main()

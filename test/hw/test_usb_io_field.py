#!/usr/bin/env python3
"""Reject an opened USB pair before running the expensive field solver."""
import argparse
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
sys.path.insert(0, str(ROOT / 'hw/si'))
from kicadgen import dump, find1, parse
from openems_usb_io import (PML_CELLS, PREPREG_MM, ROI, Z_LINES, cleared_axis,
                            cleared_z_lines, routed_pair, signal_path_length,
                            validate_series)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', type=Path, required=True)
    args = parser.parse_args()
    netlist = args.board.with_suffix('.net')
    validate_series(netlist)
    routes, endpoints = routed_pair(args.board)
    lengths = {net: sum(math.dist(a, b) for a, b, _ in parts) for net, parts in routes.items()}
    paths = {net: signal_path_length(parts, *endpoints[net]) for net, parts in routes.items()}
    assert all(length > 0 for length in lengths.values())
    assert all(0 < paths[net] <= lengths[net] for net in routes)
    # The airbox keeps the historical interior lattice phase and moves the
    # physical dielectric/copper outside the nearest eight PML cells.
    for low, high in ((ROI[0], ROI[1]), (ROI[2], ROI[3])):
        lines = cleared_axis(low, high, .075, 1.0)
        assert lines[PML_CELLS] < low < high < lines[-PML_CELLS - 1]
        assert low in lines
        assert all(any(math.isclose(old, new, abs_tol=1e-9) for new in lines)
                   for old in [low + index * .075
                               for index in range(int((high - low) / .075) + 1)])
    z_lines = cleared_z_lines()
    assert z_lines[PML_CELLS] < -PREPREG_MM < 0 < z_lines[-PML_CELLS - 1]
    assert z_lines[PML_CELLS:PML_CELLS + len(Z_LINES)] == Z_LINES
    with tempfile.TemporaryDirectory(prefix='cupc8-usb-open-') as temporary:
        board = parse(args.board.read_text())
        start = endpoints['/USB_CONN_DP'][0]
        candidates = [track for track in board[1:]
                      if isinstance(track, list) and track and track[0] == 'segment' and
                      find1(track, 'net') and find1(track, 'net')[1] == '/USB_CONN_DP' and
                      start in (tuple(round(float(x), 4) for x in find1(track, tag)[1:])
                                for tag in ('start', 'end'))]
        if len(candidates) != 1:
            raise AssertionError(f'USB D+ launch needs one outgoing segment, got {len(candidates)}')
        board.remove(candidates[0])
        broken = Path(temporary) / 'opened.kicad_pcb'
        broken.write_text(dump(board) + '\n')
        try:
            routed_pair(broken)
        except ValueError as error:
            assert 'disconnected' in str(error), str(error)
        else:
            raise AssertionError('opened USB D+ route escaped connectivity check')
        bad_netlist = Path(temporary) / 'wrong-series.net'
        original = netlist.read_text()
        old = '(ref "R14")\n\t\t\t(value "27R")'
        assert original.count(old) == 1
        bad_netlist.write_text(original.replace(old, '(ref "R14")\n\t\t\t(value "47R")'))
        try:
            validate_series(bad_netlist)
        except ValueError as error:
            assert 'lacks 27-ohm series' in str(error), str(error)
        else:
            raise AssertionError('wrong USB D- resistor escaped netlist check')
    print(f"USB IO signal paths D+ {paths['/USB_CONN_DP']:.3f} mm, "
          f"D- {paths['/USB_CONN_DM']:.3f} mm; total copper includes ESD branches. "
          'Open-track and wrong-series mutants rejected')


if __name__ == '__main__':
    main()

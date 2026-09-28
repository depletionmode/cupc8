#!/usr/bin/env python3
"""Copper and source mutation checks for the diagnostic six-slot SCK graph."""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/si'))
from ibis_sck_topology import DELAY_PS_PER_MM, Z0_OHM, extract, spice_deck  # noqa: E402
from test_cosim_main_cpu_data import open_pad_tracks  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path,
                        default=ROOT / 'build/hw/main/main.kicad_pcb')
    parser.add_argument('--netlist', type=Path,
                        default=ROOT / 'build/hw/main/main.net')
    args = parser.parse_args()
    report = extract(args.board, args.netlist)
    assert report['net'] == '/SPI_SCK'
    assert len(report['receivers']) == 6
    assert report['vias'] == 5 and report['branch_nodes'] >= 6
    assert report['copper_length_mm'] > 250
    assert report['netlist_sha256'] and report['board_sha256']
    assert report['valid_for_row_4_6'] is False and report['missing_inputs']
    for edge in report['edges']:
        length = edge['length_mm']
        rlgc = edge['rlgc']
        assert edge['width_mm'] > 0 and length > 0
        assert abs(rlgc['l_nh'] - length * Z0_OHM * DELAY_PS_PER_MM / 1000) < 2e-9
        assert abs(rlgc['c_pf'] - length * DELAY_PS_PER_MM / Z0_OHM) < 2e-9
        assert rlgc['r_ohm'] == rlgc['g_s'] == 0
    audit = json.loads((ROOT / 'doc/hardware/si-evidence/'
                        'ibis-final-source-audit.json').read_text())
    for path in audit['slot_sck']['paths']:
        actual = report['receivers'][path['connector']]['shortest_planar_mm']
        assert abs(actual - path['planar_copper_mm']) <= .002, path
    deck = spice_deck(report)
    assert deck.count('\nT') >= 6 and deck.count('\nCload') == 6
    assert 'Experimental deck' in deck

    with tempfile.TemporaryDirectory(prefix='cupc8-sck-topology-') as directory:
        directory = Path(directory)
        changed = directory / 'open-j16.kicad_pcb'
        open_pad_tracks(args.board, changed, 'J16', 'B13', '/SPI_SCK', 1)
        try:
            extract(changed, args.netlist)
        except ValueError as error:
            assert "SCK copper open from R36.2 to ['J16.B13']" in str(error)
        else:
            raise AssertionError('J16 SCK launch copper open passed')

        source = args.netlist.read_text()
        altered, count = re.subn(r'(\(ref "R36"\)\s*\(value ")33("\))',
                                 r'\g<1>47\2', source, count=1)
        assert count == 1
        wrong = directory / 'wrong-r36.net'
        wrong.write_text(altered)
        try:
            extract(args.board, wrong)
        except ValueError as error:
            assert 'exact 33-ohm R36 source' in str(error)
        else:
            raise AssertionError('wrong R36 source value passed')

    print(f'SCK diagnostic: {len(report["edges"])} electrical edges, '
          f'{report["branch_nodes"]} branch nodes, 6 routed receivers; '
          'J16 copper-open and R36-value mutants rejected; SI gate remains pending')


if __name__ == '__main__':
    main()

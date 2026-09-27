#!/usr/bin/env python3
"""The co-sim input graph must notice missing and swapped schematic wires."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hw/cosim'))
from netlist import read


def fixture(wire='BUS', resistor_output='BUS_SOCKET', socket_input='BUS_SOCKET', include_pull=True):
    comps = [('U1', 'FPGA', 'FPGA_Lattice', 'ICE40HX4K-TQ144'),
             ('J1', 'socket', 'Connector', 'Socket'),
             ('R1', '33', 'Device', 'R'),
             ('R2', '10k', 'Device', 'R')]
    cs = ''.join('(comp (ref "%s") (value "%s") (libsource (lib "%s") (part "%s")))'
                 % c for c in comps)
    ns = [('BUS', [('U1', '1'), ('R1', '1')]),
          (resistor_output, [('R1', '2')]),
          (socket_input, [('J1', '1')]),
          ('3V3', [('R2', '1')]),
          (wire, [('J1', '2')] + ([('R2', '2')] if include_pull else []))]
    # A swapped net name is represented by a changed endpoint, not a duplicate
    # KiCad net declaration.
    merged = {}
    for name, nodes in ns:
        merged.setdefault(name, []).extend(nodes)
    netlist = ''.join('(net (name "%s") %s)' % (name,
                      ''.join('(node (ref "%s") (pin "%s"))' % n for n in nodes))
                      for name, nodes in merged.items())
    return '(export (components %s) (nets %s))' % (cs, netlist)


class NetlistGraphTests(unittest.TestCase):
    def load(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'board.net'
            path.write_text(content)
            return read(path)

    def test_series_resistor_and_pull_stay_in_graph(self):
        circuit = self.load(fixture())
        self.assertFalse(circuit.direct(('U1', '1'), ('J1', '1')))
        self.assertEqual(circuit.series(('U1', '1'), ('J1', '1')).value, '33')
        self.assertEqual([(r.value, net) for r, net in circuit.pulls('3V3')],
                         [('10k', 'BUS')])

    def test_swapped_and_missing_wire_break_expected_path(self):
        for changed in (fixture(socket_input='WRONG'),
                        fixture().replace('(node (ref "R1") (pin "2"))', '')):
            with self.subTest(changed=changed):
                try:
                    circuit = self.load(changed)
                except ValueError:
                    continue
                self.assertIsNone(circuit.series(('U1', '1'), ('J1', '1')))

    def test_reject_duplicate_pin_and_missing_netlist(self):
        with self.assertRaises(ValueError):
            self.load(fixture().replace('(node (ref "J1") (pin "2"))',
                                        '(node (ref "J1") (pin "1"))'))
        with self.assertRaises(ValueError):
            read('/no/such/board.net')

    def test_four_resistor_pack_pin_pairs(self):
        source = fixture().replace('(comp (ref "R1") (value "33") (libsource (lib "Device") (part "R")))',
            '(comp (ref "R1") (value "33") (libsource (lib "Device") (part "R_Pack04")))')
        source = source.replace('(node (ref "R1") (pin "2"))',
                                '(node (ref "R1") (pin "8"))')
        circuit = self.load(source)
        self.assertEqual(circuit.series(('U1', '1'), ('J1', '1')).ref, 'R1.1')
        self.assertEqual(len(circuit.resistors), 2)  # one pack channel and R2
        with self.assertRaises(ValueError):
            self.load(source.replace('(node (ref "R1") (pin "8"))', ''))


if __name__ == '__main__':
    unittest.main()

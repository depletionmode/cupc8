"""Mutation checks for WC-005's KiCad binding and routed copper extraction."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
from wifi_board import PINS, VALUES, routes, topology
sys.path.insert(0, str(ROOT / 'hw'))
from cosim.netlist import Circuit


class WifiPowerBoard(unittest.TestCase):
    def circuit(self):
        pins = dict(PINS)
        nets = {net: tuple(pin for pin, name in pins.items() if name == net)
                for net in set(pins.values())}
        return Circuit(dict(VALUES), nets, pins, ())

    def test_regulator_netlist_mutations(self):
        circuit = self.circuit()
        with patch('wifi_board.read', return_value=circuit):
            self.assertIs(topology('unused'), circuit)
            circuit.pins[('R9', '2')] = '/GND'
            with self.assertRaisesRegex(ValueError, 'R9'):
                topology('unused')
            circuit.pins[('R9', '2')] = '/FB'
            circuit.components['C2'] = ('10u', ('Device', 'C'))
            with self.assertRaisesRegex(ValueError, 'C2'):
                topology('unused')
            circuit.components['C2'] = VALUES['C2']
            circuit.nets['/SW'] += (('R1', '1'),)
            with self.assertRaisesRegex(ValueError, '/SW'):
                topology('unused')

    def fixture(self, directory, broken=False):
        out = Path(directory)
        (out / 'order.json').write_text(json.dumps({'layers': 2, 'thickness_mm': 1.6,
                                                    'finished_outer_copper_oz': 1}))
        parts = ['(kicad_pcb (layers (0 "F.Cu" signal) (31 "B.Cu" signal))']
        by_net = {'/+5V': [], '/3V3': []}
        for index, ((ref, pin), net) in enumerate(PINS.items()):
            x = index + 1
            y = 0 if net == '/+5V' else 5 if net == '/3V3' else 10 + index
            parts.append(f'(footprint "X" (at {x} {y}) (property "Reference" "{ref}") '
                         f'(pad "{pin}" smd rect (at 0 0) (size 0.5 0.5) '
                         f'(layers "F.Cu") (net "{net}")))')
            if net in by_net:
                by_net[net].append(x)
        for net, xs in by_net.items():
            y = 0 if net == '/+5V' else 5
            for a, b in zip(xs, xs[1:]):
                if broken and net == '/3V3' and a == xs[0]:
                    continue
                parts.append(f'(segment (start {a} {y}) (end {b} {y}) '
                             f'(width 0.5) (layer "F.Cu") (net "{net}"))')
        parts.append(')')
        board = out / 'wifi.kicad_pcb'
        board.write_text(' '.join(parts))
        return board, out / 'order.json'

    def test_routed_rails_and_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            board, order = self.fixture(tmp)
            r5, r3 = routes(board, order, self.circuit())
            self.assertGreater(r5, 0)
            self.assertGreater(r3, 0)
            order.write_text(json.dumps({'layers': 4, 'thickness_mm': 1.6}))
            with self.assertRaisesRegex(ValueError, '2-layer'):
                routes(board, order, self.circuit())
            order.write_text(json.dumps({'layers': 2, 'thickness_mm': 1.6}))
            with self.assertRaisesRegex(ValueError, '1 oz'):
                routes(board, order, self.circuit())
            order.write_text(json.dumps({'layers': 2, 'thickness_mm': 1.6,
                                         'finished_outer_copper_oz': 1}))
            board.write_text(board.read_text().replace('(width 0.5)', '(width 0.1)', 1))
            self.assertGreater(routes(board, order, self.circuit())[0], r5)
            board.write_text(board.read_text().replace('(net "/3V3")', '(net "/+5V")', 1))
            with self.assertRaisesRegex(ValueError, 'PCB pad'):
                routes(board, order, self.circuit())

    def test_disconnected_rail_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            board, order = self.fixture(tmp, broken=True)
            with self.assertRaisesRegex(ValueError, 'no routed copper|no routed path'):
                routes(board, order, self.circuit())


if __name__ == '__main__':
    unittest.main()

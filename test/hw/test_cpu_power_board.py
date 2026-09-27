"""Mutation evidence for the CPU card's 1V2 netlist and routed tracks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
from cpu_board import EXPECTED, NET, SINKS, VALUES, route_resistance, topology
sys.path.insert(0, str(ROOT / 'hw'))
from cosim.netlist import Circuit


class CpuPowerBoard(unittest.TestCase):
    def circuit(self):
        pins = dict(EXPECTED)
        nets = {net: tuple(pin for pin, name in pins.items() if name == net)
                for net in set(pins.values())}
        return Circuit(dict(VALUES), nets, pins, ())

    def fixture(self, directory):
        out = Path(directory)
        order = out / 'order.json'
        order.write_text(json.dumps({'layers': 6, 'finished_outer_copper_oz': 1}))
        parts = ['(kicad_pcb']
        rail = [('U3', '5'), *SINKS]
        for index, (pin, net) in enumerate(EXPECTED.items()):
            x = rail.index(pin) + 1 if pin in rail else 30 + index
            y = 0 if net == NET else 5
            parts.append('(footprint "X" (at %s %s) (property "Reference" "%s") '
                         '(pad "%s" smd rect (at 0 0) (size 0.5 0.5) '
                         '(layers "F.Cu") (net "%s")))' % (x, y, pin[0], pin[1], net))
        for x in range(1, len(rail)):
            parts.append('(segment (start %s 0) (end %s 0) (width 0.5) '
                         '(layer "F.Cu") (net "%s"))' % (x, x + 1, NET))
        parts.append(')')
        board = out / 'cpu.kicad_pcb'
        board.write_text(' '.join(parts))
        return board, order

    def test_netlist_pin_swap_fails(self):
        circuit = self.circuit()
        with patch('cpu_board.read', return_value=circuit):
            self.assertIs(topology('unused'), circuit)
            circuit.pins[('U3', '5')] = '/GND'
            with self.assertRaisesRegex(ValueError, 'U3'):
                topology('unused')

    def test_track_width_and_disconnection_change_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            board, order = self.fixture(tmp)
            n, paths = route_resistance(board, order)
            self.assertEqual(n, len(SINKS))
            self.assertTrue(all(ohms > 0 for ohms in paths.values()))
            original = board.read_text()
            board.write_text(original.replace('(width 0.5)', '(width 0.1)', 1))
            self.assertGreater(max(route_resistance(board, order)[1].values()), max(paths.values()))
            board.write_text(original.replace('(segment (start 1 0) (end 2 0) (width 0.5) '
                                              '(layer "F.Cu") (net "/1V2"))', ''))
            with self.assertRaisesRegex(ValueError, 'no 1V2 track|does not reach'):
                route_resistance(board, order)


if __name__ == '__main__':
    unittest.main()

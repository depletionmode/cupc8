"""Exact affine voltage reference and actual native copper counterexamples.

Run with system Python/pcbnew. The production solver is the default target;
CUPC8_TEST_COPPER_MESH may explicitly select an isolated review proposal.
"""
from fractions import Fraction
from pathlib import Path
import importlib.util
import os
import sys
import unittest

import numpy as np
import pcbnew as p

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
proposal = os.environ.get('CUPC8_TEST_COPPER_MESH')
if proposal:
    spec = importlib.util.spec_from_file_location('copper_mesh_under_test', proposal)
    cm = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cm
    spec.loader.exec_module(cm)
else:
    import copper_mesh as cm


def native_strip():
    board = p.BOARD()
    net = p.NETINFO_ITEM(board, '/GND')
    board.Add(net)
    for ref, x in [('SRC', 1), ('PROBE', 4), ('SINK', 8)]:
        fp = p.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetPosition(p.VECTOR2I(p.FromMM(x), p.FromMM(2)))
        pad = p.PAD(fp)
        pad.SetNumber('1')
        pad.SetAttribute(p.PAD_ATTRIB_SMD)
        pad.SetShape(p.PAD_SHAPE_RECT)
        pad.SetSize(p.VECTOR2I(p.FromMM(1), p.FromMM(1)))
        pad.SetPosition(fp.GetPosition())
        layers = p.LSET()
        layers.AddLayer(p.F_Cu)
        pad.SetLayerSet(layers)
        pad.SetNet(net)
        fp.Add(pad)
        board.Add(fp)
    track = p.PCB_TRACK(board)
    track.SetStart(p.VECTOR2I(p.FromMM(1), p.FromMM(2)))
    track.SetEnd(p.VECTOR2I(p.FromMM(8), p.FromMM(2)))
    track.SetWidth(p.FromMM(1))
    track.SetLayer(p.F_Cu)
    track.SetNet(net)
    board.Add(track)
    return board, track


class NativeAffineReference(unittest.TestCase):
    def solve(self, board, **options):
        return cm.solve(board, '/GND', [('SRC', '1')], [('SINK', '1')],
                        (0, 0, 9, 4), pitch=.2, tol=1e-13,
                        probes=[('PROBE', '1')], **options)

    def test_default_keeps_source_reference_exactly(self):
        board, _ = native_strip()
        default = self.solve(board)
        explicit = self.solve(board, voltage_reference='source')
        self.assertEqual(default.milliohms, explicit.milliohms)
        self.assertEqual(default.transfer_milliohms, explicit.transfer_milliohms)
        self.assertEqual(default.j_max_a_per_mm, explicit.j_max_a_per_mm)
        self.assertEqual(default.j_term_a_per_mm, explicit.j_term_a_per_mm)
        for layer in default.grids:
            np.testing.assert_array_equal(default.grids[layer][0], explicit.grids[layer][0])

    def test_native_self_finite_pad_transfer_and_density_are_invariant(self):
        board, _ = native_strip()
        a = self.solve(board, voltage_reference='source')
        b = self.solve(board, voltage_reference='sink')
        self.assertAlmostEqual(a.milliohms / b.milliohms, 1, places=10)
        self.assertGreater(b.transfer_milliohms[('PROBE', '1')], 0)
        np.testing.assert_allclose(list(a.transfer_milliohms.values()),
                                   list(b.transfer_milliohms.values()), rtol=1e-10, atol=1e-12)
        self.assertEqual(a.cells, b.cells)
        for layer in a.grids:
            np.testing.assert_allclose(a.grids[layer][0], b.grids[layer][0],
                                       rtol=1e-9, atol=1e-9)
            np.testing.assert_array_equal(a.grids[layer][1], b.grids[layer][1])

    def test_disconnected_native_pads_fail_in_both_references(self):
        board, track = native_strip()
        board.Remove(track)
        track.thisown = False
        for reference in ('source', 'sink'):
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(ValueError, 'open copper'):
                    self.solve(board, voltage_reference=reference)

    def test_unknown_reference_fails_closed(self):
        board, _ = native_strip()
        with self.assertRaisesRegex(ValueError, 'voltage_reference'):
            self.solve(board, voltage_reference='ground-all-pads')


def rational_solve(matrix, rhs):
    rows = [list(row) + [value] for row, value in zip(matrix, rhs)]
    for i in range(len(rows)):
        pivot = next(j for j in range(i, len(rows)) if rows[j][i])
        rows[i], rows[pivot] = rows[pivot], rows[i]
        scale = rows[i][i]
        rows[i] = [value / scale for value in rows[i]]
        for j in range(len(rows)):
            if i != j:
                scale = rows[j][i]
                rows[j] = [a - scale*b for a, b in zip(rows[j], rows[i])]
    return [row[-1] for row in rows]


class ExactGraphMapping(unittest.TestCase):
    def test_multiple_electrodes_cycle_and_branch_current_mapping(self):
        # This derives the identity independently of the implementation.
        edges = [(0, 1, 2), (0, 2, 5), (1, 2, 7), (2, 3, 11),
                 (3, 4, 13), (4, 5, 17), (2, 6, 19)]
        sources, sinks = {0, 1}, {4, 5}
        free = [2, 3, 6]
        index = {node: i for i, node in enumerate(free)}
        matrix = [[Fraction(0) for _ in free] for _ in free]
        rhs, reverse_rhs = [Fraction(0) for _ in free], [Fraction(0) for _ in free]
        for a, b, conductance in edges:
            for node, neighbour in ((a, b), (b, a)):
                if node not in index:
                    continue
                i = index[node]
                matrix[i][i] += conductance
                if neighbour in index:
                    matrix[i][index[neighbour]] -= conductance
                else:
                    rhs[i] += conductance * int(neighbour in sources)
                    reverse_rhs[i] += conductance * int(neighbour in sinks)
        v = [Fraction(int(i in sources)) for i in range(7)]
        w = [Fraction(int(i in sinks)) for i in range(7)]
        for node, value in zip(free, rational_solve(matrix, rhs)):
            v[node] = value
        for node, value in zip(free, rational_solve(matrix, reverse_rhs)):
            w[node] = value
        self.assertEqual([a+b for a, b in zip(v, w)], [1]*7)
        currents = [g*(v[a]-v[b]) for a, b, g in edges]
        reverse = [g*(w[a]-w[b]) for a, b, g in edges]
        self.assertEqual(currents, [-value for value in reverse])
        total = abs(sum(q*(int(a in sources)-int(b in sources))
                        for (a, b, _), q in zip(edges, currents)))
        reverse_total = abs(sum(q*(int(a in sources)-int(b in sources))
                                for (a, b, _), q in zip(edges, reverse)))
        self.assertEqual(total, reverse_total)
        self.assertEqual(1000/total, 1000/reverse_total)
        self.assertEqual(1000*max(1-v[node] for node in free)/total,
                         1000*max(w[node] for node in free)/reverse_total)


if __name__ == '__main__':
    unittest.main()

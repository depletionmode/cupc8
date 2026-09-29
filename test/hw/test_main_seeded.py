"""The main board's seeded route: the cleanup that runs after the hand-route seed goes on
(kicadgen.remove_dangling(trim=True), main._unbridge_vias), on small pcbnew boards."""

from pathlib import Path
import sys
import unittest

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
sys.path.insert(0, str(ROOT / 'hw/boards'))
import kicadgen as kg
import main

mm = pcbnew.FromMM


def board(pads, tracks=(), vias=()):
    """pads: (ref, net, x, y); tracks: (net, layer, x0, y0, x1, y1, width); vias: (net, x, y). 4 layers."""
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(4)
    nets = {}

    def net(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(b, name)
            b.Add(nets[name])
        return nets[name]
    for ref, name, x, y in pads:
        fp = pcbnew.FOOTPRINT(b)
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        pad = pcbnew.PAD(fp)
        pad.SetNumber("1")
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(ls)
        pad.SetSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
        fp.Add(pad)
        pad.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        pad.SetNet(net(name))
        b.Add(fp)
    for name, layer, x0, y0, x1, y1, w in tracks:
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        t.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        t.SetWidth(mm(w))
        t.SetLayer(layer)
        t.SetNet(net(name))
        b.Add(t)
    for name, x, y in vias:
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        v.SetWidth(mm(0.6))
        v.SetDrill(mm(0.3))
        v.SetNet(net(name))
        b.Add(v)
    return b


def items(b):
    ts = b.Tracks()
    out = []
    for i in range(len(ts)):
        t = ts[i]
        a, e = t.GetStart(), t.GetEnd()
        if t.Type() == pcbnew.PCB_VIA_T:
            out.append(('via', pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)))
        else:
            out.append(('track', pcbnew.ToMM(a.x), pcbnew.ToMM(a.y), pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)))
    return out


class RemoveDangling(unittest.TestCase):
    def test_a_dead_end_stub_and_its_via_go(self):
        b = board([('A', 'N', 10, 10), ('B', 'N', 20, 10)],
                  tracks=[('N', pcbnew.F_Cu, 10, 10, 20, 10, 0.2), ('N', pcbnew.F_Cu, 15, 10, 15, 12, 0.2)],
                  vias=[('N', 15, 12)])
        self.assertEqual(kg.remove_dangling(b, (), trim=True), 2)
        self.assertEqual(items(b), [('track', 10, 10, 20, 10)])

    def test_a_dead_end_that_carries_a_tap_is_shortened_to_the_tap_not_removed(self):
        # A-B is joined to A; its end B is free; a track C-D of the same net starts on its body at x = 14
        b = board([('A', 'N', 10, 10), ('D', 'N', 14, 16)],
                  tracks=[('N', pcbnew.F_Cu, 10, 10, 20, 10, 0.2), ('N', pcbnew.F_Cu, 14, 10, 14, 16, 0.2)])
        kg.remove_dangling(b, (), trim=True)
        got = sorted(items(b))
        self.assertEqual(got, [('track', 10, 10, 14, 10), ('track', 14, 10, 14, 16)])

    def test_without_trim_the_carrier_is_removed(self):
        b = board([('A', 'N', 10, 10), ('D', 'N', 14, 16)],
                  tracks=[('N', pcbnew.F_Cu, 10, 10, 20, 10, 0.2), ('N', pcbnew.F_Cu, 14, 10, 14, 16, 0.2)])
        self.assertGreaterEqual(kg.remove_dangling(b, ()), 1)

    def test_vias_in_a_kept_box_stay(self):
        b = board([('A', 'N', 10, 10)], vias=[('N', 30, 30)])
        kg.remove_dangling(b, (), keep_vias=[tuple(mm(v) for v in (25, 25, 35, 35))])
        self.assertEqual(items(b), [('via', 30, 30)])


class UnbridgeVias(unittest.TestCase):
    def test_a_via_that_holds_two_pieces_on_one_layer_becomes_a_link(self):
        # the pad's stub ends in the via's centre; the route starts at the via's rim (0.25 mm away)
        b = board([('A', 'N', 10, 10), ('B', 'N', 20, 12)],
                  tracks=[('N', pcbnew.F_Cu, 10, 10, 15, 10, 0.2), ('N', pcbnew.F_Cu, 15.25, 10, 20, 12, 0.2)],
                  vias=[('N', 15, 10)])
        self.assertEqual(main._unbridge_vias(b), 1)
        got = items(b)
        self.assertNotIn(('via', 15, 10), got)
        self.assertEqual(kg.remove_dangling(b, (), trim=True), 0)      # nothing dangling, nothing left open
        self.assertEqual(len(got), 3)

    def test_a_through_via_and_a_plane_net_are_left(self):
        b = board([('A', 'N', 10, 10)], tracks=[('N', pcbnew.F_Cu, 10, 10, 15, 10, 0.2),
                                                ('N', pcbnew.B_Cu, 15, 10, 20, 10, 0.2)], vias=[('N', 15, 10)])
        self.assertEqual(main._unbridge_vias(b), 0)
        b = board([('A', 'G', 10, 10)], tracks=[('G', pcbnew.F_Cu, 10, 10, 15, 10, 0.2),
                                                ('G', pcbnew.F_Cu, 15.25, 10, 20, 10, 0.2)], vias=[('G', 15, 10)])
        self.assertEqual(main._unbridge_vias(b, ('G',)), 0)


class NodeJoins(unittest.TestCase):
    def test_a_track_ending_in_anothers_body_gets_a_node_and_a_link(self):
        # B ends 0.06 mm off A's centre line (inside its 0.2 mm width): KiCad joins them; a path measure needs a node
        b = board([('P', 'N', 10, 10), ('Q', 'N', 20, 10), ('R', 'N', 15, 16)],
                  tracks=[('N', pcbnew.F_Cu, 10, 10, 20, 10, 0.2), ('N', pcbnew.F_Cu, 15, 16, 15, 10.06, 0.1)])
        self.assertEqual(main._node_joins(b), 1)
        got = sorted(items(b))
        self.assertIn(('track', 10, 10, 15, 10), got)         # A split at the node (15, 10)
        self.assertIn(('track', 15, 10, 20, 10), got)
        self.assertIn(('track', 15, 10.06, 15, 10), got)      # the link
        self.assertEqual(len(got), 4)

    def test_a_track_ending_off_a_pads_centre_is_linked_to_it_and_planes_are_left(self):
        b = board([('P', 'N', 10, 10), ('G', 'G', 20, 10)],
                  tracks=[('N', pcbnew.F_Cu, 10.2, 10, 15, 10, 0.2), ('G', pcbnew.F_Cu, 20.2, 10, 25, 10, 0.2)])
        self.assertEqual(main._node_joins(b, ('G',)), 1)
        self.assertIn(('track', 10.2, 10, 10, 10), items(b))
        self.assertNotIn(('track', 20.2, 10, 20, 10), items(b))


    def test_a_via_on_a_tracks_body_splits_it(self):
        # an inner-layer track passing through a via's centre (In2 diagonal, the via's own track on F.Cu)
        b = board([('P', 'N', 10, 10), ('Q', 'N', 30, 30)],
                  tracks=[('N', pcbnew.In2_Cu, 10, 10, 30, 30, 0.2), ('N', pcbnew.F_Cu, 20, 20, 20, 25, 0.2)],
                  vias=[('N', 20, 20)])
        self.assertEqual(main._node_joins(b), 0)               # on the line: no link needed
        got = sorted(items(b))
        self.assertIn(('track', 10, 10, 20, 20), got)
        self.assertIn(('track', 20, 20, 30, 30), got)


if __name__ == '__main__':
    unittest.main()

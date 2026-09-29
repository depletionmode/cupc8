"""MB-051 routing prep: every connected SMD pad of the main board gets a fixed via
and stub (hw/boards/main_fanout.py), on a small pcbnew board."""

from pathlib import Path
import math
import sys
import unittest

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/boards'))
import main_fanout as fan

mm = pcbnew.FromMM
to = pcbnew.ToMM


def clearance(net):
    return 0.2


def board(pads, tracks=()):
    """pads: [(ref, number, net, x, y, w, h)]; one footprint per pad, SMD on F.Cu."""
    b = pcbnew.BOARD()
    nets = {}
    for ref, num, net, x, y, w, h in pads:
        if net not in nets:
            nets[net] = pcbnew.NETINFO_ITEM(b, net)
            b.Add(nets[net])
        fp = pcbnew.FOOTPRINT(b)
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        pad = pcbnew.PAD(fp)
        pad.SetNumber(num)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(ls)
        pad.SetSize(pcbnew.VECTOR2I(mm(w), mm(h)))
        fp.Add(pad)
        pad.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        pad.SetNet(nets[net])
        b.Add(fp)
    for net, x0, y0, x1, y1 in tracks:
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        t.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        t.SetWidth(mm(0.2))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(nets[net])
        b.Add(t)
    for a, c in (((0, 0), (40, 0)), ((40, 0), (40, 30)), ((40, 30), (0, 30)), ((0, 30), (0, 0))):
        seg = pcbnew.PCB_SHAPE(b)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1])))
        b.Add(seg)
    return b


def vias(b):
    ts = b.Tracks()
    return [ts[i].Cast() for i in range(len(ts)) if ts[i].Cast().Type() == pcbnew.PCB_VIA_T]


# net N: two SMD pads 12 mm apart, nothing routed; net M: a pad 1.0 mm from N's left pad;
# a big pad K (2 x 1 mm) whose 0.9 mm ring would land inside it
PADS = [('A', '1', 'N', 10.0, 10.0, 0.8, 0.8), ('B', '1', 'N', 22.0, 10.0, 0.8, 0.8),
        ('C', '1', 'M', 10.0, 11.4, 0.8, 0.8), ('D', '1', 'M', 30.0, 20.0, 0.8, 0.8),
        ('K', '1', 'Q', 10.0, 20.0, 2.0, 1.0), ('L', '1', 'Q', 20.0, 20.0, 0.8, 0.8)]


class FanOut(unittest.TestCase):
    def setUp(self):
        self.board = board(PADS)

    def test_every_connected_pad_is_bare_first_then_fanned(self):
        self.assertEqual(len(fan.bare_pads(self.board)), 6)
        placed, unplaced = fan.fan_out_bare_pads(self.board, clearance)
        self.assertEqual((len(placed), unplaced), (6, []))
        self.assertEqual(fan.bare_pads(self.board), [])

    def test_vias_and_stubs_are_locked_and_on_their_own_net(self):
        placed, _ = fan.fan_out_bare_pads(self.board, clearance)
        by_net = {(ref, net): (x, y) for ref, _, net, x, y, _ in placed}
        vs = vias(self.board)
        self.assertEqual(len(vs), 6)
        for v in vs:
            self.assertTrue(v.IsLocked())
            self.assertIn(v.GetNetname(), ('N', 'M', 'Q'))
        for ref, net in by_net:
            fp = self.board.FindFootprintByReference(ref)
            self.assertEqual(fp.Pads()[0].GetNetname(), net)

    def test_via_keeps_its_class_clearance_and_stays_out_of_every_pad(self):
        placed, _ = fan.fan_out_bare_pads(self.board, clearance)
        for ref, _, net, x, y, _ in placed:
            for other in PADS:
                r, _, n, px, py, w, h = other
                dx = max(px - w / 2 - x, x - px - w / 2, 0)
                dy = max(py - h / 2 - y, y - py - h / 2, 0)
                d = math.hypot(dx, dy)
                # inside or touching a pad of its own net: never; other nets: via radius + 0.2
                self.assertGreaterEqual(d, fan.VIA / 2 + (0.2 if n != net else 0.1) - 1e-6, (ref, r))

    def test_deleting_a_via_leaves_a_dangling_stub_that_is_bare_again(self):
        fan.fan_out_bare_pads(self.board, clearance)
        v = vias(self.board)[0]
        net = v.GetNetname()
        self.board.Remove(v)
        self.assertTrue([n for _, _, n in fan.bare_pads(self.board) if n == net])

    def test_a_routed_pad_is_not_bare(self):
        b = board(PADS, tracks=[('N', 10.0, 10.0, 22.0, 10.0)])
        self.assertNotIn(('A', '1', 'N'), fan.bare_pads(b))
        self.assertNotIn(('B', '1', 'N'), fan.bare_pads(b))

    def test_no_room_is_reported_and_exempt_only_when_listed(self):
        # a pad walled in by other nets' pads on all sides
        wall = [('W%d' % i, '1', 'X', 10.0 + 2.0 * math.cos(a), 10.0 + 2.0 * math.sin(a), 1.2, 1.2)
                for i, a in enumerate(math.radians(d) for d in range(0, 360, 20))]
        b = board([('P', '1', 'Y', 10.0, 10.0, 0.8, 0.8), ('P2', '1', 'Y', 35.0, 25.0, 0.8, 0.8)] + wall)
        placed, unplaced = fan.fan_out_bare_pads(b, clearance)
        self.assertEqual([u[:2] for u in unplaced], [('P', '1')])
        self.assertIn(('P', '1', 'Y'), fan.bare_pads(b))
        old = dict(fan.EXEMPT)
        try:
            fan.EXEMPT[('P', '1')] = 'test'
            self.assertNotIn(('P', '1', 'Y'), fan.bare_pads(b))
        finally:
            fan.EXEMPT.clear()
            fan.EXEMPT.update(old)


class WideTrackAndCustomPad(unittest.TestCase):
    def test_a_wide_track_whose_centre_line_is_out_of_reach_still_keeps_vias_off(self):
        # 9 mm wide track along y = 9.5 (edge at 14.0): its centre line is 5.5 mm from the pad, beyond the
        # search's reach (4.6 mm), its copper 1.0 mm from it (the /+5V trunk beside R4's via)
        b = board([('A', '1', 'N', 20.0, 15.0, 0.8, 0.8), ('B', '1', 'N', 32.0, 25.0, 0.8, 0.8),
                   ('T', '1', 'Z', 5.0, 9.5, 0.8, 0.8), ('U', '1', 'Z', 35.0, 9.5, 0.8, 0.8)],
                  tracks=[('Z', 5.0, 9.5, 35.0, 9.5)])
        ts = b.Tracks()
        for i in range(len(ts)):
            if ts[i].GetNetname() == 'Z':
                ts[i].SetWidth(mm(9.0))
        fan.fan_out_bare_pads(b, clearance)
        for v in vias(b):
            if v.GetNetname() == 'N':
                self.assertGreaterEqual(to(v.GetPosition().y) - 14.0, fan.VIA / 2 + 0.2 - 1e-6)

    def test_a_custom_shape_pad_gets_a_stub_as_wide_as_its_box_not_its_anchor(self):
        # U2's corner pads: a 0.005 mm anchor with a polygon on it
        b = board([('A', '1', 'N', 20.0, 15.0, 0.8, 0.8), ('B', '1', 'N', 32.0, 25.0, 0.8, 0.8)])
        pad = b.FindFootprintByReference('A').Pads()[0]
        pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
        pad.SetAnchorPadShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I(mm(0.005), mm(0.005)))
        pad.AddPrimitivePoly(pcbnew.F_Cu, [pcbnew.VECTOR2I(mm(x), mm(y)) for x, y in
                                           ((-0.4, -0.4), (0.4, -0.4), (0.4, 0.4), (-0.4, 0.4))], 0, True)
        fan.fan_out_bare_pads(b, clearance, lambda net: 0.3)
        ts = b.Tracks()
        widths = [to(ts[i].GetWidth()) for i in range(len(ts)) if ts[i].Cast().Type() == pcbnew.PCB_TRACE_T
                  and ts[i].GetNetname() == 'N']
        self.assertTrue(widths)
        self.assertTrue(all(w >= 0.1 for w in widths), widths)


if __name__ == '__main__':
    unittest.main()

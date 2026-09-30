#!/usr/bin/env python3
"""Distributed graph contacts keep finite pad stubs and reject actual gaps."""
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hw/si'))
import pcbnew as p
import slowbus_route as route
vec = lambda x, y: p.VECTOR2I(p.FromMM(x), p.FromMM(y))

class PadContacts(unittest.TestCase):
    def graph(self, y, via=False, tjoin=False):
        b = p.BOARD(); b.SetCopperLayerCount(2)
        n = p.NETINFO_ITEM(b, '/SIG'); b.Add(n)
        for ref, x in [('A', 0), ('B', 4)]:
            f = p.FOOTPRINT(b); f.SetReference(ref); b.Add(f)
            q = p.PAD(f); q.SetNumber('1'); q.SetShape(p.PAD_SHAPE_RECT)
            q.SetSize(vec(.4, .4)); q.SetPosition(vec(2, 2) if tjoin and ref == 'B'
                                                 else vec(x, y if via else 0))
            q.SetAttribute(p.PAD_ATTRIB_SMD)
            ls = p.LSET(); ls.AddLayer(p.F_Cu); q.SetLayerSet(ls); q.SetNet(n); f.Add(q)
        t = p.PCB_TRACK(b); t.SetStart(vec(0, 0 if tjoin else y)); t.SetEnd(vec(4, 0 if tjoin else y))
        t.SetWidth(p.FromMM(.1)); t.SetLayer(p.F_Cu); t.SetNet(n); b.Add(t)
        if tjoin:
            t = p.PCB_TRACK(b); t.SetStart(vec(2, y)); t.SetEnd(vec(2, 2))
            t.SetWidth(p.FromMM(.1)); t.SetLayer(p.F_Cu); t.SetNet(n); b.Add(t)
        pins = ['A.1', 'B.1']
        if via:
            f = p.FOOTPRINT(b); f.SetReference('C'); b.Add(f)
            q = p.PAD(f); q.SetNumber('1'); q.SetShape(p.PAD_SHAPE_RECT)
            q.SetSize(vec(.01, .01)); q.SetPosition(vec(2, 0))
            q.SetAttribute(p.PAD_ATTRIB_SMD); q.SetLayerSet(ls); q.SetNet(n); f.Add(q)
            v = p.PCB_VIA(b); v.SetPosition(vec(2, 0)); v.SetWidth(p.FromMM(.6))
            v.SetDrill(p.FromMM(.3)); v.SetLayerPair(p.F_Cu, p.B_Cu); v.SetNet(n); b.Add(v)
            pins.append('C.1')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'contact.kicad_pcb'; p.SaveBoard(str(path), b)
            with patch.object(route, 'cross_section', return_value=('fixture',)), \
                 patch.object(route, 'xsec_constants', return_value={}):
                return route.extract(path, 'wifi', '/SIG', pins)

    def test_width_contact_keeps_track_and_two_finite_stubs(self):
        g = self.graph(.24)
        self.assertAlmostEqual(sum(t[4] for t in g.tracks), 4.48)
        self.assertEqual(len(g.tracks), 3)

    def test_one_tenth_micron_clear_gap_is_not_connected(self):
        with self.assertRaisesRegex(ValueError, 'copper open'):
            self.graph(.2501)

    def test_existing_pad_center_path_keeps_its_length(self):
        g = self.graph(0)
        self.assertAlmostEqual(sum(t[4] for t in g.tracks), 4.)

    def test_track_body_contacts_via_annulus_with_finite_stub(self):
        g = self.graph(.302, via=True)
        self.assertAlmostEqual(sum(t[4] for t in g.tracks), 4.302)
        self.assertEqual(len(g.barrels), 1)

    def test_via_annulus_real_clear_gap_stays_open(self):
        with self.assertRaisesRegex(ValueError, 'copper open'):
            self.graph(.3501, via=True)

    def test_width_only_track_t_join_retains_finite_bridge(self):
        g = self.graph(.09, tjoin=True)
        self.assertAlmostEqual(sum(t[4] for t in g.tracks), 6.)

    def test_track_t_join_clear_gap_stays_open(self):
        with self.assertRaisesRegex(ValueError, 'copper open'):
            self.graph(.1001, tjoin=True)

if __name__ == '__main__': unittest.main()

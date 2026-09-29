"""Hand/tool routing of the main board's leftovers (hw/boards/main_handroute.py), on small
synthetic pcbnew boards: a legal route is found and passes the KiCad DRC, a walled-in pad is
reported (never violated), the output is deterministic and the seed file reproduces the copper."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/boards'))
import main_handroute as hr

mm = pcbnew.FromMM

PRO = {"board": {"design_settings": {"rules": {"min_track_width": 0.1, "min_clearance": 0.1, "min_via_diameter": 0.6,
                                               "min_through_hole_diameter": 0.3, "min_hole_clearance": 0.25,
                                               "min_hole_to_hole": 0.5, "min_copper_edge_clearance": 0.3,
                                               "min_via_annular_width": 0.13}}},
       "net_settings": {"classes": [{"name": "Default", "track_width": 0.2, "clearance": 0.2, "via_diameter": 0.6,
                                     "via_drill": 0.3, "priority": 2147483647},
                                    {"name": "DenseSignal", "track_width": 0.1, "clearance": 0.1, "via_diameter": 0.7,
                                     "via_drill": 0.3, "priority": 0}],
                        "netclass_patterns": [{"netclass": "DenseSignal", "pattern": "/DENSE*"}], "meta": {"version": 4}},
       "meta": {"filename": "x.kicad_pro", "version": 3}}


def make(path, pads, tracks=(), vias=(), npth=()):
    """A 2-layer 40 x 30 mm board. pads: (ref, net, x, y, w, h); tracks: (net, layer, x0, y0, x1, y1, width);
    npth: (x, y, drill diameter)."""
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(2)
    nets = {}

    def net(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(b, name)
            b.Add(nets[name])
        return nets[name]
    for ref, name, x, y, w, h in pads:
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
        pad.SetSize(pcbnew.VECTOR2I(mm(w), mm(h)))
        fp.Add(pad)
        pad.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        pad.SetNet(net(name))
        b.Add(fp)
    for name, layer, x0, y0, x1, y1, w in tracks:
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        t.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        t.SetWidth(mm(w))
        t.SetLayer(b.GetLayerID(layer))
        t.SetNet(net(name))
        b.Add(t)
    for name, x, y in vias:
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        v.SetWidth(mm(0.6))
        v.SetDrill(mm(0.3))
        v.SetNet(net(name))
        b.Add(v)
    for k, (x, y, d) in enumerate(npth):
        fp = pcbnew.FOOTPRINT(b)
        fp.SetReference("H%d" % k)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        pad = pcbnew.PAD(fp)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetSize(pcbnew.VECTOR2I(mm(d), mm(d)))
        pad.SetDrillSize(pcbnew.VECTOR2I(mm(d), mm(d)))
        fp.Add(pad)
        pad.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        b.Add(fp)
    for a, c in (((0, 0), (40, 0)), ((40, 0), (40, 30)), ((40, 30), (0, 30)), ((0, 30), (0, 0))):
        seg = pcbnew.PCB_SHAPE(b)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1])))
        b.Add(seg)
    pcbnew.SaveBoard(str(path), b)
    with open(str(path)[:-len(".kicad_pcb")] + ".kicad_pro", "w") as f:
        json.dump(PRO, f)


class Route(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def wall_board(self, name, back_wall):
        """A on the left, B on the right, a foreign wall (x = 20, full height) on F.Cu (and on B.Cu)."""
        p = self.dir / (name + ".kicad_pcb")
        tracks = [("/WALL", "F.Cu", 20, -1, 20, 31, 0.3)] + ([("/WALL", "B.Cu", 20, -1, 20, 31, 0.3)] if back_wall else [])
        make(p, [("A", "/SIG", 5, 15, 1, 1), ("B", "/SIG", 35, 15, 1, 1), ("W", "/WALL", 20, 1, 1, 1)], tracks)
        return p

    def route(self, p, **kw):
        b = hr.Board(str(p))
        return b, hr.route_all(b, log=lambda *a: None, **kw)

    def test_routes_round_a_wall_and_passes_drc(self):
        """Layer change through a via, every emitted piece legal: the KiCad DRC has no violation."""
        p = self.wall_board("w", back_wall=False)
        b, res = self.route(p)
        self.assertEqual([r["status"] for r in res], ["routed"])
        self.assertGreaterEqual(res[0]["vias"], 2)
        hr._add(b.b, b.new)
        pcbnew.SaveBoard(str(p), b.b)
        drc = hr.run_drc(str(p), str(self.dir / "drc.json"))
        # the fixture's own wall runs off the board (edge clearance): not the router's copper
        errors = [v for v in drc["violations"] if v["severity"] == "error"
                  and not any("[/WALL]" in i["description"] for i in v["items"])]
        self.assertEqual(errors, [])
        self.assertEqual(drc["unconnected_items"], [])
        self.assertEqual(hr.leftovers(hr.Board(str(p))), [])

    def test_walled_in_is_reported_not_violated(self):
        """Walls on both layers: no legal path. Nothing emitted, the blocker named, a fix proposed."""
        p = self.wall_board("x", back_wall=True)
        b, res = self.route(p)
        self.assertEqual([r["status"] for r in res], ["blocked"])
        self.assertEqual(b.new, [])
        self.assertTrue(any("/WALL" in " ".join(x) for x in res[0]["blockers"]))
        self.assertTrue(res[0]["proposed_fix"])

    def test_clearance_is_the_larger_of_the_two_nets(self):
        """A dense (0.1) net beside a Default (0.2) net keeps 0.2 to it, on every emitted piece."""
        p = self.dir / "c.kicad_pcb"
        make(p, [("A", "/DENSE1", 5, 15, 1, 1), ("B", "/DENSE1", 35, 15, 1, 1), ("W", "/OTHER", 20, 1, 1, 1)],
             [("/OTHER", "F.Cu", 5, 16.5, 35, 16.5, 0.2)])
        b, res = self.route(p)
        self.assertEqual([r["status"] for r in res], ["routed"])
        for item in b.new:
            if item[0] == "track" and item[2] == "F.Cu":
                y0, y1 = item[4] / 1e6, item[6] / 1e6
                # the wire is 0.1 wide, the other net's 0.2 wide at y 16.5: centre distance >= 0.05 + 0.2 + 0.1
                self.assertTrue(max(y0, y1) <= 16.5 - 0.35 + 1e-9 or min(y0, y1) >= 16.5 + 0.35 - 1e-9, item)

    def test_keeps_out_of_an_unplated_hole(self):
        """A 6 mm NPTH between the pads: the route goes round it, 0.25 mm hole clearance kept (DRC)."""
        p = self.dir / "h.kicad_pcb"
        make(p, [("A", "/SIG", 5, 15, 1, 1), ("B", "/SIG", 35, 15, 1, 1)], npth=[(20, 15, 6)])
        b, res = self.route(p)
        self.assertEqual([r["status"] for r in res], ["routed"])
        hr._add(b.b, b.new)
        pcbnew.SaveBoard(str(p), b.b)
        drc = hr.run_drc(str(p), str(self.dir / "drc.json"))
        self.assertEqual([v["type"] for v in drc["violations"] if v["severity"] == "error"], [])

    def test_deterministic_and_seed_reproduces_the_copper(self):
        p = self.wall_board("d", back_wall=False)
        runs = []
        for k in range(2):
            b, _ = self.route(p)
            runs.append(b.new)
        self.assertEqual(runs[0], runs[1])
        seed = self.dir / "seed.json"
        hr.write_seed(runs[0], str(seed), str(p), "0" * 64)
        fresh = pcbnew.LoadBoard(str(p))
        n = len(fresh.Tracks())
        hr.apply(fresh, str(seed))
        self.assertEqual(len(fresh.Tracks()) - n, len(runs[0]))
        hr.apply(fresh, str(seed))                     # applying twice adds nothing
        self.assertEqual(len(fresh.Tracks()) - n, len(runs[0]))

    def test_leftover_detection_ignores_joined_nets(self):
        p = self.dir / "j.kicad_pcb"
        make(p, [("A", "/S", 5, 15, 1, 1), ("B", "/S", 15, 15, 1, 1)], [("/S", "F.Cu", 5, 15, 15, 15, 0.2)])
        self.assertEqual(hr.leftovers(hr.Board(str(p))), [])


if __name__ == "__main__":
    unittest.main()

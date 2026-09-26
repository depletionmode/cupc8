#!/usr/bin/env python3
"""MB-054: the main board's locked eFuse escapes (main.py _efuse_escapes)
never join two nets, with EN/UVLO on its own net (the POWER button) and
tied to IN as before.

    python3 test/hw/test_efuse_escapes.py

The escapes are laid on a bare board holding only the eFuse (TPS259470,
VQFN-10), each pad on the net main.py gives it; then no track may touch a
pad or a track of another net.
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
sys.path.insert(0, os.path.join(ROOT, "hw", "boards"))
import kicadgen as kg  # noqa: E402
import main  # noqa: E402
import pcbnew  # noqa: E402

to = pcbnew.ToMM
fails = 0


def seg_dist(a, b, c, d):
    """the shortest distance between segments ab and cd (2D)"""
    def pt(p, q, r):
        dx, dy = r[0] - q[0], r[1] - q[1]
        k = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(p[0] - q[0] - k * dx, p[1] - q[1] - k * dy)

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    if cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0:
        return 0.0
    return min(pt(a, c, d), pt(b, c, d), pt(c, a, b), pt(d, a, b))


def run(label, en_net):
    global fails
    spec = [p for p in main.build_parts() if p.ref == "U2"][0]
    b = pcbnew.BOARD()
    lib, name = spec.fp.split(":")
    fp = pcbnew.FootprintLoad(kg.footprint_dir(lib), name)
    fp.SetReference("U2")
    b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(20), pcbnew.FromMM(20)))
    pins = {}
    sym = kg.load_symbol(spec.lib)
    for num, v in kg.symbol_pins(sym).items():
        pins[v[3]] = num
    conns = dict(spec.conns, **{"EN/UVLO": en_net if en_net != "IN" else spec.conns["IN"]})
    nets = {}
    for pname, net in conns.items():
        net = net or "unconnected-%s" % pname
        if net not in nets:
            nets[net] = pcbnew.NETINFO_ITEM(b, "/" + net)
            b.Add(nets[net])
        for p in fp.Pads():
            if p.GetNumber() == str(pins[pname]):
                p.SetNet(nets[net])
    main._efuse_escapes(b, fp)
    ts = b.Tracks()                      # indexed: iterating it breaks on Python 3.14
    tracks = [ts[i] for i in range(len(ts)) if ts[i].Type() == pcbnew.PCB_TRACE_T]
    bad = []
    segs = [((to(t.GetStart().x), to(t.GetStart().y)), (to(t.GetEnd().x), to(t.GetEnd().y)), to(t.GetWidth()) / 2,
             t.GetNetname()) for t in tracks]
    for i, (a, c, w, n) in enumerate(segs):
        for a2, c2, w2, n2 in segs[i + 1:]:
            if n != n2 and seg_dist(a, c, a2, c2) < w + w2 + 0.1:
                bad.append("%s track within 0.1 mm of a %s track" % (n, n2))
        for p in list(fp.Pads()):
            if p.GetNetname() == n:
                continue
            for q in (a, c):
                if p.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(q[0]), pcbnew.FromMM(q[1])), pcbnew.FromMM(w)):
                    bad.append("%s track ends on pad %s (%s)" % (n, p.GetNumber(), p.GetNetname()))
    ok = not bad
    print("%s %s: %d tracks%s" % ("pass" if ok else "FAIL", label, len(tracks),
                                  "" if ok else ": " + "; ".join(sorted(set(bad)))))
    fails += not ok


run("EN/UVLO on its own net (PWR_EN)", "PWR_EN")
run("EN/UVLO tied to IN", "IN")
print("MB-054: %d failed" % fails)
sys.exit(1 if fails else 0)

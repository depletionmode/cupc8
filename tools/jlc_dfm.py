#!/usr/bin/env python3
"""JLCPCB assembly (PCBA) design-for-manufacture facts for a built board.

Reads build/hw/<board>/<board>.kicad_pcb and fab/cpl.csv (read-only) and
reports what JLC's PCBA review looks at: board size, part-to-edge distance,
parts and silkscreen near the card-edge fingers, fiducials and tooling
holes, bottom-side and through-hole parts, part-to-part pad gaps, solder
mask webs between fine-pitch pads, vias in SMD pads, small parts with one
pad solid to a pour (tombstoning), paste coverage on exposed pads, and a
pin-1 silkscreen mark on polarised parts.

    python3 tools/jlc_dfm.py build/hw/gpu [build/hw/io ...]
    python3 tools/jlc_dfm.py --json build/hw/gpu

The thresholds are JLC's published figures as audited in
doc/hardware/jlc-assembly-dfm-audit-20260928.md; the report states facts
and flags, the audit document makes the pass / issue / must-fix calls.
"""
import csv
import json
import math
import sys
from pathlib import Path

# JLC figures (see the audit document for the pages they come from)
EDGE_MM = 3.0            # part body/pad closer than this to a board edge: flag
FINGER_KEEPOUT_MM = 1.0  # nothing (parts, silk, vias) this close to the finger area
PART_GAP_MM = 0.3        # pad-to-pad copper gap between different parts
MASK_WEB_MM = 0.1        # minimum solder mask bridge (green)
BIG_PAD_MM2 = 2.0        # exposed / thermal pads checked for paste coverage
POLAR = ('U', 'D', 'Q', 'J', 'Y', 'RN', 'SW', 'LED')


# ------------------------------------------------------------ geometry (mm)

def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def edges(poly):
    return [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]


def inside(p, poly):
    """Even-odd point in polygon."""
    x, y = p
    hit = False
    for (ax, ay), (bx, by) in edges(poly):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            hit = not hit
    return hit


def poly_gap(p, q):
    """Distance between two polygons' boundaries; 0 when they overlap."""
    if any(inside(v, q) for v in p) or any(inside(v, p) for v in q):
        return 0.0
    return min(min(seg_dist(v, a, b) for v in p for a, b in edges(q)),
               min(seg_dist(v, a, b) for v in q for a, b in edges(p)))


def poly_to_lines(poly, lines):
    return min(seg_dist(v, a, b) for v in poly for a, b in lines)


def area(poly):
    return abs(sum(ax * by - bx * ay for (ax, ay), (bx, by) in edges(poly))) / 2


# ------------------------------------------------------------ board access

def load(board_dir):
    import pcbnew
    board_dir = Path(board_dir)
    b = pcbnew.LoadBoard(str(board_dir / (board_dir.name + '.kicad_pcb')))
    with open(board_dir / 'fab' / 'cpl.csv') as f:
        cpl = {r['Designator']: r for r in csv.DictReader(f)}
    return b, cpl


def sps_polys(sps):
    import pcbnew
    to = pcbnew.ToMM
    out = []
    for i in range(sps.OutlineCount()):
        ol = sps.Outline(i)
        out.append([(to(ol.CPoint(k).x), to(ol.CPoint(k).y)) for k in range(ol.PointCount())])
    return out


def pad_poly(pad, layer):
    import pcbnew
    polys = sps_polys(pad.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE))
    return polys[0] if polys else None


def copper_pads(fp):
    """(pad, layer, polygon) for each pad's outer copper."""
    import pcbnew
    out = []
    for p in fp.Pads():
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if p.IsOnLayer(layer):
                poly = pad_poly(p, layer)
                if poly:
                    out.append((p, layer, poly))
    return out


def seq(items):
    """A KiCad container as a list: iterating some of them breaks on Python 3.14."""
    return [items[i].Cast() for i in range(len(items))]


def silk_points(g):
    """Sample points of a silkscreen item (mm): ends, centres, corners."""
    import pcbnew
    if not isinstance(g, pcbnew.PCB_SHAPE):
        return [xy(g.GetPosition())]
    shape = g.GetShape()
    if shape == pcbnew.SHAPE_T_POLY:
        return [pt for poly in sps_polys(g.GetPolyShape()) for pt in poly]
    if shape == pcbnew.SHAPE_T_RECTANGLE:
        return [xy(v) for v in g.GetRectCorners()]
    if shape == pcbnew.SHAPE_T_CIRCLE:
        return [xy(g.GetCenter())]
    pts = [xy(g.GetStart()), xy(g.GetEnd())]
    if shape == pcbnew.SHAPE_T_ARC:
        pts.append(xy(g.GetArcMid()))
    else:                                 # a segment: its interior counts too
        a, b = pts
        pts += [(a[0] + (b[0] - a[0]) * k / 8, a[1] + (b[1] - a[1]) * k / 8) for k in range(1, 8)]
    return pts


def xy(v):
    import pcbnew
    return (round(pcbnew.ToMM(v.x), 2), round(pcbnew.ToMM(v.y), 2))


# ------------------------------------------------------------ checks

def audit(board_dir):
    import pcbnew
    b, cpl = load(board_dir)
    to = pcbnew.ToMM
    outline_sps = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(outline_sps, False)
    outline = sps_polys(outline_sps)
    lines = [e for poly in outline for e in edges(poly)]
    for i in range(outline_sps.OutlineCount()):          # cutouts count as edges too
        for h in range(outline_sps.HoleCount(i)):
            hole = outline_sps.Hole(i, h)
            lines += edges([(to(hole.CPoint(k).x), to(hole.CPoint(k).y)) for k in range(hole.PointCount())])
    bb = b.GetBoardEdgesBoundingBox()
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    placed = {r: fps[r] for r in cpl}
    r = {'board': Path(board_dir).name,
         'size_mm': [round(to(bb.GetWidth()), 2), round(to(bb.GetHeight()), 2)],
         'layers': b.GetCopperLayerCount(),
         'placed': len(placed)}

    pads = {ref: copper_pads(fp) for ref, fp in placed.items()}

    # part-to-edge: nearest copper pad and nearest courtyard point
    near_edge = []
    for ref, fp in placed.items():
        pad_d = min((poly_to_lines(poly, lines) for _, _, poly in pads[ref]), default=99)
        cy = sps_polys(fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd))
        cy_d = min((poly_to_lines(p, lines) for p in cy), default=pad_d)
        # a courtyard corner off the board: the part overhangs the edge
        out = [seg_dist(v, *min(lines, key=lambda e: seg_dist(v, *e)))
               for p in cy for v in p if not any(inside(v, o) for o in outline)]
        if min(pad_d, cy_d) < EDGE_MM or out:
            near_edge.append({'ref': ref, 'fp': fp.GetFPIDAsString().split(':')[-1], 'at': xy(fp.GetPosition()),
                              'pad_mm': round(pad_d, 2), 'courtyard_mm': round(-max(out) if out else cy_d, 2)})
    r['near_edge'] = sorted(near_edge, key=lambda e: e['courtyard_mm'])

    # card-edge fingers: the finger area and what sits near it
    fingers = [f for f in b.GetFootprints() if f.GetFPIDAsString().startswith('Connector_PCBEdge:')]
    if fingers:
        fpolys = [poly for f in fingers for _, _, poly in copper_pads(f)]
        x0 = min(x for p in fpolys for x, _ in p)
        x1 = max(x for p in fpolys for x, _ in p)
        y0 = min(y for p in fpolys for _, y in p)
        y1 = max(y for p in fpolys for _, y in p)
        area_box = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        near = []
        for ref, fp in placed.items():
            d = min((poly_gap(poly, area_box) for _, _, poly in pads[ref]), default=99)
            cy = sps_polys(fp.GetCourtyard(pcbnew.F_CrtYd))
            d = min([d] + [poly_gap(p, area_box) for p in cy])
            near.append((round(d, 2), ref))
        near.sort()
        silk = []
        items = seq(b.Drawings()) + [g for f in b.GetFootprints() for g in seq(f.GraphicalItems())]
        items += [t for f in b.GetFootprints() for t in (f.Reference(), f.Value()) if t.IsVisible()]
        for g in items:
            if g.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                continue
            gb = g.GetBoundingBox()
            if (to(gb.GetRight()) > x0 - FINGER_KEEPOUT_MM and to(gb.GetLeft()) < x1 + FINGER_KEEPOUT_MM
                    and to(gb.GetBottom()) > y0 - FINGER_KEEPOUT_MM):
                owner = g.GetParentFootprint()
                silk.append({'owner': owner.GetReference() if owner else 'board', 'bottom_y': round(to(gb.GetBottom()), 2)})
        vias = [xy(t.GetPosition()) for t in seq(b.Tracks())
                if t.Type() == pcbnew.PCB_VIA_T and x0 - FINGER_KEEPOUT_MM < to(t.GetPosition().x) < x1 + FINGER_KEEPOUT_MM
                and to(t.GetPosition().y) > y0 - FINGER_KEEPOUT_MM]
        unmasked = sum(1 for f in fingers for p in f.Pads()
                       if not (p.IsOnLayer(pcbnew.F_Mask) or p.IsOnLayer(pcbnew.B_Mask)))
        r['fingers'] = {'area': [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                        'top_y': round(y0, 2), 'nearest_parts': [{'ref': ref, 'mm': d} for d, ref in near[:5]],
                        'silk_within_keepout': silk, 'vias_within_keepout': vias,
                        'fingers_without_mask_opening': unmasked}

    # fiducials and non-plated (tooling-capable) holes
    r['fiducials'] = sorted(f.GetReference() for f in b.GetFootprints() if 'fiducial' in f.GetFPIDAsString().lower())
    r['npth'] = sorted({(f.GetReference(), round(to(p.GetDrillSize().x), 2))
                        for f in b.GetFootprints() for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH})

    # side and technology
    r['bottom'] = sorted(ref for ref, row in cpl.items() if row['Layer'] != 'Top')
    r['tht'] = sorted([ref, fp.GetFPIDAsString().split(':')[-1],
                       sum(1 for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)]
                      for ref, fp in placed.items() if any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in fp.Pads()))

    # part-to-part copper gaps (outer layers)
    close = []
    refs = sorted(placed)
    boxes = {ref: placed[ref].GetBoundingBox(False) for ref in refs}
    for i, a in enumerate(refs):
        for bref in refs[i + 1:]:
            ba, bbx = boxes[a], boxes[bref]
            if not ba.Inflate(pcbnew.FromMM(PART_GAP_MM)).Intersects(bbx):
                ba.Inflate(-pcbnew.FromMM(PART_GAP_MM))
                continue
            ba.Inflate(-pcbnew.FromMM(PART_GAP_MM))
            best = None
            for pa, la, qa in pads[a]:
                for pb, lb, qb in pads[bref]:
                    if la == lb:
                        d = poly_gap(qa, qb)
                        if best is None or d < best[0]:
                            best = (d, pa.GetNumber(), pb.GetNumber())
            if best and best[0] < PART_GAP_MM:
                close.append({'a': '%s.%s' % (a, best[1]), 'b': '%s.%s' % (bref, best[2]), 'mm': round(best[0], 3)})
    r['part_gaps_under'] = sorted(close, key=lambda c: c['mm'])

    # solder mask web between neighbouring pads of one part
    webs = {}
    for ref in refs:
        ps = [(p, la, q) for p, la, q in pads[ref] if p.IsOnLayer(pcbnew.F_Mask if la == pcbnew.F_Cu else pcbnew.B_Mask)]
        for i, (pa, la, qa) in enumerate(ps):
            for pb, lb, qb in ps[i + 1:]:
                if la != lb or (pa.GetNumber() == pb.GetNumber() and pa.GetNetCode() == pb.GetNetCode()):
                    continue
                if (pa.GetPosition() - pb.GetPosition()).EuclideanNorm() > pcbnew.FromMM(3):
                    continue
                gap = poly_gap(qa, qb)
                if gap == 0:
                    continue
                web = gap - pa.GetSolderMaskExpansion(la) / 1e6 - pb.GetSolderMaskExpansion(lb) / 1e6
                if web < webs.get(ref, (99,))[0]:
                    webs[ref] = (round(web, 3), round(gap, 3))
    r['mask_web_min'] = {ref: {'web_mm': w, 'copper_gap_mm': g} for ref, (w, g) in sorted(webs.items(), key=lambda kv: kv[1])[:8]}
    r['mask_web_under'] = sorted(ref for ref, (w, _) in webs.items() if w < MASK_WEB_MM)

    # vias in SMD pads
    vip = {}
    for t in seq(b.Tracks()):
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        v = (to(t.GetPosition().x), to(t.GetPosition().y))
        vr = to(t.GetWidth(pcbnew.F_Cu)) / 2
        for ref in refs:
            for p, la, q in pads[ref]:
                if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not t.IsOnLayer(la):
                    continue
                if inside(v, q) or min(seg_dist(v, a2, b2) for a2, b2 in edges(q)) < vr:
                    key = '%s.%s' % (ref, p.GetNumber())
                    # vias are tented, but not inside a pad's mask opening:
                    # a drill that reaches into the opening is an open hole
                    reach = to(t.GetDrillValue()) / 2 + p.GetSolderMaskExpansion(la) / 1e6
                    open_hole = inside(v, q) or min(seg_dist(v, a2, b2) for a2, b2 in edges(q)) < reach
                    vip.setdefault(key, {'vias': 0, 'open_holes': 0, 'pad_mm2': round(area(q), 2),
                                         'net': p.GetNetname(), 'drill_mm': round(to(t.GetDrillValue()), 2)})
                    vip[key]['vias'] += 1
                    vip[key]['open_holes'] += open_hole
    r['via_in_pad'] = vip

    # small two-pad parts with one pad solid in a pour and the other not
    zones = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetPadConnection() == pcbnew.ZONE_CONNECTION_FULL]

    def poured(p, la):
        return any(z.GetNetCode() == p.GetNetCode() and z.IsOnLayer(la) and z.HitTestFilledArea(la, p.GetPosition())
                   for z in zones)
    tomb = []
    for ref in refs:
        fpn = placed[ref].GetFPIDAsString()
        if len(pads[ref]) == 2 and any(s in fpn for s in ('0201', '0402', '0603')):
            (pa, la, _), (pb, lb, _) = pads[ref]
            if poured(pa, la) != poured(pb, lb):
                tomb.append(ref)
    r['one_pad_solid_small'] = tomb
    r['zone_pad_connection'] = sorted({str(z.GetPadConnection()) for z in b.Zones() if not z.GetIsRuleArea()})

    # paste coverage on big pads (exposed pads, module ground pads)
    paste = []
    for ref, fp in placed.items():
        fpaste = [pad_poly(p, pcbnew.F_Paste) for p in fp.Pads() if p.IsOnLayer(pcbnew.F_Paste)]
        for p, la, q in pads[ref]:
            if la != pcbnew.F_Cu or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or area(q) < BIG_PAD_MM2:
                continue
            cov = sum(area(s) for s in fpaste if s and inside(((sum(x for x, _ in s) / len(s)), sum(y for _, y in s) / len(s)), q))
            paste.append({'pad': '%s.%s' % (ref, p.GetNumber()), 'pad_mm2': round(area(q), 2),
                          'paste_pct': round(100 * cov / area(q)), 'net': p.GetNetname()})
    r['big_pad_paste'] = paste

    # pin-1 mark
    nomark = []
    for ref, fp in placed.items():
        prefix = ''.join(c for c in ref if c.isalpha())
        if prefix not in POLAR:
            continue
        silk = [g for g in seq(fp.GraphicalItems()) if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
        pin1 = [p for p in fp.Pads() if p.GetNumber() in ('1', 'A1', 'K')]
        if not silk:
            nomark.append({'ref': ref, 'why': 'no silkscreen in footprint'})
        elif not pin1:
            nomark.append({'ref': ref, 'why': 'no pad 1'})
        else:
            # the silk must tell pad 1 from its mirror through the part's
            # centre: some silk point with no mirror image (a chamfer, dot,
            # bar or longer side); a 180-degree symmetric outline is no mark
            c = xy(fp.GetPosition())
            pts = [pt for g in silk for pt in silk_points(g)]
            odd = [pt for pt in pts
                   if not any(math.dist((2 * c[0] - pt[0], 2 * c[1] - pt[1]), q) < 0.1 for q in pts)]
            if not odd:
                nomark.append({'ref': ref, 'why': 'silk symmetric about the centre'})
    r['pin1_unmarked'] = nomark
    return r


def main(argv):
    as_json = '--json' in argv
    dirs = [a for a in argv if a != '--json']
    results = [audit(d) for d in dirs]
    if as_json:
        json.dump(results, sys.stdout, indent=1)
        print()
        return
    for res in results:
        print('== %s' % res['board'])
        for k, v in res.items():
            if k != 'board':
                print('  %s: %s' % (k, json.dumps(v)))


if __name__ == '__main__':
    main(sys.argv[1:])

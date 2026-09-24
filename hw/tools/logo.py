#!/usr/bin/env python3
"""Turn the Kaplan Labs logo (a potrace SVG) into a KiCad footprint.

The SVG is a black rectangle with the artwork cut out of it, so the ink is
every subpath except the outer rectangle, filled even-odd. Curves are
flattened, holes are attached to their outlines, and pcbnew fractures the
result into the simple polygons a footprint can hold (as bitmap2component
does). The footprint is board-only: no BOM line, no placement file entry.

    python3 hw/tools/logo.py [width_mm ...]    writes hw/lib/cupc8.pretty/

Before writing, the smallest feature is checked against JLC's 0.15 mm
silkscreen line minimum on a 10 µm raster; a size that loses detail fails.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SVG = os.path.expanduser(os.environ.get("KAPLAN_LOGO", "~/.config/omarchy/branding/kaplan-labs.svg"))
LIB = os.path.join(ROOT, "hw", "lib", "cupc8.pretty")
MIN_FEATURE_MM = 0.15


def subpaths(svg_text):
    """Every subpath as a list of (x, y) in SVG user units, Y down."""
    g = re.search(r'<g transform="translate\(([-\d.]+),([-\d.]+)\) scale\(([-\d.]+),([-\d.]+)\)"', svg_text)
    tx, ty, sx, sy = map(float, g.groups())
    out = []
    for d in re.findall(r'<path d="([^"]+)"', svg_text):
        toks = re.findall(r'[MmLlCcZz]|-?[\d.]+', d)
        i, cmd = 0, None
        x = y = sx0 = sy0 = 0.0
        cur = []

        def num():
            nonlocal i
            v = float(toks[i])
            i += 1
            return v
        while i < len(toks):
            if re.match(r'[A-Za-z]', toks[i]):
                cmd = toks[i]
                i += 1
                if cmd in "Zz":
                    if cur:
                        out.append(cur)
                    cur = []
                    x, y = sx0, sy0
                    continue
            if cmd in "Mm":
                if cur:
                    out.append(cur)
                dx, dy = num(), num()
                x, y = (x + dx, y + dy) if cmd == "m" else (dx, dy)
                sx0, sy0 = x, y
                cur = [(x, y)]
                cmd = "l" if cmd == "m" else "L"       # implicit lineto after a moveto
            elif cmd in "Ll":
                dx, dy = num(), num()
                x, y = (x + dx, y + dy) if cmd == "l" else (dx, dy)
                cur.append((x, y))
            elif cmd in "Cc":
                p = [num() for _ in range(6)]
                if cmd == "c":
                    p = [p[0] + x, p[1] + y, p[2] + x, p[3] + y, p[4] + x, p[5] + y]
                for k in range(1, 9):                  # flatten: 8 segments a curve
                    t = k / 8
                    a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                    cur.append((a * x + b * p[0] + c * p[2] + e * p[4],
                                a * y + b * p[1] + c * p[3] + e * p[5]))
                x, y = p[4], p[5]
        if cur:
            out.append(cur)
    # into user units, Y down
    return [[(tx + sx * px, ty + sy * py) for px, py in sp] for sp in out]


def area(poly):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))


def inside(pt, poly):
    x, y = pt
    c = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            c = not c
    return c


def ink(svg_text):
    """[(outline, [holes])] of the white artwork, in SVG units."""
    polys = subpaths(svg_text)
    polys.sort(key=lambda p: -abs(area(p)))
    polys = polys[1:]                                  # drop the black background
    depth = [sum(inside(p[0], q) for j, q in enumerate(polys) if j != i) for i, p in enumerate(polys)]
    shapes = []
    for i, p in enumerate(polys):
        if depth[i] % 2 == 0:
            holes = [q for j, q in enumerate(polys) if depth[j] == depth[i] + 1 and inside(q[0], p)]
            shapes.append((p, holes))
    return shapes


def check_features(shapes, scale, min_mm):
    """Fraction of ink lost by an opening with a min_mm-wide square: detail
    thinner than that would not print."""
    from PIL import Image, ImageDraw, ImageFilter
    px_mm = 0.01
    xs = [x for o, _ in shapes for x, _ in o]
    ys = [y for o, _ in shapes for _, y in o]
    w = int((max(xs) - min(xs)) * scale / px_mm) + 20
    h = int((max(ys) - min(ys)) * scale / px_mm) + 20
    img = Image.new("1", (w, h), 0)
    dr = ImageDraw.Draw(img)

    def pts(poly):
        return [((x - min(xs)) * scale / px_mm + 10, (y - min(ys)) * scale / px_mm + 10) for x, y in poly]
    for o, holes in shapes:
        dr.polygon(pts(o), fill=1)
        for hole in holes:
            dr.polygon(pts(hole), fill=0)
    k = int(round(min_mm / px_mm)) | 1
    img = img.convert("L")
    opened = img.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
    import numpy
    return 1 - numpy.count_nonzero(numpy.asarray(opened)) / numpy.count_nonzero(numpy.asarray(img))


def footprint(width_mm, layer="F.SilkS"):
    import pcbnew
    name = "KaplanLabs_Logo_%gmm" % width_mm
    path = os.path.join(LIB, name + ".kicad_mod")
    if not os.path.exists(SVG) and os.path.exists(path):
        # the SVG is not in the repo; without it, use the footprint committed
        # from it (KAPLAN_LOGO=<svg> regenerates it)
        print("logo: %s not found; using the committed %s" % (SVG, os.path.relpath(path, ROOT)))
        m = re.search(r'\(descr "Kaplan Labs logo, [\d.]+ x ([\d.]+) mm', open(path).read())
        return path, float(m.group(1)) if m else None, None, None
    with open(SVG) as f:
        shapes = ink(f.read())
    xs = [x for o, _ in shapes for x, _ in o]
    ys = [y for o, _ in shapes for _, y in o]
    scale = width_mm / (max(xs) - min(xs))
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    lost = check_features(shapes, scale, MIN_FEATURE_MM)
    if lost > 0.02:
        raise SystemExit("%.1f mm logo: %.1f%% of the ink is thinner than %.2f mm" %
                         (width_mm, 100 * lost, MIN_FEATURE_MM))

    def iu(poly):
        return [(pcbnew.FromMM((x - cx) * scale), pcbnew.FromMM((y - cy) * scale)) for x, y in poly]
    ps = pcbnew.SHAPE_POLY_SET()
    for o, holes in shapes:
        ps.NewOutline()
        for x, y in iu(o):
            ps.Append(x, y)
        for hole in holes:
            idx = ps.NewHole()
            for x, y in iu(hole):
                ps.Append(x, y, -1, idx)
    ps.Fracture()

    height = (max(ys) - min(ys)) * scale
    lines = ['(footprint "%s"' % name, '\t(version 20240108)', '\t(generator "cupc8-logo")',
             '\t(layer "F.Cu")', '\t(descr "Kaplan Labs logo, %g x %.1f mm, %s")' % (width_mm, height, layer),
             '\t(attr board_only exclude_from_pos_files exclude_from_bom)',
             '\t(property "Reference" "LOGO" (at 0 0 0) (layer "F.SilkS") (hide yes) '
             '(effects (font (size 1 1) (thickness 0.15))))',
             '\t(property "Value" "%s" (at 0 0 0) (layer "F.Fab") (hide yes) '
             '(effects (font (size 1 1) (thickness 0.15))))' % name]
    for i in range(ps.OutlineCount()):
        ol = ps.Outline(i)
        pts = " ".join("(xy %.4f %.4f)" % (pcbnew.ToMM(ol.CPoint(j).x), pcbnew.ToMM(ol.CPoint(j).y))
                       for j in range(ol.PointCount()))
        lines.append('\t(fp_poly (pts %s) (stroke (width 0) (type solid)) (fill solid) (layer "%s"))'
                     % (pts, layer))
    lines.append(")")
    os.makedirs(LIB, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path, height, lost, ps.OutlineCount()


if __name__ == "__main__":
    for w in (sys.argv[1:] or ["14"]):
        try:
            path, h, lost, n = footprint(float(w))
        except SystemExit as e:
            print(e)
            continue
        print("%s: %s x %.1f mm, %d polygons, %.2f%% of ink under %.2f mm" %
              (os.path.relpath(path, ROOT), w, h, n, 100 * lost, MIN_FEATURE_MM))

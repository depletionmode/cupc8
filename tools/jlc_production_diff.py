#!/usr/bin/env python3
"""Diff JLC's post-CAM production Gerbers against ours before confirming them.

With "Confirm Production File" ticked on the order, JLC sends back the files
its CAM will actually build. Their CAM may trim or shift gold fingers, move a
key notch or change drills when a design is outside its rules
(doc/hardware/jlc-order-checklist.md). This renders both sets, copper, solder
mask and the board profile (filled), at `--resolution`, and reports every
difference wider than `--tolerance` (smaller ones are etch compensation and
rendering noise), plus drill hits that are missing, extra or resized beyond
`--drill-tolerance` (JLC enlarges plated drills for plating; that is expected).

    python3 tools/jlc_production_diff.py build/hw/cpu/fab ~/Downloads/jlc-cpu.zip

Either side is a directory or a .zip. Layers pair by their X2 FileFunction,
else by Protel extension (.gtl .gbl .g1.. .gts .gbs .gm1/.gko, drills .drl
.xln); `--map ours=theirs` pairs a file by hand. JLC may move the origin: the
two sets are aligned on their profiles' lower-left corners (the offset is
printed). Differences within 3 mm of the board edge, where the fingers and
notch are, are marked EDGE. Exit 0: no differences; 1: differences; 2: a
layer could not be paired or parsed. Not handled: step-and-repeat (a
panelised file), Gerber 2020 LM/LR/LS transforms, Excellon rout mode.
"""

import argparse
import ast
import math
import os
import re
import sys
import zipfile
from collections import deque

import numpy as np
from PIL import Image, ImageDraw

EXT = {'gtl': 'copper-top', 'gbl': 'copper-bot', 'gts': 'mask-top', 'gbs': 'mask-bot',
       'gm1': 'profile', 'gko': 'profile', 'gml': 'profile', 'gm': 'profile'}
DRILL_EXT = ('drl', 'xln', 'exc')
EDGE_BAND_MM = 3.0
CELL_MM = 0.5


# ---------------------------------------------------------------- Gerber

def statements(text):
    """Split RS-274X into (extended?, statement) pairs, newlines ignored."""
    text = text.replace('\r', '').replace('\n', '')
    for block in re.findall(r'%[^%]*%|[^%*]*\*', text):
        if block.startswith('%'):
            for s in block[1:-1].split('*'):
                if s:
                    yield True, s
        elif block[:-1]:
            yield False, block[:-1]


def macro_value(expr, env):
    expr = re.sub(r'\$(\d+)', lambda m: repr(env.get(int(m.group(1)), 0.0)), expr)
    tree = ast.parse(expr.replace('x', '*').replace('X', '*'), mode='eval')
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                                 ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)):
            raise ValueError('aperture macro expression %r' % expr)
    return float(eval(compile(tree, '<macro>', 'eval')))


def rotate(points, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def circle_poly(cx, cy, d, n=48):
    return [(cx + d / 2 * math.cos(2 * math.pi * k / n), cy + d / 2 * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def aperture_shapes(kind, params, macros, scale):
    """An aperture as [(dark?, polygon)] in mm around its origin. A clear
    part (a hole, an exposure-off macro primitive) clears the layer under it,
    not only the aperture: close enough for a diff, and neither KiCad nor
    JLC's CAM output is known to rely on the difference."""
    return [(dark, [(x * scale, y * scale) for x, y in poly])
            for dark, poly in aperture_file_units(kind, params, macros)]


def aperture_file_units(kind, params, macros):
    if kind in ('C', 'R', 'O', 'P'):
        hole = None
        if kind == 'C':
            shapes = [(True, circle_poly(0, 0, params[0]))]
            hole = params[1] if len(params) > 1 else None
        elif kind == 'R':
            w, h = params[0] / 2, params[1] / 2
            shapes = [(True, [(-w, -h), (w, -h), (w, h), (-w, h)])]
            hole = params[2] if len(params) > 2 else None
        elif kind == 'O':
            w, h = params[0], params[1]
            r = min(w, h) / 2
            a, b = (w / 2 - r, 0) if w >= h else (0, h / 2 - r)
            shapes = [(True, stroke_poly([(-a, -b), (a, b)], r * 2))]
            hole = params[2] if len(params) > 2 else None
        else:
            n = int(params[1])
            rot = params[2] if len(params) > 2 else 0
            shapes = [(True, rotate(circle_poly(0, 0, params[0], n), rot))]
            hole = params[3] if len(params) > 3 else None
        if hole:
            shapes.append((False, circle_poly(0, 0, hole)))
        return shapes
    env = {i + 1: v for i, v in enumerate(params)}
    shapes = []
    for prim in macros[kind]:
        prim = prim.strip()
        if not prim or prim.startswith('0'):
            continue
        if prim.startswith('$'):
            name, expr = prim.split('=', 1)
            env[int(name[1:])] = macro_value(expr, env)
            continue
        v = [macro_value(p, env) for p in prim.split(',')]
        code, dark = int(v[0]), v[1] != 0
        if code == 1:
            rot = v[5] if len(v) > 5 else 0
            shapes.append((dark, rotate(circle_poly(v[3], v[4], v[2]), rot)))
        elif code in (20, 2):
            shapes.append((dark, rotate(rect_stroke(v[3], v[4], v[5], v[6], v[2]), v[7])))
        elif code == 21:
            w, h, cx, cy = v[2] / 2, v[3] / 2, v[4], v[5]
            shapes.append((dark, rotate([(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h),
                                         (cx - w, cy + h)], v[6])))
        elif code == 4:
            n = int(v[2])
            pts = [(v[3 + 2 * k], v[4 + 2 * k]) for k in range(n + 1)]
            shapes.append((dark, rotate(pts, v[5 + 2 * n])))
        elif code == 5:
            shapes.append((dark, rotate(circle_poly(v[3], v[4], v[5], int(v[2])), v[6])))
        elif code == 7:  # thermal: drawn as its ring (gaps ignored)
            shapes.append((True, rotate(circle_poly(v[1], v[2], v[3]), v[6])))
            shapes.append((False, rotate(circle_poly(v[1], v[2], v[4]), v[6])))
        else:
            raise ValueError('aperture macro primitive %d' % code)
    return shapes


def rect_stroke(x1, y1, x2, y2, w):
    """A square-ended line of width w as a polygon."""
    length = math.hypot(x2 - x1, y2 - y1) or 1e-9
    nx, ny = -(y2 - y1) / length * w / 2, (x2 - x1) / length * w / 2
    return [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]


def stroke_poly(seg, d):
    """A round-ended line of width d as a polygon."""
    (x1, y1), (x2, y2) = seg
    a = math.atan2(y2 - y1, x2 - x1)
    pts = [(x2 + d / 2 * math.cos(a - math.pi / 2 + math.pi * k / 16),
            y2 + d / 2 * math.sin(a - math.pi / 2 + math.pi * k / 16)) for k in range(17)]
    pts += [(x1 + d / 2 * math.cos(a + math.pi / 2 + math.pi * k / 16),
             y1 + d / 2 * math.sin(a + math.pi / 2 + math.pi * k / 16)) for k in range(17)]
    return pts


def arc_points(start, end, center, clockwise, full_ok):
    r = math.hypot(start[0] - center[0], start[1] - center[1])
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = a0 - a1 if clockwise else a1 - a0
    sweep %= 2 * math.pi
    if sweep < 1e-9 and full_ok:
        sweep = 2 * math.pi
    n = max(2, int(abs(sweep) * max(r, 0.01) / 0.02) + 1)
    sign = -1 if clockwise else 1
    return [(center[0] + r * math.cos(a0 + sign * sweep * k / n),
             center[1] + r * math.sin(a0 + sign * sweep * k / n)) for k in range(1, n)] + [end]


def parse_gerber(text):
    """Return {'function': str|None, 'ops': [(dark?, polygon mm)],
    'segments': [(a, b)]}: `segments` are the centre lines of every draw,
    which is what a profile layer is."""
    fmt, scale = (4, 6), 1.0
    zero_trailing = False
    macros, apertures, current = {}, {}, None
    pos, dark, interp, multi = (0.0, 0.0), True, 'G01', True
    region, contour, ops, function, last_d = False, [], [], None, 'D02'
    segments = []
    macro_name = None

    def coord(s):
        if '.' in s:
            return float(s) * scale
        if zero_trailing:
            neg = s.startswith('-')
            s = s.lstrip('+-').ljust(fmt[0] + fmt[1], '0')
            v = int(s) / 10 ** fmt[1]
            return (-v if neg else v) * scale
        return int(s) / 10 ** fmt[1] * scale

    def finish_contour():
        if len(contour) > 2:
            ops.append((dark, list(contour)))

    for extended, s in statements(text):
        if extended:
            if macro_name is not None and not s.startswith('AM') and re.match(r'^[\d$]', s):
                macros[macro_name].append(s)
                continue
            macro_name = None
            if s.startswith('FS'):
                m = re.match(r'FS([LT])([AI])X(\d)(\d)Y\d\d', s)
                zero_trailing = m.group(1) == 'T'
                if m.group(2) == 'I':
                    raise ValueError('incremental coordinates are not supported')
                fmt = (int(m.group(3)), int(m.group(4)))
            elif s.startswith('MO'):
                scale = 25.4 if s == 'MOIN' else 1.0
            elif s.startswith('AM'):
                macro_name = s[2:]
                macros[macro_name] = []
            elif s.startswith('AD'):
                m = re.match(r'ADD(\d+)([^,]+),?(.*)$', s)
                params = [float(p) for p in m.group(3).split('X') if p]
                apertures[int(m.group(1))] = (m.group(2), params)
            elif s.startswith('LP'):
                dark = s == 'LPD'
            elif s.startswith('TF.FileFunction'):
                function = s[len('TF.FileFunction,'):]
            elif s.startswith('SR') and s != 'SR':
                if not re.match(r'SRX1Y1', s):
                    raise ValueError('step and repeat (a panelised file) is not supported')
            elif s[:2] in ('LM', 'LR', 'LS') and s not in ('LMN', 'LR0', 'LS1'):
                raise ValueError('aperture transformation %s is not supported' % s)
            continue
        if s.startswith('G04') or s in ('M02', 'M00', 'M01'):
            continue
        m = re.match(r'^(G\d+)?(.*)$', s)
        g, rest = m.group(1), m.group(2)
        if g:
            g = 'G%02d' % int(g[1:])
            if g in ('G01', 'G02', 'G03'):
                interp = g
            elif g == 'G36':
                region, contour = True, []
            elif g == 'G37':
                finish_contour()
                region, contour = False, []
            elif g == 'G74':
                multi = False
            elif g == 'G75':
                multi = True
            elif g == 'G70':
                scale = 25.4
            elif g == 'G71':
                scale = 1.0
        if not rest:
            continue
        sel = re.match(r'^D(\d+)$', rest)
        if sel and int(sel.group(1)) >= 10:
            current = int(sel.group(1))
            continue
        w = dict(re.findall(r'([XYIJD])([+-]?[\d.]+)', rest))
        x = coord(w['X']) if 'X' in w else pos[0]
        y = coord(w['Y']) if 'Y' in w else pos[1]
        d = 'D%02d' % int(w['D']) if 'D' in w else last_d
        last_d = d
        target = (x, y)
        if d == 'D03':
            for sdark, poly in aperture_shapes(*apertures[current], macros, scale):
                ops.append((dark == sdark, [(px + x, py + y) for px, py in poly]))
        elif d == 'D02':
            if region:
                finish_contour()
                contour = [target]
        elif d == 'D01':
            if interp == 'G01':
                path = [target]
            else:
                i = coord(w['I']) if 'I' in w else 0.0
                j = coord(w['J']) if 'J' in w else 0.0
                cw = interp == 'G02'
                if multi:
                    center = (pos[0] + i, pos[1] + j)
                else:  # single quadrant: pick the signs whose arc is <= 90 degrees
                    best = None
                    for si in (1, -1):
                        for sj in (1, -1):
                            c = (pos[0] + si * abs(i), pos[1] + sj * abs(j))
                            err = abs(math.hypot(pos[0] - c[0], pos[1] - c[1])
                                      - math.hypot(x - c[0], y - c[1]))
                            a0 = math.atan2(pos[1] - c[1], pos[0] - c[0])
                            a1 = math.atan2(y - c[1], x - c[0])
                            sweep = ((a0 - a1) if cw else (a1 - a0)) % (2 * math.pi)
                            if sweep <= math.pi / 2 + 1e-6 and (best is None or err < best[0]):
                                best = (err, c)
                    center = best[1]
                path = arc_points(pos, target, center, cw, multi)
            if region:
                if not contour:
                    contour = [pos]
                contour.extend(path)
            else:
                kind, params = apertures[current]
                params = [v * scale for v in params]
                prev = pos
                for p in path:
                    segments.append((prev, p))
                    if kind == 'R':
                        corners = []
                        for cx, cy in (prev, p):
                            corners += [(cx + sx * params[0] / 2, cy + sy * params[1] / 2)
                                        for sx in (-1, 1) for sy in (-1, 1)]
                        ops.append((dark, hull(corners)))
                    else:
                        ops.append((dark, stroke_poly((prev, p), params[0] if params else 0)))
                    prev = p
        pos = target
    return {'function': function, 'ops': ops, 'segments': segments}


def hull(points):
    points = sorted(set(points))
    if len(points) < 3:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# ---------------------------------------------------------------- Excellon

def parse_drill(text):
    """Return [(x, y, diameter)] in mm; a G85 slot is its two end hits."""
    metric, lz, digits = True, False, None
    tools, tool, hits, pos = {}, None, [], (0.0, 0.0)

    def coord(s):
        if '.' in s:
            v = float(s)
        else:
            neg = s.startswith('-')
            s = s.lstrip('+-')
            whole, frac = digits or ((3, 3) if metric else (2, 4))
            v = int(s.ljust(whole + frac, '0')) / 10 ** frac if lz else int(s) / 10 ** frac
            v = -v if neg else v
        return v if metric else v * 25.4

    for line in text.replace('\r', '').split('\n'):
        line = line.strip()
        m = re.match(r';\s*FILE_FORMAT=(\d):(\d)', line)
        if m:
            digits = (int(m.group(1)), int(m.group(2)))
        if not line or line.startswith(';'):
            continue
        if line.startswith(('METRIC', 'M71')):
            metric = True
            lz = 'LZ' in line
        elif line.startswith(('INCH', 'M72')):
            metric = False
            lz = 'LZ' in line
        m = re.match(r'^T(\d+)(?:[FSB][\d.]+)*C([\d.]+)', line)
        if m:
            tools[int(m.group(1))] = float(m.group(2)) * (1 if metric else 25.4)
            continue
        m = re.match(r'^T(\d+)$', line)
        if m:
            tool = int(m.group(1))
            continue
        for part in re.split(r'(?=G85)', line):
            w = dict(re.findall(r'([XY])([+-]?[\d.]+)', part))
            if not w or not re.match(r'^(G85)?[XY]', part):
                continue
            pos = (coord(w['X']) if 'X' in w else pos[0], coord(w['Y']) if 'Y' in w else pos[1])
            if tool is not None and tool in tools and tools[tool] > 0:
                hits.append((pos[0], pos[1], tools[tool]))
    return hits


# ---------------------------------------------------------------- rendering and diff

class Frame:
    def __init__(self, xmin, ymin, xmax, ymax, res):
        self.xmin, self.ymax, self.res = xmin, ymax, res
        self.w = int(math.ceil((xmax - xmin) / res)) + 1
        self.h = int(math.ceil((ymax - ymin) / res)) + 1

    def px(self, poly, dx=0.0, dy=0.0):
        return [((x + dx - self.xmin) / self.res, (self.ymax - y - dy) / self.res) for x, y in poly]

    def render(self, ops, dx=0.0, dy=0.0):
        img = Image.new('1', (self.w, self.h), 0)
        draw = ImageDraw.Draw(img)
        for dark, poly in ops:
            if len(poly) > 2:
                draw.polygon(self.px(poly, dx, dy), fill=1 if dark else 0)
        return np.array(img, dtype=bool)

    def render_profile(self, layer, dx=0.0, dy=0.0):
        """Fill the region the profile's drawn loops enclose (even-odd); a
        profile drawn as regions is rendered as it is."""
        if not layer['segments']:
            return self.render(layer['ops'], dx, dy)
        loops = chain(layer['segments'])
        filled = np.zeros((self.h, self.w), dtype=bool)
        for loop in loops:
            img = Image.new('1', (self.w, self.h), 0)
            ImageDraw.Draw(img).polygon(self.px(loop, dx, dy), fill=1)
            filled ^= np.array(img, dtype=bool)
        return filled


def chain(segments, eps=0.01):
    loops, left = [], list(segments)
    while left:
        a, b = left.pop()
        loop = [a, b]
        grew = True
        while grew and math.dist(loop[0], loop[-1]) > eps:
            grew = False
            for k, (p, q) in enumerate(left):
                if math.dist(p, loop[-1]) <= eps:
                    loop.append(q)
                elif math.dist(q, loop[-1]) <= eps:
                    loop.append(p)
                else:
                    continue
                left.pop(k)
                grew = True
                break
        loops.append(loop)
    return loops


def erode(mask, n):
    out = mask.copy()
    for k in range(1, n):
        out[:, :-k] &= mask[:, k:]
        out[:, -k:] = False
    col = out.copy()
    for k in range(1, n):
        out[:-k, :] &= col[k:, :]
        out[-k:, :] = False
    return out


def cells(mask, c):
    h, w = mask.shape
    padded = np.zeros(((h + c - 1) // c * c, (w + c - 1) // c * c), dtype=bool)
    padded[:h, :w] = mask
    return padded.reshape(padded.shape[0] // c, c, padded.shape[1] // c, c).any(axis=(1, 3))


def clusters(grid):
    seen, found = np.zeros_like(grid), []
    for start in zip(*np.nonzero(grid)):
        if seen[start]:
            continue
        seen[start] = True
        queue, members = deque([start]), []
        while queue:
            r, c = queue.popleft()
            members.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < grid.shape[0] and 0 <= cc < grid.shape[1] and grid[rr, cc] \
                            and not seen[rr, cc]:
                        seen[rr, cc] = True
                        queue.append((rr, cc))
        found.append(members)
    return found


def compare(ours, theirs, frame, tol, edge_band):
    """Report lines for the differences wider than tol between two rendered layers."""
    n = max(1, int(round(tol / frame.res)))
    removed, added = erode(ours & ~theirs, n), erode(theirs & ~ours, n)
    c = max(1, int(round(CELL_MM / frame.res)))
    grid_removed, grid_added = cells(removed, c), cells(added, c)
    report = []
    for members in clusters(grid_removed | grid_added):
        rows = [r for r, _ in members]
        cols = [col for _, col in members]
        x0 = frame.xmin + min(cols) * c * frame.res
        x1 = frame.xmin + (max(cols) + 1) * c * frame.res
        y1 = frame.ymax - min(rows) * c * frame.res
        y0 = frame.ymax - (max(rows) + 1) * c * frame.res
        what = []
        if any(grid_removed[m] for m in members):
            what.append('removed')
        if any(grid_added[m] for m in members):
            what.append('added')
        near = any(edge_band[m] for m in members if m[0] < edge_band.shape[0]
                   and m[1] < edge_band.shape[1])
        report.append('%s%s at X %.2f..%.2f Y %.2f..%.2f mm (our coordinates)'
                      % ('EDGE ' if near else '', '+'.join(what), x0, x1, y0, y1))
    return sorted(report, key=lambda line: not line.startswith('EDGE'))


def compare_drills(ours, theirs, dx, dy, pos_tol, dia_tol):
    report, resized = [], 0
    bucket = {}
    for k, (x, y, d) in enumerate(theirs):
        bucket.setdefault((round((x - dx) / 0.5), round((y - dy) / 0.5)), []).append(k)
    used = set()
    for x, y, d in ours:
        best = None
        gx, gy = round(x / 0.5), round(y / 0.5)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for k in bucket.get((gx + i, gy + j), []):
                    tx, ty, td = theirs[k]
                    dist = math.hypot(tx - dx - x, ty - dy - y)
                    if k not in used and dist <= pos_tol and (best is None or dist < best[0]):
                        best = (dist, k, td)
        if best is None:
            report.append('drill %.3f mm at X %.3f Y %.3f missing' % (d, x, y))
            continue
        used.add(best[1])
        if abs(best[2] - d) > dia_tol:
            report.append('drill at X %.3f Y %.3f resized %.3f -> %.3f mm' % (x, y, d, best[2]))
        elif abs(best[2] - d) > 1e-6:
            resized += 1
    for k, (x, y, d) in enumerate(theirs):
        if k not in used:
            report.append('drill %.3f mm at X %.3f Y %.3f (their coordinates) extra' % (d, x, y))
    return report, resized


# ---------------------------------------------------------------- files

def layer_key(name, function):
    if function:
        f = function.split(',')
        if f[0] == 'Copper':
            return {'Top': 'copper-top', 'Bot': 'copper-bot'}.get(
                f[2], 'copper-in%d' % (int(f[1][1:]) - 1))
        if f[0] == 'Soldermask':
            return 'mask-' + f[1].lower()
        if f[0] == 'Profile':
            return 'profile'
        return None
    ext = name.rsplit('.', 1)[-1].lower()
    m = re.match(r'^g(?:p)?(\d+)$', ext)
    if m:
        return 'copper-in%d' % int(m.group(1))
    return EXT.get(ext)


def load(source, manual):
    """{key: parsed layer} and the combined drill hits of a directory or zip."""
    files = {}
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as z:
            for info in z.infolist():
                if not info.is_dir():
                    files[os.path.basename(info.filename)] = z.read(info).decode('latin-1')
    else:
        for name in sorted(os.listdir(source)):
            path = os.path.join(source, name)
            if os.path.isfile(path):
                with open(path, encoding='latin-1') as f:
                    files[name] = f.read()
    layers, drills, drill_files = {}, [], []
    for name, text in sorted(files.items()):
        ext = name.rsplit('.', 1)[-1].lower()
        if ext in DRILL_EXT or manual.get(name) == 'drill':
            drills += parse_drill(text)
            drill_files.append(name)
            continue
        if 'FS' not in text[:4000] and name not in manual:
            continue
        head = re.search(r'%TF\.FileFunction,([^*]+)\*%', text)
        key = manual.get(name) or layer_key(name, head.group(1) if head else None)
        if key:
            if key in layers:
                raise ValueError('%s: two files map to %s' % (source, key))
            layers[key] = (name, text)
    return layers, drills, drill_files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ours', help='our fab directory, e.g. build/hw/cpu/fab (or a zip)')
    ap.add_argument('theirs', help="JLC's production files (directory or zip)")
    ap.add_argument('--resolution', type=float, default=0.02, help='mm per pixel (0.02)')
    ap.add_argument('--tolerance', type=float, default=0.1,
                    help='ignore differences narrower than this, mm (0.1)')
    ap.add_argument('--drill-position', type=float, default=0.05, help='drill match radius, mm')
    ap.add_argument('--drill-tolerance', type=float, default=0.16,
                    help='drill diameter change allowed (plating allowance), mm')
    ap.add_argument('--map', action='append', default=[],
                    help='THEIR_FILE=KEY, KEY one of copper-top copper-bot copper-inN '
                         'mask-top mask-bot profile drill')
    args = ap.parse_args(argv)
    manual = dict(m.split('=', 1) for m in args.map)
    try:
        ours, our_drills, _ = load(args.ours, {})
        theirs, their_drills, their_drill_files = load(args.theirs, manual)
        parsed_ours = {k: parse_gerber(t) for k, (_, t) in ours.items()}
        parsed_theirs = {k: parse_gerber(t) for k, (_, t) in theirs.items()}
    except (ValueError, KeyError, IndexError, AttributeError) as e:
        print('cannot parse: %s' % e)
        return 2
    missing = sorted(set(ours) - set(theirs))
    if missing:
        print('no production file for: %s (their files: %s; pair them with --map)'
              % (', '.join(missing), ', '.join(sorted(n for n, _ in theirs.values()))))
        return 2
    if 'profile' not in ours:
        print('our files have no profile layer')
        return 2

    def bbox(parsed):
        pts = [p for seg in parsed['segments'] for p in seg] or \
            [p for _, poly in parsed['ops'] for p in poly]
        return (min(p[0] for p in pts), min(p[1] for p in pts),
                max(p[0] for p in pts), max(p[1] for p in pts))
    ob, tb = bbox(parsed_ours['profile']), bbox(parsed_theirs['profile'])
    dx, dy = tb[0] - ob[0], tb[1] - ob[1]
    size_ours, size_theirs = (ob[2] - ob[0], ob[3] - ob[1]), (tb[2] - tb[0], tb[3] - tb[1])
    print('profile %.2f x %.2f mm ours, %.2f x %.2f mm theirs; their origin offset %+.3f, %+.3f mm'
          % (size_ours + size_theirs + (dx, dy)))
    margin = 2.0
    frame = Frame(ob[0] - margin, ob[1] - margin, ob[2] + margin, ob[3] + margin, args.resolution)
    board = frame.render_profile(parsed_ours['profile'])
    c = max(1, int(round(CELL_MM / frame.res)))
    band_cells = int(round(EDGE_BAND_MM / CELL_MM))
    board_cells = cells(board, c)
    edge_band = board_cells & ~erode(np.pad(board_cells, band_cells), 2 * band_cells + 1)[
        :board_cells.shape[0], :board_cells.shape[1]]
    failures = 0
    for key in sorted(ours):
        if key == 'profile':
            a, b = board, frame.render_profile(parsed_theirs['profile'], -dx, -dy)
        else:
            a = frame.render(parsed_ours[key]['ops'])
            b = frame.render(parsed_theirs[key]['ops'], -dx, -dy)
        lines = compare(a, b, frame, args.tolerance, edge_band)
        print('%-11s %s vs %s: %s' % (key, ours[key][0], theirs[key][0],
                                      '%d difference(s)' % len(lines) if lines else 'same'))
        for line in lines:
            print('    ' + line)
        failures += len(lines)
    lines, resized = compare_drills(our_drills, their_drills, dx, dy,
                                    args.drill_position, args.drill_tolerance)
    print('drills      %d ours vs %d theirs (%s): %s%s' % (
        len(our_drills), len(their_drills), ', '.join(their_drill_files) or 'none',
        '%d difference(s)' % len(lines) if lines else 'same',
        '; %d resized within %.2f mm (plating allowance)' % (resized, args.drill_tolerance)
        if resized else ''))
    for line in lines:
        print('    ' + line)
    failures += len(lines)
    print('RESULT: %s' % ('%d difference(s): review before confirming' % failures if failures
                          else 'no differences above tolerance'))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

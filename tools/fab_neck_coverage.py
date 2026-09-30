#!/usr/bin/env python3
"""Prove that every plotted filled region meets the minimum neck width.

Method (per copper or silkscreen Gerber layer; details in
doc/hardware/filled-neck-and-silk-text-audit-20260928.md):

1. Parse the plotted ink with the independent gerberdrc parser, but build an
   inner approximation of it: round flashes, strokes and rounded corners use
   chords inscribed in their true arcs, and stroked arcs are shrunk by their
   recorded chord error. Region arcs (G02/G03 inside G36/G37) are replaced by
   chords within 1 nm of the arc, and that deviation is added to the radius.
2. U = union of all ink on the layer (a thin region part can be widened by
   overlapping pads or tracks, so the physical ink is what is measured).
3. Thin material: E = erode(U, r_e), O = dilate(E, r_e) with r_e = (rule/2 +
   arc deviation) / cos(pi/4Q); the chord error of GEOS's Q-segment arcs is
   folded into r_e, so E lies inside the exact erosion and O is a union of
   true disks of diameter >= rule lying in the ink. Every point of every
   filled region must lie within TOLERANCE_MM of O, or in the cap of a
   convex corner with an interior angle of at least 90 degrees whose cap
   triangle and tangent disk of diameter >= rule both lie in the ink.
4. Pinches and webs: within every ink component that touches a filled
   region, the eroded set (plus the centrelines of plotted strokes at least
   the rule wide, which lie in the exact erosion) must stay connected, and no
   two holes of the component, or a hole and the outside, may merge after
   erosion. A merge or split means a disk of the rule's diameter cannot pass,
   and it is reported at the narrowest point.

An isolated, simple, orthogonal region whose exact integer scanline span
meets the rule is also accepted by the exact certificate from gerberdrc.
Every other shortfall is reported with coordinates; nothing is deferred.
"""

import argparse
import ctypes
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import sys
import tempfile

import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw/tools'))
import gerberdrc  # noqa: E402

BOARDS = ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system')
# JLCPCB PCB capabilities, Legend/silkscreen "Minimum Line Width: >=0.15mm"
# (https://jlcpcb.com/capabilities/pcb-capabilities, read 2026-09-28).
JLC_SILK_MIN_LINE_MM = 0.15
QUAD = 128                 # GEOS chords per quarter circle in erosion/dilation
TOLERANCE_MM = 5e-6        # 5 nm: numerical slack, five Gerber grid units
ARC_CHORD_MM = 1e-6        # region arcs become chords within 1 nm of the arc
ARC_DEVIATION_MM = 4e-6    # chord + nm rounding + the 2 nm radius mismatch
REPORT_LIMIT = 40


class ProofGeometry(gerberdrc.Geometry):
    """gerberdrc's GEOS engine with inner approximations and more operations."""

    def __init__(self):
        super().__init__()
        self.outward = False   # inscribed chords: every buffer is a subset
        self.sources = {}
        self.prepared = []
        self._functions = {}
        self._boundaries = {}

    def buffer(self, shape, radius):
        result = super().buffer(shape, radius)
        self.sources[result] = (shape, radius)
        return result

    def fn(self, name, result, *args):
        if name not in self._functions:
            self._functions[name] = self.call(name, result, [ctypes.c_void_p, *args])
        return self._functions[name]

    def own(self, shape, what):
        if not shape:
            raise ValueError('GEOS failed to ' + what)
        self.shapes.append(shape)
        return shape

    def styled_buffer(self, shape, distance, quad):
        return self.own(self.fn('GEOSBufferWithStyle_r', ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_double, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_double)(self.ctx, shape, distance, quad, 1, 1, 5.0),
                        'buffer ink')

    def union_all(self, shapes):
        clone = self.fn('GEOSGeom_clone_r', ctypes.c_void_p, ctypes.c_void_p)
        members = (ctypes.c_void_p * len(shapes))(*[clone(self.ctx, shape) for shape in shapes])
        collection = self.fn('GEOSGeom_createCollection_r', ctypes.c_void_p, ctypes.c_int,
                             ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint)(
                                 self.ctx, 7, members, len(shapes))
        collection = self.own(collection, 'collect ink')
        return self.own(self.fn('GEOSUnaryUnion_r', ctypes.c_void_p, ctypes.c_void_p)(
            self.ctx, collection), 'union ink')

    def binary(self, name, first, second):
        return self.own(self.fn(name, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            self.ctx, first, second), name)

    def empty(self, shape):
        return self.fn('GEOSisEmpty_r', ctypes.c_byte, ctypes.c_void_p)(self.ctx, shape) == 1

    def parts(self, shape):
        if self.empty(shape):
            return []
        kind = self.fn('GEOSGeomTypeId_r', ctypes.c_int, ctypes.c_void_p)(self.ctx, shape)
        if kind == 3:
            return [shape]
        if kind not in (6, 7):
            raise ValueError('unexpected GEOS geometry type %d' % kind)
        count = self.fn('GEOSGetNumGeometries_r', ctypes.c_int, ctypes.c_void_p)(self.ctx, shape)
        nth = self.fn('GEOSGetGeometryN_r', ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
        result = []
        for index in range(count):
            part = nth(self.ctx, shape, index)
            if self.fn('GEOSGeomTypeId_r', ctypes.c_int, ctypes.c_void_p)(self.ctx, part) != 3:
                raise ValueError('unexpected non-polygon ink part')
            result.append(part)
        return result

    def rings(self, polygon):
        """Exterior ring, then holes (internal pointers owned by polygon)."""
        exterior = self.fn('GEOSGetExteriorRing_r', ctypes.c_void_p, ctypes.c_void_p)
        count = self.fn('GEOSGetNumInteriorRings_r', ctypes.c_int, ctypes.c_void_p)
        nth = self.fn('GEOSGetInteriorRingN_r', ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
        return [exterior(self.ctx, polygon)] + [nth(self.ctx, polygon, index)
                                               for index in range(count(self.ctx, polygon))]

    def coords(self, ring):
        seq = self.fn('GEOSGeom_getCoordSeq_r', ctypes.c_void_p, ctypes.c_void_p)(self.ctx, ring)
        size = ctypes.c_uint()
        self.fn('GEOSCoordSeq_getSize_r', ctypes.c_int, ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint))(self.ctx, seq, ctypes.byref(size))
        buffer = numpy.empty((size.value, 2), dtype=numpy.float64)
        if self.fn('GEOSCoordSeq_copyToBuffer_r', ctypes.c_int, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_int, ctypes.c_int)(
                       self.ctx, seq, buffer.ctypes.data, 0, 0) == 0:
            raise ValueError('GEOS failed to copy ring coordinates')
        return buffer

    def ring_polygon(self, ring):
        clone = self.fn('GEOSGeom_clone_r', ctypes.c_void_p, ctypes.c_void_p)(self.ctx, ring)
        return self.own(self.fn('GEOSGeom_createPolygon_r', ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint)(self.ctx, clone, None, 0),
                        'make hole polygon')

    def bounds(self, shape):
        values = []
        for name in ('GEOSGeom_getXMin_r', 'GEOSGeom_getYMin_r',
                     'GEOSGeom_getXMax_r', 'GEOSGeom_getYMax_r'):
            value = ctypes.c_double()
            self.fn(name, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_double))(
                self.ctx, shape, ctypes.byref(value))
            values.append(value.value)
        return tuple(values)

    def area(self, shape):
        value = ctypes.c_double()
        self.fn('GEOSArea_r', ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_double))(
            self.ctx, shape, ctypes.byref(value))
        return value.value

    def surface_point(self, shape):
        point = self.own(self.fn('GEOSPointOnSurface_r', ctypes.c_void_p, ctypes.c_void_p)(
            self.ctx, shape), 'find a surface point')
        x, y = ctypes.c_double(), ctypes.c_double()
        self.fn('GEOSGeomGetX_r', ctypes.c_int, ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_double))(self.ctx, point, ctypes.byref(x))
        self.fn('GEOSGeomGetY_r', ctypes.c_int, ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_double))(self.ctx, point, ctypes.byref(y))
        return point, (x.value, y.value)

    def nearest(self, first, second):
        seq = self.fn('GEOSNearestPoints_r', ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            self.ctx, first, second)
        if not seq:
            raise ValueError('GEOS failed to find nearest points')
        points = []
        for index in range(2):
            x, y = ctypes.c_double(), ctypes.c_double()
            self.fn('GEOSCoordSeq_getXY_r', ctypes.c_int, ctypes.c_void_p, ctypes.c_uint,
                    ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double))(
                        self.ctx, seq, index, ctypes.byref(x), ctypes.byref(y))
            points.append((x.value, y.value))
        self.fn('GEOSCoordSeq_destroy_r', None, ctypes.c_void_p)(self.ctx, seq)
        return points

    def boundary(self, shape):
        # Geometry is immutable for this engine's lifetime. A width witness
        # must not retain another copy of the complete board boundary.
        if shape not in self._boundaries:
            self._boundaries[shape] = self.own(
                self.fn('GEOSBoundary_r', ctypes.c_void_p, ctypes.c_void_p)(
                    self.ctx, shape), 'take a boundary')
        return self._boundaries[shape]

    def prepare(self, shape):
        prepared = self.fn('GEOSPrepare_r', ctypes.c_void_p, ctypes.c_void_p)(self.ctx, shape)
        if not prepared:
            raise ValueError('GEOS failed to prepare geometry')
        self.prepared.append(prepared)
        return prepared

    def prepared_test(self, name, prepared, shape):
        result = self.fn(name, ctypes.c_byte, ctypes.c_void_p, ctypes.c_void_p)(
            self.ctx, prepared, shape)
        if result not in (0, 1):
            raise ValueError('GEOS failed ' + name)
        return result == 1

    def close(self):
        destroy = self.fn('GEOSPreparedGeom_destroy_r', None, ctypes.c_void_p)
        for prepared in self.prepared:
            destroy(self.ctx, prepared)
        super().close()
        self._boundaries.clear()


def expand_region_arcs(path, directory):
    """Copy path with region arcs replaced by chords within ARC_CHORD_MM.

    Returns (path to parse, line map to the original, whether arcs occurred).
    Chord vertices lie on the arc and are rounded to the 1 nm Gerber grid.
    """
    lines = path.read_text().splitlines()
    output, origin = [], []
    in_region, mode, position, arcs = False, 'G01', None, False
    for number, line in enumerate(lines, 1):
        text = line.strip()
        emitted = [text]
        if text == 'G36*':
            in_region = True
        elif text == 'G37*':
            in_region = False
            if mode != 'G01':
                emitted.append(mode + '*')
        elif text in ('G01*', 'G02*', 'G03*'):
            mode = text[:-1]
            if in_region:
                emitted = ['G01*']
        elif match := gerberdrc.ARC_COORD.fullmatch(text):
            target = (int(match[1]), int(match[2]))
            if in_region:
                if position is None or mode not in ('G02', 'G03'):
                    raise ValueError('%s:%d: unsupported region arc' % (path.name, number))
                arcs = True
                emitted = ['X%dY%dD01*' % point for point in
                           region_arc_chords(position, target, (int(match[3]), int(match[4])),
                                             mode, '%s:%d' % (path.name, number))]
            position = target
        elif match := gerberdrc.COORD.fullmatch(text):
            if position is not None or (match[1] is not None and match[2] is not None):
                position = (int(match[1]) if match[1] is not None else position[0],
                            int(match[2]) if match[2] is not None else position[1])
        output.extend(emitted)
        origin.extend([number] * len(emitted))
    if not arcs:
        return path, None, False
    copy = Path(directory) / path.name
    copy.write_text('\n'.join(output) + '\n')
    return copy, origin, True


def region_arc_chords(start, target, offsets, mode, where):
    """Integer-nm chord vertices (excluding start) of a Gerber G75 arc."""
    center = (start[0] + offsets[0], start[1] + offsets[1])
    radius = math.dist(start, center)
    if radius <= 0 or abs(math.dist(target, center) - radius) > 2:
        raise ValueError(where + ': invalid region arc radius')
    begin = math.atan2(start[1]-center[1], start[0]-center[0])
    finish = math.atan2(target[1]-center[1], target[0]-center[0])
    sweep = ((finish-begin) % (2*math.pi) if mode == 'G03' else
             -((begin-finish) % (2*math.pi)))
    if abs(sweep) < 1e-12:
        sweep = 2*math.pi if mode == 'G03' else -2*math.pi
    chord = ARC_CHORD_MM * 1e6          # in Gerber nm units
    step = 2 * math.acos(max(-1.0, 1 - chord/radius)) if radius > chord else math.pi
    count = max(2, math.ceil(abs(sweep) / step))
    points = [(round(center[0] + radius*math.cos(begin + sweep*i/count)),
               round(center[1] + radius*math.sin(begin + sweep*i/count)))
              for i in range(1, count)]
    return points + [target]


def corner_caps(engine, ink_prepared, vertices, box, radius):
    """Triangles of qualifying convex corners (>= 90 degrees) inside box."""
    x0, y0, x1, y1 = box
    here, before, after = vertices
    mask = ((here[:, 0] >= x0) & (here[:, 0] <= x1) &
            (here[:, 1] >= y0) & (here[:, 1] <= y1))
    caps = []
    # The tangent disk test uses an inscribed polygon whose inradius is the
    # conservative radius, so the true disk it contains is at least that big.
    outer = radius / math.cos(math.pi / (4 * QUAD)) + 1e-7
    for v, a, b in zip(here[mask], before[mask], after[mask]):
        first, second = a - v, b - v
        la, lb = numpy.hypot(*first), numpy.hypot(*second)
        if la == 0 or lb == 0:
            continue
        first, second = first / la, second / lb
        angle = math.acos(max(-1.0, min(1.0, float(first @ second))))
        if angle < math.pi/2 - 1e-9 or angle > math.pi - 1e-9:
            continue
        leg = outer / math.tan(angle / 2)
        bisector = first + second
        length = numpy.hypot(*bisector)
        if length == 0:
            continue
        bisector /= length
        center = v + bisector * (outer / math.sin(angle / 2))
        # Tangent coordinates rounded for GEOS can land infinitesimally
        # outside a diagonal edge. Move the unchanged full-size disk and
        # the cap's contact vertices 0.1 nm into the ink. Both candidates
        # must still pass strict Covers; no containment slack is allowed.
        inward = bisector * 1e-7
        center += inward
        p1, p2 = v + first * leg + inward, v + second * leg + inward
        triangle = engine.wkt('POLYGON ((%.12f %.12f, %.12f %.12f, %.12f %.12f, %.12f %.12f))' %
                              (*v, *p1, *p2, *v))
        disk = engine.styled_buffer(engine.wkt('POINT (%.12f %.12f)' % tuple(center)),
                                    outer, QUAD)
        if (engine.prepared_test('GEOSPreparedCovers_r', ink_prepared, triangle) and
                engine.prepared_test('GEOSPreparedCovers_r', ink_prepared, disk)):
            caps.append(triangle)
    return caps


def covering_corner_caps(engine, ink_prepared, vertices, box, radius):
    """Find full-size certified caps that can reach the residue box."""
    # For qualifying angles >= 90 degrees the contact-leg length is no
    # greater than outer. A corner can cover residue without its vertex
    # lying in that residue's bounding box.
    reach = radius / math.cos(math.pi / (4 * QUAD)) + 1e-7 + TOLERANCE_MM
    x0, y0, x1, y1 = box
    return corner_caps(engine, ink_prepared, vertices,
                       (x0-reach, y0-reach, x1+reach, y1+reach), radius)


def ring_vertices(engine, ink_parts):
    here, before, after = [], [], []
    for part in ink_parts:
        for ring in engine.rings(part):
            points = engine.coords(ring)[:-1]
            if len(points) < 3:
                continue
            here.append(points)
            before.append(numpy.roll(points, 1, axis=0))
            after.append(numpy.roll(points, -1, axis=0))
    if not here:
        empty = numpy.empty((0, 2))
        return empty, empty, empty
    return numpy.concatenate(here), numpy.concatenate(before), numpy.concatenate(after)


def overlaps(first, second, margin=0.0):
    return not (first[2] + margin < second[0] or second[2] + margin < first[0] or
                first[3] + margin < second[1] or second[3] + margin < first[1])


def prove_layer(path, minimum, *, silk=False):
    """Return the neck proof for every filled region of one plotted layer."""
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('positive minimum width required')
    with tempfile.TemporaryDirectory(prefix='cupc8-neck-') as directory:
        source, origin, arcs = expand_region_arcs(path, directory)
        engine = ProofGeometry()
        try:
            return _prove(engine, source, origin, arcs, minimum, silk)
        finally:
            engine.close()


def _prove(engine, source, origin, arcs, minimum, silk):
    regions = []
    objects = gerberdrc.plotted_copper(
        source, engine, require_net=not silk,
        extra_function='Legend' if silk else None, allow_empty=silk,
        minimum_track=minimum, filled_regions=regions)
    lines = [origin[line - 1] if origin else line for _, _, _, line, _ in regions]
    result = {'filled_regions': len(regions), 'rule_mm': minimum,
              'tolerance_mm': TOLERANCE_MM, 'region_arcs': arcs,
              'orthogonal_certificates': 0, 'failures': [], 'outside_region_necks': 0}
    if not regions:
        result.update(proved=0, failed_regions=[], complete_for_filled_regions=True)
        return result
    half = minimum / 2 + (ARC_DEVIATION_MM if arcs else 0)
    radius = half / math.cos(math.pi / (4 * QUAD))

    # Inner approximation: stroked arcs carry an outward allowance (overfill)
    # of chord sagitta + 1 nm; rebuffer them that much smaller than plotted.
    shapes, skeletons = [], []
    for _, shape, _ in objects:
        extra = engine.overfill.get(shape, 0.0)
        source_shape, plotted = engine.sources.get(shape, (None, None))
        if extra > 0:
            shape = engine.styled_buffer(source_shape, plotted - 2 * extra, 64)
        shapes.append(shape)
        # A stroke's centreline (or a rounded flash's core) at least half the
        # rule from its edge lies in the exact erosion; it keeps exact-rule
        # tracks connected where the conservative erosion radius removes them.
        if source_shape is not None and plotted - 2 * extra >= minimum / 2:
            skeletons.append(engine.styled_buffer(source_shape, TOLERANCE_MM, 2))
    ink = engine.union_all(shapes)
    region_shapes = [shape for _, shape, _, _, _ in regions]
    region_bounds = [engine.bounds(shape) for shape in region_shapes]
    region_union = engine.union_all(region_shapes)

    eroded = engine.styled_buffer(ink, -radius, QUAD)
    opened = engine.styled_buffer(eroded, radius, QUAD)
    covered = engine.styled_buffer(opened, TOLERANCE_MM, 8)
    ink_parts = engine.parts(ink)
    ink_prepared = engine.prepare(ink)
    failures = []

    def owners(shape, margin):
        box = engine.bounds(shape)
        return [index for index, bounds in enumerate(region_bounds)
                if overlaps(box, bounds, margin) and
                engine.distance(shape, region_shapes[index]) <= margin]

    def local_width(point, part):
        return 2 * engine.distance(point, engine.boundary(part))

    # Thin material inside the filled regions.
    residue = engine.binary('GEOSDifference_r', region_union, covered)
    if not engine.empty(residue):
        vertices = ring_vertices(engine, ink_parts)
        leftovers = []
        for part in engine.parts(residue):
            x0, y0, x1, y1 = engine.bounds(part)
            caps = covering_corner_caps(engine, ink_prepared, vertices,
                                        (x0, y0, x1, y1), radius)
            if caps:
                allowed = engine.styled_buffer(engine.union_all(caps), TOLERANCE_MM, 8)
                part = engine.binary('GEOSDifference_r', part, allowed)
            leftovers.extend(engine.parts(part))
        for part in leftovers:
            point, (x, y) = engine.surface_point(part)
            failures.append({'kind': 'thin', 'x_mm': x, 'y_mm': y,
                             'width_mm': local_width(point, ink),
                             'regions': owners(part, TOLERANCE_MM)})

    # Pinches (erosion splits a component) and webs (holes merge).
    healed = engine.union_all([eroded] + skeletons) if skeletons else eroded
    healed_parts = engine.parts(healed)
    scope = [part for part in ink_parts
             if engine.prepared_test('GEOSPreparedIntersects_r',
                                     engine.prepare(region_union), part)]
    scope_bounds = [engine.bounds(part) for part in scope]
    scope_prepared = [engine.prepare(part) for part in scope]
    members = [[] for _ in scope]
    for part in healed_parts:
        point, (x, y) = engine.surface_point(part)
        for index, bounds in enumerate(scope_bounds):
            if (bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3] and
                    engine.prepared_test('GEOSPreparedIntersects_r', scope_prepared[index], point)):
                members[index].append(part)
                break
    necks = []
    for component, pieces in zip(scope, members):
        if len(pieces) > 1:
            pieces = sorted(pieces, key=engine.area, reverse=True)
            for index, piece in enumerate(pieces[1:], 1):
                best = min((engine.nearest(piece, other) for j, other in enumerate(pieces)
                            if j != index), key=lambda pair: math.dist(*pair))
                necks.append(('pinch', component, best))
        rings = engine.rings(component)
        if len(rings) == 1:
            continue
        piece_holes = []
        for piece in pieces:
            for ring in engine.rings(piece)[1:]:
                hole = engine.ring_polygon(ring)
                piece_holes.append((engine.bounds(hole), engine.prepare(hole)))
        groups = {}
        for ring in rings[1:]:
            point, (x, y) = engine.surface_point(engine.ring_polygon(ring))
            where = next((index for index, (bounds, prepared) in enumerate(piece_holes)
                          if bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3] and
                          engine.prepared_test('GEOSPreparedIntersects_r', prepared, point)),
                         'outside')
            groups.setdefault(where, []).append(ring)
        for where, holes in groups.items():
            others = holes + ([rings[0]] if where == 'outside' else [])
            if where != 'outside' and len(holes) < 2:
                continue
            for hole in holes:
                pairs = [engine.nearest(hole, other) for other in others if other is not hole]
                if pairs:
                    necks.append(('web', component, min(pairs, key=lambda p: math.dist(*p))))
    for kind, component, (first, second) in necks:
        middle = ((first[0]+second[0])/2, (first[1]+second[1])/2)
        point = engine.wkt('POINT (%.12f %.12f)' % middle)
        owned = owners(point, radius + TOLERANCE_MM)
        if not owned:
            result['outside_region_necks'] += 1
            continue
        failures.append({'kind': kind, 'x_mm': middle[0], 'y_mm': middle[1],
                         'width_mm': (math.dist(first, second) if kind == 'web'
                                      else local_width(point, component)),
                         'regions': owned})

    # Exact certificate for isolated simple orthogonal regions (exact rule).
    certified = set()
    rule_grid = Decimal(str(minimum)) * 2000000
    for index, (_, shape, bounds, _, points) in enumerate(regions):
        if not engine.simple_hole_free_polygon(shape):
            continue
        span = gerberdrc.orthogonal_region_min_span(points)
        if span is None or span < rule_grid:
            continue
        if not any(other is not shape and overlaps(bounds, other_bounds) and
                   engine.distance(shape, other) == 0
                   for _, other, other_bounds in objects):
            certified.add(index)
    result['orthogonal_certificates'] = len(certified)
    kept = []
    for failure in failures:
        if failure['regions'] and set(failure['regions']) <= certified:
            continue
        failure['regions'] = [lines[index] for index in failure['regions']]
        for key in ('x_mm', 'y_mm', 'width_mm'):
            failure[key] = round(failure[key], 6)
        kept.append(failure)
    kept.sort(key=lambda failure: (failure['width_mm'], failure['x_mm'], failure['y_mm']))
    failed = sorted({line for failure in kept for line in failure['regions']})
    result['failure_count'] = len(kept)
    result['failures'] = kept[:REPORT_LIMIT]
    result['failed_regions'] = failed
    result['proved'] = len(regions) - len(failed)
    result['complete_for_filled_regions'] = not kept
    return result


def analyze_layer(path, minimum, *, silk=False):
    return prove_layer(Path(path), minimum, silk=silk)


def board_check(build):
    import pcbnew
    import boardevidence
    receipt = boardevidence.validate(build.name, build)
    board = pcbnew.LoadBoard(str(build / (build.name + '.kicad_pcb')))
    fab = build / 'fab'
    copper = sorted(path for path in fab.iterdir()
                    if path.suffix.lower() in ('.gtl', '.gbl', '.g1', '.g2', '.g3', '.g4'))
    silk = sorted(path for path in fab.iterdir()
                  if path.suffix.lower() in ('.gto', '.gbo'))
    if len(copper) != board.GetCopperLayerCount() or len(silk) != 2:
        raise ValueError(f'{build.name}: incomplete plotted copper or silk layer set')
    settings = board.GetDesignSettings()
    copper_min = pcbnew.ToMM(settings.m_TrackMinWidth)
    if copper_min <= 0:
        raise ValueError(f'{build.name}: positive minimum track width required')
    layers = {path.name: analyze_layer(path, copper_min) for path in copper}
    layers.update({path.name: analyze_layer(path, JLC_SILK_MIN_LINE_MM, silk=True)
                   for path in silk})
    return {'board': build.name,
            'receipt_sha256': boardevidence.digest(build / 'evidence.json'),
            'copper_rule_mm': copper_min, 'silk_line_rule_mm': JLC_SILK_MIN_LINE_MM,
            'board_min_silk_text_thickness_mm': pcbnew.ToMM(settings.m_MinSilkTextThickness),
            'layers': layers,
            'complete_for_filled_regions': all(
                row['complete_for_filled_regions'] for row in layers.values()),
            'gerber_sha256': {f'fab/{name}': receipt['artifacts'][f'fab/{name}']
                              for name in layers}}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('boards', nargs='*', choices=BOARDS, default=BOARDS)
    parser.add_argument('--require-complete', action='store_true',
                        help='exit nonzero when any filled region lacks a neck proof')
    args = parser.parse_args()
    incomplete = []
    for name in args.boards:
        result = board_check(ROOT / 'build/hw' / name)
        print(json.dumps(result), flush=True)
        if not result['complete_for_filled_regions']:
            incomplete.append(name)
    if args.require_complete and incomplete:
        raise SystemExit('filled-region neck proof failed: ' + ', '.join(incomplete))


if __name__ == '__main__':
    main()

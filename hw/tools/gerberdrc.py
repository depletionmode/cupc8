"""Independent copper clearance check over exported RS-274X/X2 Gerbers.

Only the KiCad primitives explicitly handled below are accepted. GEOS operates on
the plotted coordinates, not on pcbnew board objects or a second board export.
"""
import ctypes
import ctypes.util
from decimal import Decimal, localcontext
from fractions import Fraction
import math
from pathlib import Path
import re
from collections import defaultdict


COORD = re.compile(r'^(?:X(-?\d+))?(?:Y(-?\d+))?D(0[123])\*$')
ARC_COORD = re.compile(r'^X(-?\d+)Y(-?\d+)I(-?\d+)J(-?\d+)D01\*$')
APERTURE = re.compile(r'^%ADD(\d+)(C|R|O|RoundRect|FreePoly\d+),([^*]+)\*%$')
SELECT = re.compile(r'^D(\d+)\*$')
PROFILE_MOVE = re.compile(r'^X(-?\d+)Y(-?\d+)D02\*$')
PROFILE_DRAW = re.compile(r'^X(-?\d+)Y(-?\d+)(?:I(-?\d+)J(-?\d+))?D01\*$')
ROUND_RECT_MACRO = (
    '0 Rectangle with rounded corners*',
    '0 $1 Rounding radius*',
    '0 $2 $3 $4 $5 $6 $7 $8 $9 X,Y pos of 4 corners*',
    '0 Add a 4 corners polygon primitive as box body*',
    '4,1,4,$2,$3,$4,$5,$6,$7,$8,$9,$2,$3,0*',
    '0 Add four circle primitives for the rounded corners*',
    '1,1,$1+$1,$2,$3*', '1,1,$1+$1,$4,$5*',
    '1,1,$1+$1,$6,$7*', '1,1,$1+$1,$8,$9*',
    '0 Add four rect primitives between the rounded corners*',
    '20,1,$1+$1,$2,$3,$4,$5,0*',
    '20,1,$1+$1,$4,$5,$6,$7,0*',
    '20,1,$1+$1,$6,$7,$8,$9,0*',
    '20,1,$1+$1,$8,$9,$2,$3,0*%',
)


class Geometry:
    def __init__(self):
        library = ctypes.util.find_library('geos_c')
        if not library:
            raise ValueError('GEOS C library is required for Gerber geometry DRC')
        self.lib = ctypes.CDLL(library)
        self.ctx = self.call('GEOS_init_r', ctypes.c_void_p, [])()
        if not self.ctx:
            raise ValueError('cannot initialize GEOS')
        self.reader = self.call('GEOSWKTReader_create_r', ctypes.c_void_p, [ctypes.c_void_p])(self.ctx)
        self.shapes = []
        self.overfill = {}
        self.circles = {}
        self.obrounds = {}
        self.flashes = {}
        self.repaired = set()
        self.outward = True

    def call(self, name, result, args):
        function = getattr(self.lib, name)
        function.restype = result
        function.argtypes = args
        return function

    def wkt(self, value, repair=False):
        shape = self.call('GEOSWKTReader_read_r', ctypes.c_void_p,
                          [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p])(
                              self.ctx, self.reader, value.encode())
        if not shape:
            raise ValueError('invalid Gerber geometry: ' + value[:100])
        self.shapes.append(shape)
        valid = self.call('GEOSisValid_r', ctypes.c_byte, [ctypes.c_void_p, ctypes.c_void_p])(
            self.ctx, shape)
        if valid != 1 and repair:
            shape = self.call('GEOSMakeValid_r', ctypes.c_void_p,
                              [ctypes.c_void_p, ctypes.c_void_p])(self.ctx, shape)
            if shape:
                self.shapes.append(shape)
                self.repaired.add(shape)
                valid = self.call('GEOSisValid_r', ctypes.c_byte,
                                  [ctypes.c_void_p, ctypes.c_void_p])(self.ctx, shape)
        empty = self.call('GEOSisEmpty_r', ctypes.c_byte, [ctypes.c_void_p, ctypes.c_void_p])(
            self.ctx, shape)
        if valid != 1 or empty != 0:
            raise ValueError('invalid or empty Gerber geometry: ' + value[:100])
        return shape

    def buffer(self, shape, radius):
        # GEOS emits 64 chords per quadrant. Its ordinary buffer polygon is
        # inscribed in the requested circular arc and can overstate clearance.
        # At each chord midpoint the inradius is R*cos(pi/256); expanding R
        # by its reciprocal makes this approximation a superset of the plot.
        conservative_radius = radius / math.cos(math.pi / 256) if self.outward else radius
        result = self.call('GEOSBuffer_r', ctypes.c_void_p,
                           [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_int])(
                               self.ctx, shape, conservative_radius, 64)
        if not result:
            raise ValueError('GEOS failed to buffer plotted geometry')
        self.shapes.append(result)
        self.overfill[result] = conservative_radius - radius
        return result

    def distance(self, first, second):
        value = ctypes.c_double()
        result = self.call('GEOSDistance_r', ctypes.c_int,
                           [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)])(
                               self.ctx, first, second, ctypes.byref(value))
        if result != 1 or not math.isfinite(value.value):
            raise ValueError('GEOS failed to measure Gerber clearance')
        return value.value

    def circle_distance(self, first, second):
        """Exact decimal clearance of two circular flashes, if both qualify."""
        if first not in self.circles or second not in self.circles:
            return None
        x0, y0, d0 = self.circles[first]
        x1, y1, d1 = self.circles[second]
        with localcontext() as context:
            context.prec = 50
            dx = Decimal(x0-x1) / Decimal(1000000)
            dy = Decimal(y0-y1) / Decimal(1000000)
            return (dx*dx + dy*dy).sqrt() - (Decimal(str(d0)) + Decimal(str(d1))) / 2

    def covers(self, outer, inner):
        result = self.call('GEOSCovers_r', ctypes.c_byte,
                           [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p])(
                               self.ctx, outer, inner)
        if result not in (0, 1):
            raise ValueError('GEOS failed to compare plotted coverage')
        return result == 1

    def equals(self, first, second):
        result = self.call('GEOSEquals_r', ctypes.c_byte,
                           [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p])(
                               self.ctx, first, second)
        if result not in (0, 1):
            raise ValueError('GEOS failed to compare plotted shapes')
        return result == 1

    def union(self, first, second):
        result = self.call('GEOSUnion_r', ctypes.c_void_p,
                           [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p])(
                               self.ctx, first, second)
        if not result:
            raise ValueError('GEOS failed to union plotted openings')
        self.shapes.append(result)
        return result

    def simple_hole_free_polygon(self, shape):
        """Whether a filled region retained one valid polygon without holes."""
        if shape in self.repaired:
            return False
        kind = self.call('GEOSGeomTypeId_r', ctypes.c_int,
                         [ctypes.c_void_p, ctypes.c_void_p])(self.ctx, shape)
        if kind != 3:
            return False
        holes = self.call('GEOSGetNumInteriorRings_r', ctypes.c_int,
                          [ctypes.c_void_p, ctypes.c_void_p])(self.ctx, shape)
        if holes < 0:
            raise ValueError('GEOS failed to inspect filled-region holes')
        return holes == 0

    def close(self):
        destroy = self.call('GEOSGeom_destroy_r', None, [ctypes.c_void_p, ctypes.c_void_p])
        for shape in self.shapes:
            destroy(self.ctx, shape)
        self.call('GEOSWKTReader_destroy_r', None, [ctypes.c_void_p, ctypes.c_void_p])(
            self.ctx, self.reader)
        self.call('GEOS_finish_r', None, [ctypes.c_void_p])(self.ctx)


def polygon(points):
    if len(points) < 3:
        raise ValueError('Gerber region has fewer than three corners')
    if points[-1] != points[0]:
        points = points + [points[0]]
    return 'POLYGON ((' + ', '.join('%.9f %.9f' % point for point in points) + '))'


def arc_points(start, target, offsets, mode):
    center = (start[0]+offsets[0], start[1]+offsets[1])
    radius = math.dist(start, center)
    if radius <= 0 or abs(math.dist(target, center)-radius) > .000002:
        raise ValueError('invalid Gerber arc radius')
    begin = math.atan2(start[1]-center[1], start[0]-center[0])
    finish = math.atan2(target[1]-center[1], target[0]-center[0])
    sweep = ((finish-begin) % (2*math.pi) if mode == 'G03' else
             -((begin-finish) % (2*math.pi)))
    if abs(sweep) < 1e-12:
        sweep = 2*math.pi if mode == 'G03' else -2*math.pi
    count = max(2, math.ceil(abs(sweep)*radius/.01))
    points = [(center[0]+radius*math.cos(begin+sweep*i/count),
               center[1]+radius*math.sin(begin+sweep*i/count)) for i in range(count+1)]
    points[0], points[-1] = start, target
    sagitta = radius * (1-math.cos(abs(sweep)/(2*count)))
    return points, sagitta


def plotted_copper(path, geometry, minimum_track=None, require_net=True, features=None,
                   extra_function=None, allow_empty=False, filled_regions=None):
    """Return (net, GEOS shape, bounds) for every supported dark operation."""
    lines = path.read_text().splitlines()
    apertures = {}
    current = None
    position = None
    net = None
    region = None
    result = []
    seen_format = seen_units = seen_end = False
    file_polarity = None
    file_function = None
    macro = None
    macro_name = None
    macro_defined = False
    free_polys = {}
    aperture_function = None
    mode = 'G01'

    def add(shape, bounds, flash_function=None, at=None):
        if require_net and net is None:
            raise ValueError('%s: copper geometry without TO.N net' % path.name)
        result.append((net, shape, bounds))
        if features is not None and flash_function is not None:
            features.append((flash_function, at, net, shape, bounds))

    for number, line in enumerate(lines, 1):
        line = line.strip()
        if macro is not None:
            macro.append(line)
            if line.endswith('*%'):
                if macro_name == 'RoundRect':
                    if tuple(macro) != ROUND_RECT_MACRO:
                        raise ValueError('%s: unsupported RoundRect macro definition' % path.name)
                    macro_defined = True
                elif re.fullmatch(r'FreePoly\d+', macro_name) and len(macro) == 2 and macro[1] == '$1*%':
                    parts = macro[0].rstrip('*').split(',')
                    if len(parts) < 10 or parts[:2] != ['4', '1'] or parts[-1] != '':
                        raise ValueError('%s: unsupported FreePoly macro primitive' % path.name)
                    try:
                        count = int(parts[2])
                        values = [float(value) for value in parts[3:-1]]
                    except ValueError as error:
                        raise ValueError('%s: invalid FreePoly coordinates' % path.name) from error
                    if (count < 4 or len(values) not in (count * 2, (count + 1) * 2) or
                            any(not math.isfinite(value) for value in values)):
                        raise ValueError('%s: invalid FreePoly vertex count' % path.name)
                    points = list(zip(values[::2], values[1::2]))
                    # KiCad 10 repeats the closing point twice in this macro.
                    if len(points) == count + 1:
                        if points[-2] != points[0] or points[-1] != points[0]:
                            raise ValueError('%s: invalid FreePoly closure' % path.name)
                        points.pop()
                    if points[0] != points[-1] or len(set(points[:-1])) < 3:
                        raise ValueError('%s: FreePoly polygon is not closed' % path.name)
                    free_polys[macro_name] = points
                else:
                    raise ValueError('%s: unsupported aperture macro definition' % path.name)
                macro = None
                macro_name = None
            continue
        if line == '%FSLAX46Y46*%':
            seen_format = True
        elif line == '%MOMM*%':
            seen_units = True
        elif line.startswith('%AM'):
            name = line[3:-1] if line.endswith('*') else ''
            if name != 'RoundRect' and not re.fullmatch(r'FreePoly\d+', name):
                raise ValueError('%s:%d: unsupported aperture macro' % (path.name, number))
            macro_name = name
            macro = []
        elif match := APERTURE.fullmatch(line):
            params = tuple(float(x) for x in match[3].split('X'))
            kind = match[2]
            if kind == 'RoundRect' and not macro_defined:
                raise ValueError('%s:%d: undefined RoundRect macro' % (path.name, number))
            if kind.startswith('FreePoly') and (kind not in free_polys or len(params) != 1 or params[0] != 0):
                raise ValueError('%s:%d: unsupported FreePoly aperture rotation' % (path.name, number))
            if (kind == 'C' and len(params) != 1 or kind in ('R', 'O') and len(params) != 2 or
                    kind == 'RoundRect' and len(params) != 10 or
                    any(not math.isfinite(x) for x in params) or
                    any(x < 0 if kind == 'C' and extra_function == 'Legend' else
                        False if kind.startswith('FreePoly') else x <= 0
                        for x in params[:1 if kind not in ('R', 'O') else 2])):
                raise ValueError('%s:%d: unsupported aperture dimensions' % (path.name, number))
            apertures[int(match[1])] = (kind, params, aperture_function)
        elif line.startswith('%TA.AperFunction,') and line.endswith('*%'):
            aperture_function = line[len('%TA.AperFunction,'):-2].split(',')[0]
        elif line.startswith('%TO.N,') and line.endswith('*%'):
            net = line[6:-2]
            if not net:
                raise ValueError('%s:%d: empty net attribute' % (path.name, number))
        elif line == '%TD*%' or line == '%TD.N*%':
            net = None
            if line == '%TD*%':
                aperture_function = None
        elif line == '%TD.AperFunction*%':
            aperture_function = None
        elif line == '%LPD*%':
            pass
        elif line.startswith('%TF.FileFunction,'):
            file_function = line[len('%TF.FileFunction,'):].split(',')[0]
        elif line.startswith('%TF.FilePolarity,'):
            file_polarity = line
            expected_polarity = ('%TF.FilePolarity,Negative*%' if not require_net and
                                 extra_function is None else '%TF.FilePolarity,Positive*%')
            if line != expected_polarity:
                raise ValueError('%s:%d: unsupported file polarity' % (path.name, number))
        elif line == 'G36*':
            if region is not None:
                raise ValueError('%s:%d: nested region' % (path.name, number))
            region = []
        elif line == 'G37*':
            if region is None:
                raise ValueError('%s:%d: region end without start' % (path.name, number))
            xs, ys = zip(*region)
            bounds = (min(xs), min(ys), max(xs), max(ys))
            shape = geometry.wkt(polygon(region), repair=True)
            add(shape, bounds)
            if filled_regions is not None:
                filled_regions.append((net, shape, bounds, number, tuple(region)))
            region = None
        elif line in ('G01*', 'G02*', 'G03*'):
            mode = line[:-1]
        elif line == 'G75*':
            pass
        elif match := SELECT.fullmatch(line):
            current = int(match[1])
            if current not in apertures:
                raise ValueError('%s:%d: undefined aperture' % (path.name, number))
        elif match := ARC_COORD.fullmatch(line):
            if region is not None or position is None or current is None or mode not in ('G02', 'G03'):
                raise ValueError('%s:%d: unsupported arc context' % (path.name, number))
            kind, params, _ = apertures[current]
            if kind != 'C' or params[0] <= 0:
                raise ValueError('%s:%d: unsupported arc aperture' % (path.name, number))
            if minimum_track is not None and params[0] < minimum_track:
                raise ValueError('%s:%d: plotted trace width %.6f mm < %.6f mm' %
                                 (path.name, number, params[0], minimum_track))
            target = (int(match[1])/1e6, int(match[2])/1e6)
            points, sagitta = arc_points(position, target,
                                         (int(match[3])/1e6, int(match[4])/1e6), mode)
            line_shape = geometry.wkt('LINESTRING (' + ', '.join('%.9f %.9f' % p for p in points) + ')')
            shape = geometry.buffer(line_shape, params[0]/2 + sagitta + .000001)
            engine_error = sagitta + .000001
            geometry.overfill[shape] += engine_error
            xs, ys = zip(*points)
            radius = params[0]/2 + sagitta + .000001
            add(shape, (min(xs)-radius,min(ys)-radius,max(xs)+radius,max(ys)+radius))
            position = target
        elif match := COORD.fullmatch(line):
            if not seen_format or not seen_units:
                raise ValueError('%s:%d: coordinate before supported format' % (path.name, number))
            if match[1] is None and match[2] is None:
                raise ValueError('%s:%d: coordinate missing X and Y' % (path.name, number))
            x = int(match[1]) / 1e6 if match[1] is not None else position[0] if position else None
            y = int(match[2]) / 1e6 if match[2] is not None else position[1] if position else None
            if x is None or y is None:
                raise ValueError('%s:%d: incomplete first coordinate' % (path.name, number))
            target = (x, y)
            operation = match[3]
            if region is not None:
                if operation == '02':
                    if region:
                        raise ValueError('%s:%d: multiple region contours unsupported' % (path.name, number))
                    region.append(target)
                elif operation == '01':
                    region.append(target)
                else:
                    raise ValueError('%s:%d: flash in region' % (path.name, number))
            elif operation != '02':
                if current is None:
                    raise ValueError('%s:%d: drawing before aperture selection' % (path.name, number))
                kind, params, function = apertures[current]
                if operation == '01':
                    if position is None or kind != 'C' or params[0] <= 0 or mode != 'G01':
                        raise ValueError('%s:%d: unsupported stroked aperture' % (path.name, number))
                    if minimum_track is not None and params[0] < minimum_track:
                        raise ValueError('%s:%d: plotted trace width %.6f mm < %.6f mm' %
                                         (path.name, number, params[0], minimum_track))
                    radius = params[0] / 2
                    shape = geometry.buffer(geometry.wkt('LINESTRING (%.9f %.9f, %.9f %.9f)' %
                                                         (*position, *target)), radius)
                    bounds = (min(x, position[0])-radius, min(y, position[1])-radius,
                              max(x, position[0])+radius, max(y, position[1])+radius)
                elif kind == 'C':
                    if params[0] <= 0:
                        raise ValueError('%s:%d: zero-size flash aperture' % (path.name, number))
                    radius = params[0] / 2
                    shape = geometry.buffer(geometry.wkt('POINT (%.9f %.9f)' % target), radius)
                    geometry.circles[shape] = (round(x*1e6), round(y*1e6), params[0])
                    bounds = (x-radius, y-radius, x+radius, y+radius)
                elif kind == 'R':
                    rx, ry = (p/2 for p in params)
                    shape = geometry.wkt(polygon([(x-rx,y-ry),(x+rx,y-ry),
                                                  (x+rx,y+ry),(x-rx,y+ry)]))
                    bounds = (x-rx,y-ry,x+rx,y+ry)
                elif kind == 'O':
                    width, height = params
                    radius = min(width, height) / 2
                    if width >= height:
                        ends = [(x-width/2+radius,y), (x+width/2-radius,y)]
                    else:
                        ends = [(x,y-height/2+radius), (x,y+height/2-radius)]
                    if ends[0] == ends[1]:
                        shape = geometry.buffer(geometry.wkt('POINT (%.9f %.9f)' % target), radius)
                    else:
                        shape = geometry.buffer(geometry.wkt('LINESTRING (%.9f %.9f, %.9f %.9f)' %
                                                             (*ends[0], *ends[1])), radius)
                    geometry.obrounds[shape] = (round(x*1e6), round(y*1e6), width, height)
                    bounds = (x-width/2,y-height/2,x+width/2,y+height/2)
                elif kind.startswith('FreePoly'):
                    points = [(x+px, y+py) for px, py in free_polys[kind]]
                    shape = geometry.wkt(polygon(points))
                    xs, ys = zip(*points)
                    bounds = (min(xs), min(ys), max(xs), max(ys))
                else:
                    radius = params[0]
                    corners = [(x+params[i], y+params[i+1]) for i in (1,3,5,7)]
                    center = (sum(px for px, _ in corners)/4, sum(py for _, py in corners)/4)
                    corners.sort(key=lambda point: math.atan2(point[1]-center[1], point[0]-center[0]))
                    shape = geometry.buffer(geometry.wkt(polygon(corners)), radius)
                    xs, ys = zip(*corners)
                    bounds = (min(xs)-radius,min(ys)-radius,max(xs)+radius,max(ys)+radius)
                if operation == '03':
                    definition = (tuple(free_polys[kind]) if kind.startswith('FreePoly')
                                  else params)
                    geometry.flashes[shape] = (round(x*1e6), round(y*1e6),
                                               'FreePoly' if kind.startswith('FreePoly') else kind,
                                               definition)
                add(shape, bounds, function if operation == '03' else None, target)
            position = target
        elif line == 'M02*':
            seen_end = True
            if number != len(lines):
                raise ValueError('%s:%d: commands after end marker' % (path.name, number))
        elif (not line or line.startswith('G04 ') or
              line.startswith(('%TF.', '%TA.', '%TO.P,', '%TO.C,', '%TD.AperFunction')) or
              line == '%TD.P*%'):
            pass
        else:
            raise ValueError('%s:%d: unsupported Gerber command %s' % (path.name, number, line))
    expected_function = extra_function or 'Soldermask'
    expected_polarity = ('%TF.FilePolarity,Negative*%' if not require_net and
                         extra_function is None else '%TF.FilePolarity,Positive*%')
    if (macro is not None or region is not None or not seen_end or not seen_format or
            not seen_units or not result and not allow_empty or not require_net and
            (file_polarity != expected_polarity or file_function != expected_function) or
            require_net and (file_polarity not in (None, expected_polarity) or
                             file_function not in (None, 'Copper'))):
        raise ValueError('%s: incomplete or empty copper Gerber' % path.name)
    return result


def check_mask(paths, minimum):
    """Check positive mask webs between distinct plotted openings."""
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('board has no positive solder-mask web rule')
    engine = Geometry()
    try:
        count = 0
        for path in paths:
            openings = plotted_copper(Path(path), engine, require_net=False)
            for index, (_, shape, (x0,y0,x1,y1)) in enumerate(openings):
                for _, other, (a0,b0,a1,b1) in openings[:index]:
                    if x0-a1 >= minimum or a0-x1 >= minimum or y0-b1 >= minimum or b0-y1 >= minimum:
                        continue
                    distance = engine.distance(shape, other)
                    # Overlapping openings merge; there is no mask web between them.
                    if 0 < distance < minimum:
                        raise ValueError('%s: solder-mask web %.6f mm < %.6f mm' %
                                         (Path(path).name, distance, minimum))
                count += 1
        return count
    finally:
        engine.close()


def via_flash_diameters(path):
    """Read X2 ViaPad aperture flashes as (position, copper diameter)."""
    path = Path(path)
    apertures = {}
    via_function = False
    current = None
    flashes = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line == '%TA.AperFunction,ViaPad*%':
            via_function = True
        elif line.startswith('%TA.AperFunction,') or line in ('%TD*%', '%TD.AperFunction*%'):
            via_function = False
        elif match := APERTURE.fullmatch(line):
            if via_function:
                if match[2] != 'C':
                    raise ValueError('%s:%d: unsupported noncircular via aperture' % (path.name, number))
                apertures[int(match[1])] = float(match[3])
        elif match := SELECT.fullmatch(line):
            current = int(match[1])
        elif match := COORD.fullmatch(line):
            if match[3] == '03' and current in apertures:
                if match[1] is None or match[2] is None:
                    raise ValueError('%s:%d: incomplete via flash coordinate' % (path.name, number))
                point = (int(match[1])/1e6, int(match[2])/1e6)
                flashes.setdefault(point, []).append(apertures[current])
    return flashes


def check_via_annular(board, paths, minimum):
    """Require every through via's plotted pad on every copper layer to cover its drill."""
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('board has no positive via annular-ring rule')
    import kicadgen
    tree = kicadgen.parse(Path(board.GetFileName()).read_text())
    vias = {}
    for via in kicadgen.find(tree, 'via'):
        at = kicadgen.find1(via, 'at')
        drill = kicadgen.find1(via, 'drill')
        layers = kicadgen.find1(via, 'layers')
        if (at is None or len(at) != 3 or drill is None or len(drill) != 2 or
                layers is None or layers[1:] != ['F.Cu', 'B.Cu']):
            raise ValueError('unsupported blind, buried, or malformed via for annular check')
        point = (float(at[1]), -float(at[2]))
        if point in vias:
            raise ValueError('coincident vias require separate annular validation')
        vias[point] = float(drill[1])
    if not vias:
        raise ValueError('no vias available for annular check')
    count = 0
    for path in paths:
        flashes = via_flash_diameters(path)
        extra = set(flashes) - set(vias)
        missing = set(vias) - set(flashes)
        if extra or missing:
            raise ValueError('%s: ViaPad flash mismatch: missing %s; extra %s' %
                             (Path(path).name, sorted(missing)[:3], sorted(extra)[:3]))
        for point, drill in vias.items():
            if len(flashes[point]) != 1:
                raise ValueError('%s: duplicate ViaPad flash at %s' % (Path(path).name, point))
            ring = (flashes[point][0] - drill) / 2
            if ring < minimum:
                raise ValueError('%s: via annular ring %.6f mm < %.6f mm at %s' %
                                 (Path(path).name, ring, minimum, point))
            count += 1
    return count


def check_pth_annular(board, paths, minimum):
    """Check plotted ComponentPad copper around every plated pad drill."""
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('no positive PTH annular-ring requirement')
    import pcbnew
    pads = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                continue
            drill = pad.GetDrillSize()
            if drill.x <= 0 or drill.y <= 0:
                raise ValueError('%s: plated pad without drill' % footprint.GetReference())
            center = (pcbnew.ToMM(pad.GetPosition().x), -pcbnew.ToMM(pad.GetPosition().y))
            pads.append((footprint.GetReference(), pad, center))
    engine = Geometry()
    try:
        holes = {}
        for ref, pad, center in pads:
            drill = pad.GetDrillSize()
            dx, dy = pcbnew.ToMM(drill.x), pcbnew.ToMM(drill.y)
            if dx == dy:
                primitive = engine.wkt('POINT (%.9f %.9f)' % center)
                radius = dx/2 + minimum
            else:
                half = abs(dx-dy)/2
                angle = math.radians(pad.GetOrientationDegrees())
                direction = ((math.cos(angle), math.sin(angle)) if dx > dy
                             else (math.sin(angle), -math.cos(angle)))
                offset = (half*direction[0], half*direction[1])
                a = (center[0]-offset[0], center[1]-offset[1])
                b = (center[0]+offset[0], center[1]+offset[1])
                primitive = engine.wkt('LINESTRING (%.9f %.9f, %.9f %.9f)' % (*a, *b))
                radius = min(dx,dy)/2 + minimum
            holes[(ref, center)] = engine.buffer(primitive, radius)
        count = 0
        for path in paths:
            features = []
            engine.outward = False  # pad polygon lies inside the true plotted flash
            plotted_copper(Path(path), engine, features=features)
            engine.outward = True   # required drill clearance encloses the true drill
            component = {}
            for function, point, net, shape, _ in features:
                if function == 'ComponentPad':
                    component.setdefault(point, []).append(shape)
            for ref, pad, center in pads:
                shapes = component.get(center, ())
                if len(shapes) != 1:
                    raise ValueError('%s: expected one ComponentPad flash at %s (%s)' %
                                     (Path(path).name, center, ref))
                # Circular and axis-aligned obround flashes have exact
                # dimensions in the aperture definition. Use them directly
                # at a boundary rule; polygonized GEOS buffers otherwise
                # report a false sub-minimum annulus by tens of nanometres.
                exact = None
                drill = pad.GetDrillSize()
                dx, dy = pcbnew.ToMM(drill.x), pcbnew.ToMM(drill.y)
                origin = (round(center[0]*1e6), round(center[1]*1e6))
                if dx == dy and shapes[0] in engine.circles:
                    px, py, diameter = engine.circles[shapes[0]]
                    if (px, py) == origin:
                        exact = (Decimal(str(diameter)) - Decimal(str(dx))) / 2
                elif dx != dy and shapes[0] in engine.obrounds:
                    px, py, width, height = engine.obrounds[shapes[0]]
                    angle = math.radians(pad.GetOrientationDegrees())
                    direction = ((math.cos(angle), math.sin(angle)) if dx > dy
                                 else (math.sin(angle), -math.cos(angle)))
                    horizontal = abs(direction[0]) > 1 - 1e-9
                    vertical = abs(direction[1]) > 1 - 1e-9
                    if ((px, py) == origin and width != height and
                            ((width > height and horizontal) or
                             (height > width and vertical))):
                        across = (Decimal(str(min(width, height))) - Decimal(str(min(dx, dy)))) / 2
                        along = (Decimal(str(max(width, height))) - Decimal(str(max(dx, dy)))) / 2
                        exact = min(across, along)
                if exact is not None:
                    if exact < Decimal(str(minimum)):
                        raise ValueError('%s: PTH annular ring %s mm < %.3f mm at %s (%s)' %
                                         (Path(path).name, exact, minimum, center, ref))
                    count += 1
                    continue
                if not engine.covers(shapes[0], holes[(ref, center)]):
                    raise ValueError('%s: PTH annular ring indeterminate or below %.3f mm at %s (%s); '
                                     'unsupported exact pad/drill geometry' %
                                     (Path(path).name, minimum, center, ref))
                count += 1
        return count
    finally:
        engine.close()


def check_mask_alignment(copper_path, mask_path):
    """Require plotted openings to expose outer-layer component and connector pads."""
    engine = Geometry()
    try:
        features = []
        plotted_copper(Path(copper_path), engine, features=features)
        engine.outward = False  # inscribed opening, compared with outer copper bound
        openings = plotted_copper(Path(mask_path), engine, require_net=False)
        count = 0
        exposed_functions = {'SMDPad', 'ComponentPad', 'ConnectorPad', 'HeatsinkPad'}
        uncertain_geometry = None
        for function, point, net, copper, (x0,y0,x1,y1) in features:
            if function not in exposed_functions:
                continue
            covering = None
            identical = False
            for _, opening, (a0,b0,a1,b1) in openings:
                if x0 > a1 or a0 > x1 or y0 > b1 or b0 > y1:
                    continue
                if (engine.equals(opening, copper) or
                        (copper in engine.flashes and
                         engine.flashes.get(opening) == engine.flashes[copper])):
                    identical = True
                    break
                covering = opening if covering is None else engine.union(covering, opening)
            if identical:
                count += 1
                continue
            if covering is None or not engine.covers(covering, copper):
                if uncertain_geometry is None:
                    inner_features = []
                    engine.outward = False
                    plotted_copper(Path(copper_path), engine, features=inner_features)
                    engine.outward = True
                    outer_openings = plotted_copper(Path(mask_path), engine, require_net=False)
                    uncertain_geometry = (inner_features, outer_openings)
                inner_features, outer_openings = uncertain_geometry
                inner = next((shape for kind, at, label, shape, _ in inner_features
                              if kind == function and at == point and label == net), None)
                loose_covering = None
                for _, opening, (a0,b0,a1,b1) in outer_openings:
                    if x0 > a1 or a0 > x1 or y0 > b1 or b0 > y1:
                        continue
                    loose_covering = opening if loose_covering is None else engine.union(loose_covering, opening)
                # An identical Gerber primitive on copper and mask has the
                # same exact boundary; inner/outer tessellation is irrelevant.
                if loose_covering is not None and engine.equals(loose_covering, copper):
                    count += 1
                    continue
                if inner is not None and loose_covering is not None and engine.covers(loose_covering, inner):
                    raise ValueError('%s: mask-to-copper coverage indeterminate at %s %s pad %s '
                                     '(equal or near-equal plotted boundaries)' %
                                     (Path(mask_path).name, net, function, point))
                raise ValueError('%s: mask opening does not cover %s %s pad at %s' %
                                 (Path(mask_path).name, net, function, point))
            count += 1
        if not count:
            raise ValueError('%s: no exposed copper pads found for mask check' % Path(copper_path).name)
        return count
    finally:
        engine.close()


def check_paste_registration(copper_path, mask_path, paste_path):
    """Require each plotted paste deposit to stay inside pad copper and mask."""
    engine = Geometry()
    try:
        engine.outward = False
        pad_features = []
        plotted_copper(Path(copper_path), engine, features=pad_features)
        pads = [(shape, bounds) for function, _, _, shape, bounds in pad_features
                if function in ('SMDPad', 'HeatsinkPad')]
        openings = [(shape, bounds) for _, shape, bounds in
                    plotted_copper(Path(mask_path), engine, require_net=False)]
        engine.outward = True
        deposits = plotted_copper(Path(paste_path), engine, require_net=False,
                                  extra_function='Paste', allow_empty=True)

        def covered(shape, bounds, candidates):
            x0,y0,x1,y1 = bounds
            union = None
            for other, (a0,b0,a1,b1) in candidates:
                if x0 > a1 or a0 > x1 or y0 > b1 or b0 > y1:
                    continue
                union = other if union is None else engine.union(union, other)
            return union is not None and engine.covers(union, shape)

        def equal_candidate(shape, bounds, candidates):
            x0,y0,x1,y1 = bounds
            return any(engine.equals(shape, other) for other, (a0,b0,a1,b1) in candidates
                       if not (x0 > a1 or a0 > x1 or y0 > b1 or b0 > y1))

        loose = None
        for index, (_, deposit, bounds) in enumerate(deposits):
            for label, candidates in (('SMD copper', pads), ('mask opening', openings)):
                if covered(deposit, bounds, candidates):
                    continue
                if loose is None:
                    engine.outward = True
                    outer_features = []
                    plotted_copper(Path(copper_path), engine, features=outer_features)
                    outer_pads = [(shape, bbox) for function, _, _, shape, bbox in outer_features
                                  if function in ('SMDPad', 'HeatsinkPad')]
                    outer_mask = [(shape, bbox) for _, shape, bbox in
                                  plotted_copper(Path(mask_path), engine, require_net=False)]
                    engine.outward = False
                    inner_paste = plotted_copper(Path(paste_path), engine, require_net=False,
                                                 extra_function='Paste', allow_empty=True)
                    loose = (outer_pads, outer_mask, inner_paste)
                outer_pads, outer_mask, inner_paste = loose
                inner = inner_paste[index][1]
                outer = outer_pads if label == 'SMD copper' else outer_mask
                if equal_candidate(deposit, bounds, outer):
                    continue
                if covered(inner, bounds, outer):
                    raise ValueError('%s: paste-to-%s registration indeterminate at %s '
                                     '(equal or near-equal plotted boundaries)' %
                                     (Path(paste_path).name, label, bounds))
                raise ValueError('%s: paste deposit outside %s at %s' %
                                 (Path(paste_path).name, label, bounds))
        return len(deposits)
    finally:
        engine.close()


def check_isolated_filled_width(path, geometry, objects, filled_regions, minimum):
    """Reject a filled island whose entire plotted width is below the rule.

    A narrow region touching another shape of the same net (or any silk ink)
    can form a wider combined shape. The orthogonal scanline check below
    catches a subset of interior necks; the general union and holes remain
    at the final incomplete-coverage gate.
    """
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('no positive filled-ink width requirement')
    rule_um = Decimal(str(minimum)) * 1000000
    for net, shape, (x0, y0, x1, y1), line, _ in filled_regions:
        width_um = round(min(x1-x0, y1-y0) * 1000000)
        if width_um >= rule_um:
            continue
        for other_net, other, (a0, b0, a1, b1) in objects:
            if other == shape or other_net != net:
                continue
            if x1 < a0 or a1 < x0 or y1 < b0 or b1 < y0:
                continue
            if geometry.distance(shape, other) == 0:
                break
        else:
            raise ValueError('%s:%d: isolated filled region width %.6f mm < %.6f mm' %
                             (Path(path).name, line, width_um/1000000, minimum))


def orthogonal_regions_min_span(contours, measured_count=None):
    """Exact minimum span of a filled union on the 0.5 um Gerber grid.

    Between consecutive vertex coordinates an orthogonal polygon's scanline
    intersections are constant. Alternating pairs of crossed edges bound
    filled intervals. Merge intervals from all contours before measuring;
    only intervals containing one of the first `measured_count` filled regions
    count. Later contours may be rectangular flashes that widen the region,
    but a thin pad-only tongue is not a filled-region violation. Nonorthogonal
    contours and excessive complexity are deferred.
    """
    if measured_count is None:
        measured_count = len(contours)
    if sum(len(points) for points in contours) > 2000:
        return None  # bound the quadratic scan; the final gate retains this case
    outlines = []
    for points in contours:
        vertices = [(round(x * 2000000), round(y * 2000000)) for x, y in points]
        if vertices[0] != vertices[-1]:
            vertices.append(vertices[0])
        edges = list(zip(vertices, vertices[1:]))
        if any(a == b or a[0] != b[0] and a[1] != b[1] for a, b in edges):
            return None
        outlines.append((vertices, edges))
    best = None
    for axis in (0, 1):
        coordinates = sorted({point[axis] for vertices, _ in outlines for point in vertices})
        for low, high in zip(coordinates, coordinates[1:]):
            midpoint2 = low + high  # twice the half-grid scanline coordinate
            spans = []
            for index, (_, edges) in enumerate(outlines):
                crossings = []
                for a, b in edges:
                    if (a[1-axis] == b[1-axis] and
                            min(2*a[axis], 2*b[axis]) < midpoint2 < max(2*a[axis], 2*b[axis])):
                        crossings.append(a[1-axis])
                crossings.sort()
                if len(crossings) % 2:
                    return None  # unsupported topology, never claim a pass
                spans.extend((start, end, index < measured_count)
                             for start, end in zip(crossings[::2], crossings[1::2]))
            merged = []
            for start, end, measured in sorted(spans):
                if end <= start:
                    return None
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]),
                                  merged[-1][2] or measured)
                else:
                    merged.append((start, end, measured))
            for start, end, measured in merged:
                if not measured:
                    continue
                width = end - start
                best = width if best is None else min(best, width)
    return best


def orthogonal_region_min_span(points):
    return orthogonal_regions_min_span((points,))


def polygon_scanline_witness(points, minimum):
    """Find an exact interior neck inside a simple, hole-free polygon.

    Cross-section width between polygon vertices is affine: a sub-rule span
    missed at the slab midpoint must lie near an endpoint. Sample rationally
    between that endpoint and the exact rule crossing. A thin section must
    have overlapping wide sections in the neighboring slabs, excluding a
    terminal tip. Other dark ink and holes are excluded by the caller.
    """
    vertices = [(round(x * 1000000), round(y * 1000000)) for x, y in points]
    if vertices[0] != vertices[-1]:
        vertices.append(vertices[0])
    if len(vertices) > 2000 or any(a == b for a, b in zip(vertices, vertices[1:])):
        return None
    edges = list(zip(vertices, vertices[1:]))
    threshold = Fraction(Decimal(str(minimum)) * 1000000)
    for axis in (0, 1):
        levels = sorted({p[axis] for p in vertices})
        slabs = []
        for low, high in zip(levels, levels[1:]):
            sample = Fraction(low + high, 2)
            active = [(a, b) for a, b in edges
                      if min(a[axis], b[axis]) < sample < max(a[axis], b[axis])]
            def value(edge, at):
                a, b = edge
                return Fraction(a[1-axis]) + Fraction(b[1-axis]-a[1-axis],
                                                     b[axis]-a[axis]) * (at-a[axis])
            def intervals(at):
                crossings = sorted(value(edge, at) for edge in active)
                if len(crossings) % 2:
                    return None
                return list(zip(crossings[::2], crossings[1::2]))
            midpoint = intervals(sample)
            if midpoint is None:
                return None
            candidates = [midpoint]
            at_mid = sorted((value(edge, sample), edge) for edge in active)
            for (left, left_edge), (right, right_edge) in zip(at_mid[::2], at_mid[1::2]):
                width_mid = right-left
                if width_mid < threshold:
                    continue  # already covered by the midpoint candidate
                for endpoint in (low, high):
                    width_end = value(right_edge, endpoint)-value(left_edge, endpoint)
                    if width_end >= threshold:
                        continue
                    # Width is affine on this open slab. The crossing of the
                    # rule is exact even if it lies arbitrarily near a vertex.
                    crossing = endpoint + (sample-endpoint) * (
                        threshold-width_end) / (width_mid-width_end)
                    interior = (Fraction(endpoint) + crossing) / 2
                    if low < interior < high:
                        candidates.append(intervals(interior))
            slabs.append((midpoint, candidates))
        for (previous, _), (_, candidates), (following, _) in zip(slabs, slabs[1:], slabs[2:]):
            for current in candidates:
                if current is None:
                    return None
                for left, right in current:
                    if not 0 < right-left < threshold:
                        continue
                    if all(any(start < right and left < end and end-start >= threshold
                               for start, end in neighbor)
                           for neighbor in (previous, following)):
                        return (right-left) / 1000000
    return None


def connected_polygon_scanline_witness(contours, measured_count, minimum):
    """Prove a narrow interior span in a hole-free filled union.

    Rational crossings at vertex-slab midpoints and near exact rule crossings
    avoid floating geometry errors. Candidate near-vertex samples come from
    individual filled regions and the union's midpoint boundary edges; the
    complete union is remeasured at every sample, so touching ink can widen
    it and boundary switches cannot create a false failure. Only a span
    containing filled-region ink can be a witness. Wide neighboring spans
    exclude terminal tips. This remains a partial failure witness.
    """
    if sum(len(points) for points in contours) > 2000:
        return None
    outlines = []
    for points in contours:
        vertices = []
        for x, y in points:
            scaled = (Decimal(str(x)) * 2000000, Decimal(str(y)) * 2000000)
            if any(value != value.to_integral_value() for value in scaled):
                return None
            vertices.append(tuple(int(value) for value in scaled))
        if len(vertices) < 3:
            return None
        if vertices[0] != vertices[-1]:
            vertices.append(vertices[0])
        if any(a == b for a, b in zip(vertices, vertices[1:])):
            return None
        outlines.append(list(zip(vertices, vertices[1:])))
    threshold = Fraction(Decimal(str(minimum)) * 2000000)
    for axis in (0, 1):
        levels = sorted({point[axis] for edges in outlines for edge in edges for point in edge})
        slabs = []
        for low, high in zip(levels, levels[1:]):
            sample = Fraction(low + high, 2)
            active = [[edge for edge in edges
                       if min(edge[0][axis], edge[1][axis]) < sample <
                       max(edge[0][axis], edge[1][axis])]
                      for edges in outlines]
            def value(edge, at):
                a, b = edge
                return Fraction(a[1-axis]) + Fraction(b[1-axis]-a[1-axis],
                                                     b[axis]-a[axis]) * (at-a[axis])
            def merged_at(at):
                intervals = []
                for index, edges in enumerate(active):
                    edges_at = sorted((value(edge, at), edge) for edge in edges)
                    if len(edges_at) % 2:
                        return None
                    intervals.extend((left, right, index < measured_count,
                                      left_edge, right_edge)
                                     for (left, left_edge), (right, right_edge)
                                     in zip(edges_at[::2], edges_at[1::2]))
                merged = []
                for start, end, measured, left_edge, right_edge in sorted(intervals):
                    if end <= start:
                        return None
                    if merged and start <= merged[-1][1]:
                        old = merged[-1]
                        merged[-1] = (old[0], max(end, old[1]), old[2] or measured,
                                      old[3], right_edge if end > old[1] else old[4])
                    else:
                        merged.append((start, end, measured, left_edge, right_edge))
                return merged
            midpoint = merged_at(sample)
            if midpoint is None:
                return None
            candidates = [midpoint]
            for left, right, measured, left_edge, right_edge in midpoint:
                if not measured or right-left < threshold:
                    continue
                for endpoint in (low, high):
                    width_end = value(right_edge, endpoint)-value(left_edge, endpoint)
                    if width_end >= threshold:
                        continue
                    crossing = endpoint + (sample-endpoint) * (
                        threshold-width_end) / (right-left-width_end)
                    interior = (Fraction(endpoint) + crossing) / 2
                    if low < interior < high:
                        candidates.append(merged_at(interior))
                    if len(candidates) > 64:
                        break
                if len(candidates) > 64:
                    break
            for edges in active[:measured_count]:
                crossings = sorted((value(edge, sample), edge) for edge in edges)
                for (left, left_edge), (right, right_edge) in zip(crossings[::2], crossings[1::2]):
                    width_mid = right-left
                    if width_mid < threshold:
                        continue
                    for endpoint in (low, high):
                        width_end = value(right_edge, endpoint)-value(left_edge, endpoint)
                        if width_end >= threshold:
                            continue
                        crossing = endpoint + (sample-endpoint) * (
                            threshold-width_end) / (width_mid-width_end)
                        interior = (Fraction(endpoint) + crossing) / 2
                        if low < interior < high:
                            candidates.append(merged_at(interior))
                        if len(candidates) > 64:
                            break  # bound rational union evaluations
                    if len(candidates) > 64:
                        break
                if len(candidates) > 64:
                    break
            slabs.append((midpoint, candidates))
        for (previous, _), (_, candidates), (following, _) in zip(slabs, slabs[1:], slabs[2:]):
            for current in candidates:
                if current is None:
                    return None
                for left, right, measured, _, _ in current:
                    if not measured or not 0 < right-left < threshold:
                        continue
                    if all(any(start < right and left < end and end-start >= threshold
                               for start, end, _, _, _ in neighbor)
                           for neighbor in (previous, following)):
                        return (right-left) / 2000000
    return None


def check_isolated_filled_necks(path, geometry, objects, filled_regions, minimum):
    """Reject a proven thin span inside an isolated orthogonal filled polygon.

    The test uses only integer plotted coordinates. Touching ink might widen
    the region, and holes or nonorthogonal boundaries need separate proofs.
    """
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('no positive filled-ink neck requirement')
    rule_grid = Decimal(str(minimum)) * 2000000
    for net, shape, (x0, y0, x1, y1), line, points in filled_regions:
        if min(x1-x0, y1-y0) < minimum:
            continue  # the existing whole-region width check handles this
        if not geometry.simple_hole_free_polygon(shape):
            continue
        for other_net, other, (a0, b0, a1, b1) in objects:
            if other == shape or other_net != net:
                continue
            if x1 < a0 or a1 < x0 or y1 < b0 or b1 < y0:
                continue
            if geometry.distance(shape, other) == 0:
                break
        else:
            width_grid = orthogonal_region_min_span(points)
            if width_grid is not None and width_grid < rule_grid:
                raise ValueError('%s:%d: isolated filled region has a %.6f mm span below %.6f mm' %
                                 (Path(path).name, line, width_grid/2000000, minimum))
            if width_grid is None:
                witness = polygon_scanline_witness(points, minimum)
                if witness is not None:
                    raise ValueError('%s:%d: isolated nonorthogonal filled region has a %.6f mm span below %.6f mm' %
                                     (Path(path).name, line, float(witness), minimum))


def check_connected_filled_necks(path, geometry, objects, filled_regions, minimum):
    """Measure touching filled regions with exact rectangular flash widening.

    Every touching same-net region or R-aperture flash joins its component.
    Its flash-only spans are exempt from the filled-region width test. Up to
    four other touching operations can be included through outward boxes:
    if even that guaranteed superset has a thin region span, the real ink
    does too. More complex components remain at the final red gate.
    """
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('no positive filled-ink neck requirement')
    if len(filled_regions) > 500:
        return  # bound pairwise component discovery
    rule_grid = Decimal(str(minimum)) * 2000000
    candidates = list(filled_regions)
    for net, shape, bounds in objects:
        flash = geometry.flashes.get(shape)
        if not flash or flash[2] != 'R':
            continue
        x_um, y_um, _, (width, height) = flash
        if (Decimal(str(width)) * 1000000 != int(Decimal(str(width)) * 1000000) or
                Decimal(str(height)) * 1000000 != int(Decimal(str(height)) * 1000000)):
            continue  # only aperture dimensions on the plotted 1 um grid
        x, y = x_um / 1000000, y_um / 1000000
        points = ((x-width/2, y-height/2), (x+width/2, y-height/2),
                  (x+width/2, y+height/2), (x-width/2, y+height/2))
        candidates.append((net, shape, bounds, None, points))
    if len(candidates) > 5000:
        return
    by_net = defaultdict(list)
    for index, candidate in enumerate(candidates):
        by_net[candidate[0]].append(index)
    visited = set()
    def touching(left, right):
        _, a, (x0, y0, x1, y1), *_ = left
        _, b, (a0, b0, a1, b1), *_ = right
        return not (x1 < a0 or a1 < x0 or y1 < b0 or b1 < y0) and geometry.distance(a, b) == 0
    for seed in range(len(filled_regions)):
        if seed in visited:
            continue
        visited.add(seed)
        group = [seed]
        for index in group:
            member = candidates[index]
            for other in by_net[member[0]]:
                if other not in visited and touching(member, candidates[other]):
                    visited.add(other)
                    group.append(other)
        members = [candidates[index] for index in group]
        regions = [member for member in members if member[3] is not None]
        flashes = [member for member in members if member[3] is None]
        if any(not geometry.simple_hole_free_polygon(member[1]) for member in regions):
            continue
        member_shapes = {member[1] for member in members}
        net = members[0][0]
        unknown = [(other_net, other, bounds) for other_net, other, bounds in objects
                   if other_net == net and other not in member_shapes and
                   any(touching(member, (other_net, other, bounds)) for member in members)]
        if len(unknown) > 4:
            continue
        if unknown:
            # An omitted object's ink could widen this component through any
            # boxed operation. Its bounds must overlap that box, so defer if
            # such an object exists. All boxes in unknown are included below.
            unknown_shapes = {extra for _, extra, _ in unknown}
            if any(other_net == net and other not in member_shapes and
                   other not in unknown_shapes and
                   any(not (x1 < a0 or a1 < x0 or y1 < b0 or b1 < y0)
                       for _, _, (x0, y0, x1, y1) in unknown)
                   for other_net, other, (a0, b0, a1, b1) in objects):
                continue
        elif len(group) < 2:
            continue  # the isolated-region check already covered it
        contours = [member[4] for member in regions + flashes]
        for _, _, (x0, y0, x1, y1) in unknown:
            scale = 2000000
            # One full micrometre outward beyond the parser's already
            # conservative bounds covers float and half-grid rounding.
            left, bottom = math.floor(x0*scale-2), math.floor(y0*scale-2)
            right, top = math.ceil(x1*scale+2), math.ceil(y1*scale+2)
            contours.append(((left/scale, bottom/scale), (right/scale, bottom/scale),
                             (right/scale, top/scale), (left/scale, top/scale)))
        width_grid = orthogonal_regions_min_span(contours, len(regions))
        if width_grid is not None and width_grid < rule_grid:
            raise ValueError('%s:%d: connected filled region union has a %.6f mm span below %.6f mm' %
                             (Path(path).name, regions[0][3], width_grid/2000000, minimum))
        if width_grid is None and len(unknown) <= 1:
            witness = connected_polygon_scanline_witness(contours, len(regions), minimum)
            if witness is not None:
                raise ValueError('%s:%d: connected nonorthogonal filled region union has a %.6f mm '
                                 'interior span below %.6f mm' %
                                 (Path(path).name, regions[0][3], float(witness), minimum))


def check_silk_clearance(silk_path, mask_path, minimum, minimum_ink_width=None):
    """Check plotted legend against negative-polarity mask openings."""
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('no positive silkscreen-to-mask requirement')
    engine = Geometry()
    try:
        openings = plotted_copper(Path(mask_path), engine, require_net=False)
        filled_regions = []
        legend = plotted_copper(Path(silk_path), engine, require_net=False,
                                extra_function='Legend', allow_empty=True,
                                minimum_track=minimum_ink_width,
                                filled_regions=filled_regions)
        if minimum_ink_width is not None:
            check_isolated_filled_width(silk_path, engine, legend, filled_regions,
                                        minimum_ink_width)
            check_isolated_filled_necks(silk_path, engine, legend, filled_regions,
                                        minimum_ink_width)
            check_connected_filled_necks(silk_path, engine, legend, filled_regions,
                                         minimum_ink_width)
        for _, ink, (x0,y0,x1,y1) in legend:
            for _, opening, (a0,b0,a1,b1) in openings:
                if x0-a1 >= minimum or a0-x1 >= minimum or y0-b1 >= minimum or b0-y1 >= minimum:
                    continue
                lower = engine.distance(ink, opening)
                if lower < minimum:
                    upper = (lower + engine.overfill.get(ink, 0) +
                             engine.overfill.get(opening, 0) + .000000002)
                    if upper >= minimum:
                        raise ValueError('%s: silkscreen-to-mask clearance indeterminate: '
                                         'lower %.9f, upper %.9f, rule %.9f mm' %
                                         (Path(silk_path).name, lower, upper, minimum))
                    raise ValueError('%s: silkscreen-to-mask clearance below rule: '
                                     'upper %.9f < %.9f mm' %
                                     (Path(silk_path).name, upper, minimum))
        return len(legend)
    finally:
        engine.close()


def profile_segments(path, geometry):
    """Read a KiCad Edge.Cuts Gerber as independent cut centerlines."""
    path = Path(path)
    lines = path.read_text().splitlines()
    mode = 'G01'
    position = None
    segments = []
    seen_format = seen_units = seen_end = False
    seen_profile = False
    apertures = set()
    current = None
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if line == '%FSLAX46Y46*%':
            seen_format = True
        elif line == '%MOMM*%':
            seen_units = True
        elif line in ('G01*', 'G02*', 'G03*'):
            mode = line[:-1]
        elif line == 'G75*' or line == '%LPD*%':
            pass
        elif line.startswith('%TF.FileFunction,'):
            if line != '%TF.FileFunction,Profile,NP*%':
                raise ValueError('%s:%d: unsupported outline file function' % (path.name, number))
            seen_profile = True
        elif line.startswith('%TF.FilePolarity,'):
            if line != '%TF.FilePolarity,Positive*%':
                raise ValueError('%s:%d: unsupported outline polarity' % (path.name, number))
        elif match := PROFILE_MOVE.fullmatch(line):
            position = (int(match[1])/1e6, int(match[2])/1e6)
        elif match := PROFILE_DRAW.fullmatch(line):
            if not seen_format or not seen_units or position is None or current is None:
                raise ValueError('%s:%d: outline draw before format or start' % (path.name, number))
            target = (int(match[1])/1e6, int(match[2])/1e6)
            if mode == 'G01':
                if match[3] is not None:
                    raise ValueError('%s:%d: arc offsets in line mode' % (path.name, number))
                points = [position, target]
            else:
                if match[3] is None or match[4] is None:
                    raise ValueError('%s:%d: arc lacks center offsets' % (path.name, number))
                center = (position[0]+int(match[3])/1e6,
                          position[1]+int(match[4])/1e6)
                radius = math.dist(position, center)
                if radius <= 0 or abs(math.dist(target, center)-radius) > .000002:
                    raise ValueError('%s:%d: invalid outline arc radius' % (path.name, number))
                begin = math.atan2(position[1]-center[1], position[0]-center[0])
                finish = math.atan2(target[1]-center[1], target[0]-center[0])
                sweep = ((finish-begin) % (2*math.pi) if mode == 'G03' else
                         -((begin-finish) % (2*math.pi)))
                if abs(sweep) < 1e-12:
                    sweep = 2*math.pi if mode == 'G03' else -2*math.pi
                count = max(2, math.ceil(abs(sweep)*radius/.01))
                points = [(center[0]+radius*math.cos(begin+sweep*i/count),
                           center[1]+radius*math.sin(begin+sweep*i/count))
                          for i in range(count+1)]
                points[0], points[-1] = position, target
            if position == target and mode == 'G01':
                raise ValueError('%s:%d: zero-length outline segment' % (path.name, number))
            shape = geometry.wkt('LINESTRING (' + ', '.join('%.9f %.9f' % p for p in points) + ')')
            # Curved segments are replaced by chords; this buffer bounds the
            # largest possible sagitta for the 0.01 mm maximum chord length.
            if mode != 'G01':
                sagitta = radius * (1-math.cos(abs(sweep)/(2*count)))
                shape = geometry.buffer(shape, sagitta + .000001)
            xs, ys = zip(*points)
            segments.append((shape, (min(xs),min(ys),max(xs),max(ys))))
            position = target
        elif match := APERTURE.fullmatch(line):
            if match[2] != 'C' or len(match[3].split('X')) != 1 or float(match[3]) <= 0:
                raise ValueError('%s:%d: unsupported outline aperture' % (path.name, number))
            apertures.add(int(match[1]))
        elif match := SELECT.fullmatch(line):
            if int(match[1]) not in apertures:
                raise ValueError('%s:%d: undefined outline aperture' % (path.name, number))
            current = int(match[1])
        elif line == 'M02*':
            seen_end = True
            if number != len(lines):
                raise ValueError('%s:%d: commands after outline end' % (path.name, number))
        elif (not line or line.startswith('G04 ') or line.startswith(('%TF.', '%TA.', '%TO.C,', '%TD'))):
            pass
        else:
            raise ValueError('%s:%d: unsupported outline command %s' % (path.name, number, line))
    if not seen_format or not seen_units or not seen_end or not seen_profile or not segments:
        raise ValueError('%s: incomplete or empty outline Gerber' % path.name)
    return segments


def check_edge(paths, outline, minimum):
    """Check plotted copper shapes against plotted board cut centerlines."""
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('board has no positive copper-to-edge rule')
    engine = Geometry()
    try:
        edges = profile_segments(outline, engine)
        count = 0
        for path in paths:
            for net, shape, (x0,y0,x1,y1) in plotted_copper(Path(path), engine):
                for edge, (a0,b0,a1,b1) in edges:
                    if x0-a1 >= minimum or a0-x1 >= minimum or y0-b1 >= minimum or b0-y1 >= minimum:
                        continue
                    distance = engine.distance(shape, edge)
                    if distance < minimum:
                        raise ValueError('%s: %s copper-to-edge lower bound %.6f mm < %.6f mm' %
                                         (Path(path).name, net, distance, minimum))
                count += 1
        return count
    finally:
        engine.close()


def check_holes(holes, non_plated, copper_paths, outline, copper_minimum, npth_edge_minimum):
    """Check verified Excellon cuts against plotted copper and NPTH edges.

    `holes` is the multiset returned by fabcheck.drill_hits, after its parity
    check against the board. `non_plated` is the subset matched to board NPTH
    pads. A coincident ComponentPad or ViaPad flash supplies a plated hole's net.
    The Excellon coordinates and tool diameters are the nominal plotted cuts.
    Board parity is checked separately; its rounding must not inflate these
    plotted dimensions. GEOS buffering remains an outward enclosure, so a
    boundary case within its polygonization error remains indeterminate.
    """
    if (not math.isfinite(copper_minimum) or copper_minimum <= 0 or
            not math.isfinite(npth_edge_minimum) or npth_edge_minimum <= 0):
        raise ValueError('hole checks require positive clearance rules')
    if not holes:
        raise ValueError('no verified Excellon cuts for plotted hole checks')
    if any(non_plated[item] > holes[item] for item in non_plated):
        raise ValueError('non-plated cut classification exceeds verified Excellon hits')
    engine = Geometry()
    try:
        objects = []
        features = []
        for path in copper_paths:
            objects.extend((Path(path).name, net, shape, bounds) for net, shape, bounds in
                           plotted_copper(Path(path), engine, features=features))
        edges = profile_segments(Path(outline), engine)
        count = 0
        for item, repeats in holes.items():
            if len(item) == 3:
                x, y, diameter = item
                center = (x, y)
                primitive = engine.wkt('POINT (%.9f %.9f)' % center)
                bounds = (x, y, x, y)
            elif len(item) == 6 and item[0] == 'slot':
                _, x0, y0, x1, y1, diameter = item
                center = ((x0+x1)/2, (y0+y1)/2)
                primitive = engine.wkt('LINESTRING (%.9f %.9f, %.9f %.9f)' % (x0,y0,x1,y1))
                bounds = (min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1))
            else:
                raise ValueError('unsupported Excellon cut key: %r' % (item,))
            if not all(math.isfinite(v) for v in item[1:] if isinstance(v, (float, int))) or diameter <= 0:
                raise ValueError('invalid Excellon cut dimensions')
            radius = diameter/2
            cut = engine.buffer(primitive, radius)
            x0,y0,x1,y1 = bounds
            cut_bounds = (x0-radius, y0-radius, x1+radius, y1+radius)
            owner_nets = {net for function, point, net, _, _ in features
                          if function in ('ComponentPad', 'ViaPad') and point is not None and
                          math.dist(point, center) <= .0011}
            if len(owner_nets) > 1:
                raise ValueError('Excellon cut has conflicting plotted pad nets at %s' % (center,))
            is_npth = bool(non_plated[item])
            owner = None if is_npth else next(iter(owner_nets), None)
            if not is_npth and owner is None:
                raise ValueError('plated Excellon cut lacks ComponentPad/ViaPad flash at %s' %
                                 (center,))
            for path_name, net, copper, (a0,b0,a1,b1) in objects:
                if owner is not None and net == owner:
                    continue
                if (cut_bounds[0]-a1 >= copper_minimum or
                        a0-cut_bounds[2] >= copper_minimum or
                        cut_bounds[1]-b1 >= copper_minimum or
                        b0-cut_bounds[3] >= copper_minimum):
                    continue
                lower = engine.distance(cut, copper)
                if lower < copper_minimum:
                    upper = (lower + engine.overfill.get(cut, 0) +
                             engine.overfill.get(copper, 0) + .000000002)
                    detail = ('indeterminate' if upper >= copper_minimum else 'below rule')
                    raise ValueError('%s: Excellon hole-to-copper %s at %s: lower %.9f, '
                                     'upper %.9f, rule %.9f mm' %
                                     (path_name, detail, center, lower, upper, copper_minimum))
            if is_npth:
                for edge, (a0,b0,a1,b1) in edges:
                    if (cut_bounds[0]-a1 >= npth_edge_minimum or
                            a0-cut_bounds[2] >= npth_edge_minimum or
                            cut_bounds[1]-b1 >= npth_edge_minimum or
                            b0-cut_bounds[3] >= npth_edge_minimum):
                        continue
                    lower = engine.distance(cut, edge)
                    if lower < npth_edge_minimum:
                        upper = lower + engine.overfill.get(cut, 0) + .000000002
                        detail = ('indeterminate' if upper >= npth_edge_minimum else 'below rule')
                        raise ValueError('%s: NPTH hole-to-edge %s at %s: lower %.9f, '
                                         'upper %.9f, rule %.9f mm' %
                                         (Path(outline).name, detail, center, lower, upper,
                                          npth_edge_minimum))
            count += repeats
        return count
    finally:
        engine.close()


def check_clearance(paths, minimum, minimum_track=None):
    """Require distinct X2 nets on each copper layer to meet board clearance."""
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('board has no positive copper clearance rule')
    engine = Geometry()
    try:
        count = 0
        for path in paths:
            filled_regions = []
            objects = plotted_copper(Path(path), engine, minimum_track,
                                     filled_regions=filled_regions)
            if minimum_track is not None:
                check_isolated_filled_width(path, engine, objects, filled_regions,
                                            minimum_track)
                check_isolated_filled_necks(path, engine, objects, filled_regions,
                                            minimum_track)
                check_connected_filled_necks(path, engine, objects, filled_regions,
                                             minimum_track)
            cells = defaultdict(list)
            for index, (net, shape, (x0,y0,x1,y1)) in enumerate(objects):
                # Two millimetre buckets avoid checking every distant pad/track
                # against every other plotted object on a large board.
                xmin = math.floor((x0-minimum)/2)
                xmax = math.floor((x1+minimum)/2)
                ymin = math.floor((y0-minimum)/2)
                ymax = math.floor((y1+minimum)/2)
                if (xmax-xmin+1) * (ymax-ymin+1) > 100000:
                    raise ValueError('%s: copper object spans unsupported area' % Path(path).name)
                candidates = set()
                for cx in range(xmin, xmax+1):
                    for cy in range(ymin, ymax+1):
                        candidates.update(cells[(cx, cy)])
                for previous in candidates:
                    other_net, other, (a0,b0,a1,b1) = objects[previous]
                    if net == other_net or x0-a1 >= minimum or a0-x1 >= minimum or y0-b1 >= minimum or b0-y1 >= minimum:
                        continue
                    exact = engine.circle_distance(shape, other)
                    if exact is not None:
                        if exact < Decimal(str(minimum)):
                            raise ValueError('%s: %s to %s circular copper clearance below rule: '
                                             '%s mm < %.9f mm' %
                                             (Path(path).name, net, other_net, exact, minimum))
                        continue
                    distance = engine.distance(shape, other)
                    if distance < minimum:
                        # The expanded 64-chord arcs guarantee a lower bound.
                        # The largest possible excess over the true plotted arc
                        # is the buffer radius inflation at each object, plus
                        # two nanometres for WKT coordinate rounding.
                        uncertainty = (engine.overfill.get(shape, 0) +
                                       engine.overfill.get(other, 0) + .000000002)
                        upper = distance + uncertainty
                        if upper >= minimum:
                            raise ValueError('%s: %s to %s copper clearance indeterminate: '
                                             'lower bound %.9f mm, upper bound %.9f mm, rule %.9f mm' %
                                             (Path(path).name, net, other_net, distance, upper, minimum))
                        raise ValueError('%s: %s to %s copper clearance below rule: '
                                         'upper bound %.9f mm < %.9f mm' %
                                         (Path(path).name, net, other_net, upper, minimum))
                for cx in range(xmin, xmax+1):
                    for cy in range(ymin, ymax+1):
                        cells[(cx, cy)].append(index)
            count += len(objects)
        return count
    finally:
        engine.close()

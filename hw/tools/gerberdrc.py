"""Independent copper clearance check over exported RS-274X/X2 Gerbers.

Only the KiCad primitives explicitly handled below are accepted. GEOS operates on
the plotted coordinates, not on pcbnew board objects or a second board export.
"""
import ctypes
import ctypes.util
import math
from pathlib import Path
import re
from collections import defaultdict


COORD = re.compile(r'^(?:X(-?\d+))?(?:Y(-?\d+))?D(0[123])\*$')
APERTURE = re.compile(r'^%ADD(\d+)(C|R|O|RoundRect),([^*]+)\*%$')
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
        conservative_radius = radius / math.cos(math.pi / 256)
        result = self.call('GEOSBuffer_r', ctypes.c_void_p,
                           [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_int])(
                               self.ctx, shape, conservative_radius, 64)
        if not result:
            raise ValueError('GEOS failed to buffer plotted geometry')
        self.shapes.append(result)
        return result

    def distance(self, first, second):
        value = ctypes.c_double()
        result = self.call('GEOSDistance_r', ctypes.c_int,
                           [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)])(
                               self.ctx, first, second, ctypes.byref(value))
        if result != 1 or not math.isfinite(value.value):
            raise ValueError('GEOS failed to measure Gerber clearance')
        return value.value

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


def plotted_copper(path, geometry, minimum_track=None, require_net=True):
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
    mask_function = False
    macro = None
    macro_defined = False

    def add(shape, bounds):
        if require_net and net is None:
            raise ValueError('%s: copper geometry without TO.N net' % path.name)
        result.append((net, shape, bounds))

    for number, line in enumerate(lines, 1):
        line = line.strip()
        if macro is not None:
            macro.append(line)
            if line.endswith('*%'):
                if tuple(macro) != ROUND_RECT_MACRO:
                    raise ValueError('%s: unsupported RoundRect macro definition' % path.name)
                macro = None
                macro_defined = True
            continue
        if line == '%FSLAX46Y46*%':
            seen_format = True
        elif line == '%MOMM*%':
            seen_units = True
        elif line.startswith('%AM'):
            if line != '%AMRoundRect*':
                raise ValueError('%s:%d: unsupported aperture macro' % (path.name, number))
            macro = []
        elif match := APERTURE.fullmatch(line):
            params = tuple(float(x) for x in match[3].split('X'))
            kind = match[2]
            if kind == 'RoundRect' and not macro_defined:
                raise ValueError('%s:%d: undefined RoundRect macro' % (path.name, number))
            if (kind == 'C' and len(params) != 1 or kind in ('R', 'O') and len(params) != 2 or
                    kind == 'RoundRect' and len(params) != 10 or
                    any(not math.isfinite(x) for x in params) or
                    any(x <= 0 for x in params[:1 if kind not in ('R', 'O') else 2])):
                raise ValueError('%s:%d: unsupported aperture dimensions' % (path.name, number))
            apertures[int(match[1])] = (kind, params)
        elif line.startswith('%TO.N,') and line.endswith('*%'):
            net = line[6:-2]
            if not net:
                raise ValueError('%s:%d: empty net attribute' % (path.name, number))
        elif line == '%TD*%' or line == '%TD.N*%':
            net = None
        elif line == '%LPD*%':
            pass
        elif line.startswith('%TF.FileFunction,'):
            mask_function = line.startswith('%TF.FileFunction,Soldermask,')
        elif line.startswith('%TF.FilePolarity,'):
            file_polarity = line
            expected_polarity = ('%TF.FilePolarity,Positive*%' if require_net else
                                 '%TF.FilePolarity,Negative*%')
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
            add(geometry.wkt(polygon(region), repair=True), (min(xs), min(ys), max(xs), max(ys)))
            region = None
        elif match := SELECT.fullmatch(line):
            current = int(match[1])
            if current not in apertures:
                raise ValueError('%s:%d: undefined aperture' % (path.name, number))
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
                kind, params = apertures[current]
                if operation == '01':
                    if position is None or kind != 'C':
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
                    radius = params[0] / 2
                    shape = geometry.buffer(geometry.wkt('POINT (%.9f %.9f)' % target), radius)
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
                    bounds = (x-width/2,y-height/2,x+width/2,y+height/2)
                else:
                    radius = params[0]
                    corners = [(x+params[i], y+params[i+1]) for i in (1,3,5,7)]
                    center = (sum(px for px, _ in corners)/4, sum(py for _, py in corners)/4)
                    corners.sort(key=lambda point: math.atan2(point[1]-center[1], point[0]-center[0]))
                    shape = geometry.buffer(geometry.wkt(polygon(corners)), radius)
                    xs, ys = zip(*corners)
                    bounds = (min(xs)-radius,min(ys)-radius,max(xs)+radius,max(ys)+radius)
                add(shape, bounds)
            position = target
        elif line == 'M02*':
            seen_end = True
            if number != len(lines):
                raise ValueError('%s:%d: commands after end marker' % (path.name, number))
        elif (not line or line.startswith('G04 ') or line == 'G01*' or
              line.startswith(('%TF.', '%TA.', '%TO.P,', '%TO.C,', '%TD.AperFunction')) or
              line == '%TD.P*%'):
            pass
        else:
            raise ValueError('%s:%d: unsupported Gerber command %s' % (path.name, number, line))
    if (macro is not None or region is not None or not seen_end or not seen_format or
            not seen_units or not result or not require_net and
            (file_polarity != '%TF.FilePolarity,Negative*%' or not mask_function)):
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


def check_clearance(paths, minimum, minimum_track=None):
    """Require distinct X2 nets on each copper layer to meet board clearance."""
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError('board has no positive copper clearance rule')
    engine = Geometry()
    try:
        count = 0
        for path in paths:
            objects = plotted_copper(Path(path), engine, minimum_track)
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
                    distance = engine.distance(shape, other)
                    if distance < minimum:
                        raise ValueError('%s: %s to %s copper clearance lower bound %.6f mm < %.6f mm' %
                                         (Path(path).name, net, other_net, distance, minimum))
                for cx in range(xmin, xmax+1):
                    for cy in range(ymin, ymax+1):
                        cells[(cx, cy)].append(index)
            count += len(objects)
        return count
    finally:
        engine.close()

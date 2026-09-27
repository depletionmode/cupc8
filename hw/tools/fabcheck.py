#!/usr/bin/env python3
"""Check fabrication files against a DRC-clean KiCad board and plotted copper."""
from collections import Counter
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

import pcbnew
import gerberdrc


GERBER_EXTENSIONS = {'.gtl', '.gbl', '.gts', '.gbs', '.gtp', '.gbp',
                     '.gto', '.gbo', '.gm1', '.g1', '.g2', '.g3', '.g4', '.gbr'}
TIMESTAMP = re.compile(r'^(?:%TF.CreationDate,|G04 Created by KiCad )')
# Hole keys use millimetres rounded to 0.001. Reject finer Excellon
# coordinates rather than silently changing the plotted drill geometry.
DECIMAL_MM = r'-?\d+(?:\.\d{1,3})?'
TOOL = re.compile(r'^T(\d+)C(' + DECIMAL_MM + r')$')
HIT = re.compile(r'^X(' + DECIMAL_MM + r')Y(' + DECIMAL_MM + r')$')
SLOT = re.compile(r'^X(' + DECIMAL_MM + r')Y(' + DECIMAL_MM + r')G85X(' + DECIMAL_MM + r')Y(' + DECIMAL_MM + r')$')


def slot_key(start, end, diameter):
    a, b = sorted((tuple(round(float(x), 3) for x in start),
                   tuple(round(float(x), 3) for x in end)))
    if a == b:
        raise ValueError('zero-length G85 slot route')
    return ('slot', *a, *b, round(float(diameter), 3))


def gerber_geometry(path):
    lines = path.read_text().splitlines()
    if not any(s.startswith('%FSLAX') for s in lines) or '%MOMM*%' not in lines:
        raise ValueError('%s: unsupported Gerber format' % path.name)
    if not any(s == 'M02*' for s in lines):
        raise ValueError('%s: missing Gerber end marker' % path.name)
    # Empty paste/mask/silk layers can be legitimate. Copper and outline cannot.
    if path.suffix.lower() in ('.gtl', '.gbl', '.gm1', '.g1', '.g2', '.g3', '.g4') and not any(
            re.search(r'[XY]-?\d+.*D0[123]\*', s) for s in lines):
        raise ValueError('%s: no plotted geometry' % path.name)
    return tuple(s for s in lines if not TIMESTAMP.match(s))


def export_parity(board, fab):
    pcb = board / (board.name + '.kicad_pcb')
    b = pcbnew.LoadBoard(str(pcb))
    layers = ['F.Cu', 'B.Cu'] + ['In%d.Cu' % n for n in range(1, b.GetCopperLayerCount() - 1)]
    layers += ['F.Mask', 'B.Mask', 'F.Paste', 'B.Paste',
               'F.SilkS', 'B.SilkS', 'Edge.Cuts']
    with tempfile.TemporaryDirectory(prefix='cupc8-fabcheck-') as tmp:
        subprocess.run(['kicad-cli', 'pcb', 'export', 'gerbers', '--layers', ','.join(layers),
                        '-o', tmp + '/', str(pcb)], check=True, capture_output=True, text=True)
        expected = {p.name: p for p in Path(tmp).iterdir() if p.suffix.lower() in GERBER_EXTENSIONS}
        actual = {p.name: p for p in fab.iterdir() if p.suffix.lower() in GERBER_EXTENSIONS}
        if not expected or set(actual) != set(expected):
            raise ValueError('Gerber layer set differs from fresh board export: missing %s; extra %s' %
                             (sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))))
        for name in sorted(expected):
            if gerber_geometry(actual[name]) != gerber_geometry(expected[name]):
                raise ValueError('%s: Gerber geometry differs from fresh board export' % name)
    return b, len(actual)


def drill_hits(path, return_types=False):
    lines = path.read_text().splitlines()
    if not lines or lines[0] != 'M48' or 'METRIC' not in lines or '%' not in lines:
        raise ValueError('%s: unsupported Excellon header' % path.name)
    tools = {}
    tool_plating = {}
    hit_plating = {}
    pending_plating = None
    active = None
    hits = Counter()
    in_body = False
    for line in lines:
        line = line.strip()
        if line.startswith('; #@! TA.AperFunction,'):
            if line.startswith('; #@! TA.AperFunction,NonPlated,NPTH,'):
                pending_plating = 'NPTH'
            elif line.startswith('; #@! TA.AperFunction,Plated,PTH,'):
                pending_plating = 'PTH'
            else:
                raise ValueError('%s: unsupported Excellon plating attribute %s' % (path.name, line))
            continue
        if line == '%':
            in_body = True
            continue
        if not line or line.startswith(';'):
            continue
        tool = TOOL.fullmatch(line)
        if tool and not in_body:
            tools[tool[1]] = round(float(tool[2]), 3)
            if return_types:
                if pending_plating is None:
                    raise ValueError('%s: drill tool lacks plating attribute' % path.name)
                tool_plating[tool[1]] = pending_plating
            pending_plating = None
        elif in_body and re.fullmatch(r'T\d+', line):
            active = line[1:]
            if active not in tools:
                raise ValueError('%s: undefined drill tool %s' % (path.name, active))
        elif in_body and (hit := HIT.fullmatch(line)):
            if active is None:
                raise ValueError('%s: drill hit before tool selection' % path.name)
            key = (round(float(hit[1]), 3), round(float(hit[2]), 3), tools[active])
            hits[key] += 1
            if return_types:
                kind = tool_plating[active]
                if key in hit_plating and hit_plating[key] != kind:
                    raise ValueError('%s: mixed plating class for same drill cut' % path.name)
                hit_plating[key] = kind
        elif in_body and (slot := SLOT.fullmatch(line)):
            if active is None:
                raise ValueError('%s: G85 slot before tool selection' % path.name)
            key = slot_key((slot[1], slot[2]), (slot[3], slot[4]), tools[active])
            hits[key] += 1
            if return_types:
                kind = tool_plating[active]
                if key in hit_plating and hit_plating[key] != kind:
                    raise ValueError('%s: mixed plating class for same drill cut' % path.name)
                hit_plating[key] = kind
        elif line in ('M48', 'FMAT,2', 'METRIC', 'G90', 'G05', 'M30'):
            continue
        else:
            raise ValueError('%s: unsupported Excellon command %s' % (path.name, line))
    if not hits or lines[-1].strip() != 'M30':
        raise ValueError('%s: empty or incomplete drill file' % path.name)
    return (hits, hit_plating) if return_types else hits


def board_holes(board, return_npth=False):
    holes = Counter()
    npth = Counter()

    def add(position, diameter, non_plated=False):
        # KiCad Excellon output uses Y-up; pcbnew board coordinates are Y-down.
        key = (round(pcbnew.ToMM(position.x), 3), round(-pcbnew.ToMM(position.y), 3),
               round(pcbnew.ToMM(diameter), 3))
        holes[key] += 1
        if non_plated:
            npth[key] += 1

    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            drill = pad.GetDrillSize()
            if drill.x or drill.y:
                non_plated = pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
                if not non_plated and pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                    raise ValueError('drilled pad has unsupported plating attribute')
                if drill.x != drill.y:
                    width = pcbnew.ToMM(min(drill.x, drill.y))
                    half_route = pcbnew.ToMM(abs(drill.x - drill.y)) / 2
                    angle = math.radians(pad.GetOrientationDegrees())
                    # Local long axis rotated into Gerber/Excellon Y-up space.
                    direction = ((math.cos(angle), math.sin(angle)) if drill.x > drill.y
                                 else (math.sin(angle), -math.cos(angle)))
                    center = (pcbnew.ToMM(pad.GetPosition().x),
                              -pcbnew.ToMM(pad.GetPosition().y))
                    offsets = (half_route * direction[0], half_route * direction[1])
                    start = (center[0] - offsets[0], center[1] - offsets[1])
                    end = (center[0] + offsets[0], center[1] + offsets[1])
                    key = slot_key(start, end, width)
                    holes[key] += 1
                    if non_plated:
                        npth[key] += 1
                else:
                    add(pad.GetPosition(), drill.x, non_plated)
    # KiCad 10's Python 3.14 binding wraps vias as PCB_TRACK, so read the
    # saved via S-expressions directly instead of trusting SWIG downcasts.
    import kicadgen
    tree = kicadgen.parse(Path(board.GetFileName()).read_text())
    for via in kicadgen.find(tree, 'via'):
        at = kicadgen.find1(via, 'at')
        drill = kicadgen.find1(via, 'drill')
        if at is None or drill is None or len(drill) != 2:
            raise ValueError('unsupported via drill in board file')
        holes[(round(float(at[1]), 3), round(-float(at[2]), 3), round(float(drill[1]), 3))] += 1
    return (holes, npth) if return_npth else holes


def check_drills(board, fab, return_hits=False):
    files = sorted(fab.glob('*.drl'))
    if not files:
        raise ValueError('missing Excellon drill file')
    actual = Counter()
    actual_plating = {}
    for path in files:
        if return_hits:
            parsed, plating = drill_hits(path, return_types=True)
            for item, kind in plating.items():
                if item in actual_plating and actual_plating[item] != kind:
                    raise ValueError('mixed Excellon plating class across files')
                actual_plating[item] = kind
            actual.update(parsed)
        else:
            actual.update(drill_hits(path))
    expected, npth_expected = board_holes(board, return_npth=True) if return_hits else (board_holes(board), Counter())
    unmatched = list(expected.elements())
    npth_remaining = npth_expected.copy()
    extra = []
    npth_actual = Counter()

    def same_hole(actual_item, expected_item):
        if len(actual_item) != len(expected_item) or actual_item[-1] != expected_item[-1]:
            return False
        if len(actual_item) == 6:
            if actual_item[0] != 'slot' or expected_item[0] != 'slot':
                return False
            coordinates = zip(actual_item[1:-1], expected_item[1:-1])
        else:
            coordinates = zip(actual_item[:-1], expected_item[:-1])
        return all(abs(a - b) <= .0011 for a, b in coordinates)

    for item in actual.elements():
        match = next((i for i, expected_item in enumerate(unmatched)
                      if same_hole(item, expected_item)), None)
        if match is None:
            extra.append(item)
        else:
            expected_item = unmatched.pop(match)
            is_npth = bool(npth_remaining[expected_item])
            if return_hits and actual_plating[item] != ('NPTH' if is_npth else 'PTH'):
                raise ValueError('Excellon plating class differs from board pad/via at %s' % (item,))
            if is_npth:
                npth_remaining[expected_item] -= 1
                npth_actual[item] += 1
    if unmatched or extra:
        missing = unmatched[:5]
        extra = extra[:5]
        raise ValueError('drill-to-pad/via mismatch: missing %s; extra %s' % (missing, extra))
    return (sum(actual.values()), actual, npth_actual) if return_hits else sum(actual.values())


def check_review(out):
    """Require a recorded visual CPL overlay review tied to exact artifacts."""
    path = out / 'fab' / 'cpl-review.json'
    if not path.is_file():
        raise ValueError('CPL overlay review missing: fab/cpl-review.json')
    review = json.loads(path.read_text())
    if review.get('board') != out.name or not review.get('reviewer') or not review.get('reviewed_at'):
        raise ValueError('CPL review lacks board, reviewer, or reviewed_at')
    if review.get('result') != 'approved':
        raise ValueError('CPL overlay review is not approved')
    import hashlib
    for name in ('fab/bom.csv', 'fab/cpl.csv', out.name + '.kicad_pcb', out.name + '-top.png'):
        digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
        if review.get('sha256', {}).get(name) != digest:
            raise ValueError('CPL review is stale or incomplete: ' + name)
    if not review.get('notes'):
        raise ValueError('CPL review needs placement/rotation notes')


def check(out):
    board, layers = export_parity(out, out / 'fab')
    holes, cuts, npth_cuts = check_drills(board, out / 'fab', return_hits=True)
    copper = sorted(path for path in (out / 'fab').iterdir()
                    if path.suffix.lower() in ('.gtl', '.gbl', '.g1', '.g2', '.g3', '.g4'))
    if len(copper) != board.GetCopperLayerCount():
        raise ValueError('Gerber copper layer count differs from board stackup')
    clearance = pcbnew.ToMM(board.GetDesignSettings().m_MinClearance)
    track_width = pcbnew.ToMM(board.GetDesignSettings().m_TrackMinWidth)
    shapes = gerberdrc.check_clearance(copper, clearance, track_width)
    rings = gerberdrc.check_via_annular(board, copper,
                                       pcbnew.ToMM(board.GetDesignSettings().m_ViasMinAnnularWidth))
    # JLCPCB lists 0.20 mm as the PTH annular-ring minimum for this process.
    # Keep it distinct from KiCad's via-only 0.13 mm rule.
    pth_rings = gerberdrc.check_pth_annular(board, copper, .20)
    outlines = sorted((out / 'fab').glob('*.gm1'))
    if len(outlines) != 1:
        raise ValueError('expected one Edge.Cuts Gerber profile')
    gerberdrc.check_edge(copper, outlines[0],
                         pcbnew.ToMM(board.GetDesignSettings().m_CopperEdgeClearance))
    gerberdrc.check_holes(cuts, npth_cuts, copper, outlines[0],
                          pcbnew.ToMM(board.GetDesignSettings().m_HoleClearance), 1.0)
    masks = {path.suffix.lower(): path for path in (out / 'fab').iterdir()
             if path.suffix.lower() in ('.gts', '.gbs')}
    surfaces = {path.suffix.lower(): path for path in copper
                if path.suffix.lower() in ('.gtl', '.gbl')}
    if set(masks) != {'.gts', '.gbs'} or set(surfaces) != {'.gtl', '.gbl'}:
        raise ValueError('expected front and back solder-mask Gerbers')
    mask_width = pcbnew.ToMM(board.GetDesignSettings().m_SolderMaskMinWidth)
    if mask_width > 0:
        gerberdrc.check_mask(masks.values(), mask_width)
    exposed = (gerberdrc.check_mask_alignment(surfaces['.gtl'], masks['.gts']) +
               gerberdrc.check_mask_alignment(surfaces['.gbl'], masks['.gbs']))
    paste = {path.suffix.lower(): path for path in (out / 'fab').iterdir()
             if path.suffix.lower() in ('.gtp', '.gbp')}
    if set(paste) != {'.gtp', '.gbp'}:
        raise ValueError('expected front and back solder-paste Gerbers')
    deposits = (gerberdrc.check_paste_registration(surfaces['.gtl'], masks['.gts'], paste['.gtp']) +
                gerberdrc.check_paste_registration(surfaces['.gbl'], masks['.gbs'], paste['.gbp']))
    silk = {path.suffix.lower(): path for path in (out / 'fab').iterdir()
            if path.suffix.lower() in ('.gto', '.gbo')}
    if set(silk) != {'.gto', '.gbo'}:
        raise ValueError('expected front and back silkscreen Gerbers')
    ink = (gerberdrc.check_silk_clearance(silk['.gto'], masks['.gts'], .15, .15) +
           gerberdrc.check_silk_clearance(silk['.gbo'], masks['.gbs'], .15, .15))
    check_review(out)
    raise ValueError('Gerber re-import DRC incomplete: %d layers match fresh export, '
                     '%d drill hits match pads/vias, and %d plotted copper objects '
                     'passed %.3f mm net clearance with %d via and %d PTH annular checks, '
                     '%d exposed pads checked against mask, %d paste deposits checked '
                     'against copper/mask, and %d silkscreen objects checked against mask; '
                     'text height, filled ink necks, and other rules remain unchecked%s' %
                     (layers, holes, shapes, clearance, rings, pth_rings, exposed, deposits, ink,
                      '; no positive solder-mask web rule is configured' if mask_width <= 0 else ''))

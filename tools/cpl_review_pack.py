#!/usr/bin/env python3
"""CPL review pack: one HTML sheet per board for the placements that need a
pin-1 / polarity look (tools/cpl_focus.py), and the helper that turns David's
decisions into fab/cpl-review.json (hw/tools/fabcheck.py check_review).

    python3 tools/cpl_review_pack.py build [--boards io wifi] [--out build/cpl-review-pack]
    python3 tools/cpl_review_pack.py sign build/cpl-review-pack/io-decisions.json --reviewer "Name" [--write]

`build` reads build/hw/<board>/{<board>.kicad_pcb, fab/bom.csv, fab/cpl.csv}
as they are and writes <out>/<board>.html (self-contained: one inline SVG plot
of the board, every close-up a crop of it), <out>/index.html and manifest.json
(the SHA-256 of the four files check_review binds a review to). It signs
nothing and writes no cpl-review.json.

`sign` turns the decisions JSON that a sheet's "Download decisions" button
writes into build/hw/<board>/fab/cpl-review.json, but only when every part in
the pack is ticked OK and the four files still hash as they did when the pack
was built (a rebuild makes the pack stale: rebuild the pack). Without --write
it only checks and prints. Run it yourself: it takes the reviewer's name from
--reviewer and never invents one.

Regenerate the pack after every board rebuild.
"""

import argparse
import csv
import datetime
import hashlib
import html
import json
import math
import os
import re
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cpl_autochecks as auto  # noqa: E402
import cpl_codex  # noqa: E402
import cpl_focus  # noqa: E402

BOARDS = ('main', 'cpu', 'gpu', 'io', 'storage', 'wifi', 'eink', 'system')
PARTS = os.path.join(ROOT, 'hw', 'parts')
RESOLUTIONS = os.path.join(HERE, 'cpl_resolutions.yaml')   # parts David resolved explicitly
DATASHEETS = os.path.join(HERE, 'cpl_datasheets.yaml')     # what the datasheet drawings show, part by part
CACHE = os.path.join(ROOT, 'build', 'cpl-datasheets')       # downloaded PDFs, page text, crops
TOLERANCE = 0.2      # mm, bomcheck.PAD_TOLERANCE
POLAR = {'K': 'K', 'A': 'A', 'CATHODE': 'K', 'ANODE': 'A', '-': 'K', '+': 'A', 'C': 'K'}
LAYERS = 'F.Cu,F.Silkscreen,F.Fab,F.Courtyard,Edge.Cuts'
# risk order: what a wrong rotation ruins hardest first
RANK = {'U': 0, 'J': 1, 'P': 1, 'D': 2, 'LED': 2, 'Q': 3, 'Y': 4, 'X': 4, 'SW': 5, 'RN': 6}


def sha256(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def bound_files(build_dir, board):
    """The four files check_review hashes, as check_review names them."""
    out = os.path.join(build_dir, board)
    return {'fab/bom.csv': os.path.join(out, 'fab', 'bom.csv'),
            'fab/cpl.csv': os.path.join(out, 'fab', 'cpl.csv'),
            board + '.kicad_pcb': os.path.join(out, board + '.kicad_pcb'),
            board + '-top.png': os.path.join(out, board + '-top.png')}


def load_yaml(path):
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        return yaml.safe_load(handle)


# ---------------------------------------------------------------- inputs

def focus_rows(build_dir, board):
    """The board's placements that need a pin-1/polarity look, with the BOM
    line and CPL row each comes from."""
    out = os.path.join(build_dir, board, 'fab')
    with open(os.path.join(out, 'cpl.csv')) as handle:
        cpl = {row['Designator']: row for row in csv.DictReader(handle)}
    rows = []
    with open(os.path.join(out, 'bom.csv')) as handle:
        for line in csv.DictReader(handle):
            for ref in line['Designator'].split(','):
                if ref in cpl:
                    rows.append({'designator': ref, 'value': line['Comment'], 'footprint': line['Footprint'],
                                 'lcsc_part': line['LCSC Part #'], 'cpl': cpl[ref]})
    return cpl_focus.focus(rows)


def rank(row):
    prefix = re.match(r'[A-Z]+', row['designator']).group(0)
    return RANK.get(prefix, 7)


def natural(ref):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', ref)]


def netlist_pins(net_path):
    """{ref: {pad number: symbol pin name}} from the board's KiCad netlist
    (a pin named K_1 is pin K on pad 1)."""
    with open(net_path) as handle:
        text = handle.read()
    pins = {}
    for ref, pin, name in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)\s+\(pinfunction "([^"]*)"\)', text):
        pins.setdefault(ref, {})[pin] = re.sub(r'_%s$' % re.escape(pin), '', name)
    return pins


def read_board(pcb_path, refs):
    """{ref: footprint facts} from the .kicad_pcb, through pcbnew; plus the
    board outline's bounding box (the SVG plot's origin)."""
    import pcbnew
    board = pcbnew.LoadBoard(pcb_path)
    mm = 1e-6
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    box = outline.BBox()
    facts = {}
    for ref in refs:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        pads = []
        for pad in fp.Pads():
            if not pad.GetNumber() or pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            rel = pad.GetFPRelativePosition()
            pads.append({'n': pad.GetNumber(), 'x': pad.GetX() * mm, 'y': pad.GetY() * mm,
                         'w': pad.GetSizeX() * mm, 'h': pad.GetSizeY() * mm,
                         'fx': rel.x * mm, 'fy': rel.y * mm,
                         'func': pad.GetPinFunction(), 'net': pad.GetNetname()})
        facts[ref] = {'x': fp.GetX() * mm, 'y': fp.GetY() * mm, 'rot': fp.GetOrientationDegrees() % 360,
                      'layer': fp.GetLayerName(), 'fpid': fp.GetFPIDAsString(), 'pads': pads}
    return facts, (box.GetX() * mm, box.GetY() * mm, box.GetWidth() * mm, box.GetHeight() * mm)


def plot_board(pcb_path, svg_path, outline):
    """One SVG of the board (kicad-cli, niced); returns (its inner markup,
    (origin x, origin y) in board mm). kicad-cli's board-sized page starts at
    the outline polygon's corner; the polygon approximates arcs, so the
    plotted size is slightly smaller and the origin is centred by the difference."""
    subprocess.run(['nice', '-n', '19', 'kicad-cli', 'pcb', 'export', 'svg', '--layers', LAYERS,
                    '--mode-single', '--page-size-mode', '2', '--exclude-drawing-sheet',
                    '-o', svg_path, pcb_path], check=True, capture_output=True)
    with open(svg_path) as handle:
        svg = handle.read()
    match = re.search(r'viewBox="0\.0000 0\.0000 ([\d.]+) ([\d.]+)"', svg)
    width, height = float(match.group(1)), float(match.group(2))
    ox, oy, ow, oh = outline
    if abs(ow - width) > 0.1 or abs(oh - height) > 0.1:
        raise SystemExit('%s: plot is %.3f x %.3f mm but the outline is %.3f x %.3f: origin unknown'
                         % (pcb_path, width, height, ow, oh))
    inner = svg[svg.index('</desc>') + len('</desc>'):svg.rindex('</svg>')]
    return inner, (ox + (ow - width) / 2, oy + (oh - height) / 2)


# ---------------------------------------------------------------- analysis

def compass(dx, dy):
    """Where (dx, dy) lies as seen on the board from the top (y down)."""
    if math.hypot(dx, dy) < 0.05:
        return 'at the centre'
    names = ['right', 'upper right', 'top', 'upper left', 'left', 'lower left', 'bottom', 'lower right']
    angle = math.degrees(math.atan2(-dy, dx)) % 360
    return names[int(((angle + 22.5) % 360) // 45)]


def analyse(ref, row, fact, turn_table, net_pins):
    """Everything the sheet says about one part. Statuses: 'ok', 'check'
    (something the tool cannot confirm) or 'bad' (a disagreement)."""
    cpl = row['cpl']
    lcsc = row['lcsc_part']
    pads = fact['pads']
    flags = []                       # (severity, text)
    info = {'ref': ref, 'value': row['value'], 'lcsc': lcsc, 'footprint': row['footprint'],
            'fpid': fact['fpid'], 'flags': flags, 'kicad_rot': fact['rot'],
            'cpl_rot': float(cpl['Rotation']) % 360, 'cpl_x': cpl['Mid X'], 'cpl_y': cpl['Mid Y'],
            'board_x': fact['x'], 'board_y': fact['y'], 'npads': len(pads)}
    if fact['layer'] != 'F.Cu' or cpl['Layer'] != 'Top':
        flags.append(('bad', 'not a Top-side part (pcb %s, CPL %s): this pack only handles Top' % (fact['layer'], cpl['Layer'])))
    # KiCad's pad 1 (or the cathode of a polarised 2-pad part)
    table = load_yaml(os.path.join(PARTS, lcsc + '.yaml')) or {}
    symbol_pins = {str(k): ([v] if isinstance(v, str) else list(v)) for k, v in (table.get('pins') or {}).items()}
    names = {p['n']: (symbol_pins.get(p['n']) or [net_pins.get(p['n'], '')]) for p in pads}
    polar = len(pads) == 2 and all(n[0].upper() in POLAR for n in names.values())
    key_pad = None
    if polar:
        for pad in pads:
            if POLAR[names[pad['n']][0].upper()] == 'K':
                key_pad = pad
        info['polar'] = 'pad %s is the cathode (%s), pad %s the anode (%s)' % tuple(
            [key_pad['n'], names[key_pad['n']][0]] + [p for q in pads if q is not key_pad
                                                       for p in (q['n'], names[q['n']][0])])
    else:
        key_pad = next((p for p in pads if p['n'] == '1'), pads[0] if pads else None)
    info['key_pad'] = key_pad
    info['names'] = {p['n']: net_pins.get(p['n'], names[p['n']][0]) for p in pads}
    if key_pad is None:
        flags.append(('bad', 'the footprint has no pads'))
        return info
    xs = [p['x'] for p in pads]
    ys = [p['y'] for p in pads]
    info['pad_box'] = (min(p['x'] - p['w'] / 2 for p in pads), min(p['y'] - p['h'] / 2 for p in pads),
                       max(p['x'] + p['w'] / 2 for p in pads), max(p['y'] + p['h'] / 2 for p in pads))
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    dx, dy = key_pad['x'] - cx, key_pad['y'] - cy
    info['where'] = ('%s %s is at the %s of the pad field (%.2f, %.2f mm from its centre; x right, y down, seen from the top)'
                     % ('cathode pad' if polar else 'pad', key_pad['n'], compass(dx, dy), dx, dy))
    info['frame'] = ('in the footprint as KiCad draws it (0 deg): pad %s at (%.3f, %.3f) mm from the footprint origin; '
                     'the part sits at %.0f deg' % (key_pad['n'], key_pad['fx'], key_pad['fy'], fact['rot']))
    # CPL row against the pcb
    turn = turn_table.get(fact['fpid'])
    if turn is None:
        flags.append(('check', 'UNKNOWN: %s has no entry in hw/parts/jlc_rotation.yaml' % fact['fpid']))
    else:
        want = (fact['rot'] + turn['rotation']) % 360
        if abs((want - info['cpl_rot'] + 180) % 360 - 180) > 0.01:
            flags.append(('bad', 'CPL rotation %.1f but pcb %.1f + table %s = %.1f' % (info['cpl_rot'], fact['rot'], turn['rotation'], want)))
        if not turn.get('offset') and (abs(float(cpl['Mid X'][:-2]) - fact['x']) > 0.001
                                       or abs(float(cpl['Mid Y'][:-2]) + fact['y']) > 0.001):
            flags.append(('bad', 'CPL position differs from the pcb position'))
    # JLC's footprint: EasyEDA's pads turned by the CPL rotation
    easyeda = load_yaml(os.path.join(PARTS, 'easyeda', lcsc + '.yaml'))
    info['easyeda'] = easyeda
    info['turn'] = turn
    info['predicted'] = None
    if easyeda is None:
        flags.append(('check', 'UNKNOWN: no EasyEDA record for %s in hw/parts/easyeda, so JLC\'s footprint and rotation are not known' % lcsc))
        return info
    epins = {str(k): v for k, v in easyeda['pins'].items()}
    epads = [(str(n), x, y) for n, x, y in easyeda['pads']]
    if polar:
        ekey = {n: POLAR.get(v.upper()) for n, v in epins.items()}
        match_key = lambda pad_number: POLAR[names[pad_number][0].upper()]
        epad_key = lambda n: ekey.get(n)
    elif table.get('interchangeable_pins') or len(pads) == 2:
        match_key, epad_key = None, None
    else:
        match_key, epad_key = (lambda n: n), (lambda n: n)
    angle = math.radians(info['cpl_rot'])
    mid_x, mid_y = float(cpl['Mid X'][:-2]), float(cpl['Mid Y'][:-2])         # y up
    world = [(n, mid_x + x * math.cos(angle) - y * math.sin(angle),
              mid_y + x * math.sin(angle) + y * math.cos(angle)) for n, x, y in epads]
    tol = table.get('pad_tolerance') or TOLERANCE
    worst = 0.0
    for pad in pads:
        near = min(world, key=lambda e: math.hypot(e[1] - pad['x'], e[2] + pad['y']))
        dist = math.hypot(near[1] - pad['x'], near[2] + pad['y'])
        worst = max(worst, dist)
        wrong_pin = bool(match_key) and match_key(pad['n']) != epad_key(near[0])
        if wrong_pin or dist > tol:
            flags.append(('bad' if wrong_pin else 'check',
                          'KiCad pad %s is %.3f mm from JLC\'s nearest pad %s (limit %.2f)%s'
                          % (pad['n'], dist, near[0], tol, ': pin 1 or polarity would be placed wrong' if wrong_pin
                             else ': same pin, the land is drawn a little apart; judge by eye')))
            break
    if match_key is None:
        info['match_note'] = 'pads are interchangeable (2-terminal or the datasheet table says so): geometry only, no pin numbers compared'
    if len(world) != len(pads):
        flags.append(('check', 'KiCad has %d pads, EasyEDA %d' % (len(pads), len(world))))
    if match_key:
        target = epad_key(match_key(key_pad['n'])) if polar else key_pad['n']
        hit = next((w for w in world if epad_key(w[0]) == (POLAR[names[key_pad['n']][0].upper()] if polar else key_pad['n'])), None)
        if hit:
            info['predicted'] = (hit[1], -hit[2], hit[0])
    else:
        hit = min(world, key=lambda e: math.hypot(e[1] - key_pad['x'], e[2] + key_pad['y']))
        info['predicted'] = (hit[1], -hit[2], hit[0])
    info['worst'] = worst
    info['tol'] = tol
    return info


def load_datasheets():
    """tools/cpl_datasheets.yaml, with pins filled from a `pinout_csv` where given."""
    records = load_yaml(DATASHEETS) or {}
    for record in records.values():
        if record.get('pinout_csv'):
            with open(os.path.join(ROOT, record['pinout_csv'])) as handle:
                rows = [line.strip().split(',') for line in handle if re.match(r'\d+,', line)]
            record['pins'] = {r[0]: r[1] for r in rows}
    return records


def fetch_datasheets(args):
    """Download each recorded datasheet (build/cpl-datasheets/<LCSC>.pdf),
    save the text of the recorded page and a PNG crop of its drawing."""
    import urllib.request
    from PIL import Image
    os.makedirs(CACHE, exist_ok=True)
    for lcsc, record in sorted(load_datasheets().items()):
        pdf = os.path.join(CACHE, lcsc + '.pdf')
        if not record.get('page'):
            continue
        if not os.path.exists(pdf) or open(pdf, 'rb').read(4) != b'%PDF':
            url = record['url']
            if url.startswith('hw/'):
                data = open(os.path.join(ROOT, url), 'rb').read()
            else:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.lcsc.com/'})
                    data = urllib.request.urlopen(req, timeout=90).read()
                except Exception as error:      # noqa: BLE001
                    print('%s: download failed (%s)' % (lcsc, error))
                    continue
            if data[:4] != b'%PDF':
                print('%s: %s did not return a PDF' % (lcsc, url))
                continue
            with open(pdf, 'wb') as handle:
                handle.write(data)
        page = str(record['page'])
        text = subprocess.run(['nice', '-n', '19', 'pdftotext', '-f', page, '-l', page, '-layout', pdf, '-'],
                              capture_output=True, text=True).stdout
        with open(os.path.join(CACHE, lcsc + '.txt'), 'w') as handle:
            handle.write(text)
        if record.get('crop'):
            prefix = os.path.join(CACHE, lcsc + '-page')
            subprocess.run(['nice', '-n', '19', 'pdftoppm', '-f', page, '-l', page, '-r', '130', '-png', '-singlefile', pdf, prefix],
                           check=True, capture_output=True)
            image = Image.open(prefix + '.png')
            w, h = image.size
            x0, y0, x1, y1 = record['crop']
            image.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))).save(os.path.join(CACHE, lcsc + '-crop.png'))
        print('%s: page %s saved' % (lcsc, page))


def exposed_free(pads):
    """The pads that form the numbered ring: an exposed pad (area more than 3x
    the median) is left out of the numbering check."""
    areas = sorted(p['w'] * p['h'] for p in pads)
    median = areas[len(areas) // 2]
    numbers = [p['n'] for p in pads]
    return [p for p in pads if p['w'] * p['h'] <= 3 * median and numbers.count(p['n']) == 1]


def datasheet_text_names(lcsc, record, kicad_names):
    """Which of the KiCad pin names (ignoring pad-number-like ones) are not
    found as text on the recorded datasheet page(s); None when the page text
    was not fetched (run the `datasheets` command)."""
    text_path = os.path.join(CACHE, '%s.txt' % lcsc)
    if not record or not os.path.exists(text_path):
        return None
    with open(text_path, errors='replace') as handle:
        text = re.sub(r'[^A-Z0-9]', '', handle.read().upper())
    wanted = sorted({t for name in kicad_names.values() for t in auto.tokens(name)
                     if not re.fullmatch(r'[A-Z]?\d+', t) and len(t) > 1})
    missing = [t for t in wanted if t not in text]
    return {'total': len(wanted), 'missing': missing}


def auto_checks(info, row, fact, turn_table, net_pins, datasheets):
    """The non-human checks, in order: CPL rotation, polarity, pin names,
    pad geometry, datasheet. Sets info['checks'] and info['auto'] ('bad',
    'human' or 'verified')."""
    checks = []
    lcsc = row['lcsc_part']
    cpl = row['cpl']
    pads = fact['pads']
    info['checks'] = checks
    turn = turn_table.get(fact['fpid'])
    if turn is None:
        checks.append(auto.check('CPL rotation', 'unknown', 'no entry in hw/parts/jlc_rotation.yaml'))
    else:
        want = (fact['rot'] + turn['rotation']) % 360
        ok = abs((want - info['cpl_rot'] + 180) % 360 - 180) <= 0.01
        checks.append(auto.check('CPL rotation', 'pass' if ok else 'fail',
                                 'CPL %.0f = KiCad %.0f + package correction %s' % (info['cpl_rot'], fact['rot'], turn['rotation'])))
    easyeda = info.get('easyeda')
    table = load_yaml(os.path.join(PARTS, lcsc + '.yaml')) or {}
    if easyeda is None or not pads:
        checks.append(auto.check('pad geometry', 'unknown', 'no EasyEDA record: JLC\'s footprint is not known'))
        info['auto'] = 'human'
        return
    kicad_names = {p['n']: info['names'][p['n']] for p in pads}
    jlc_names = {str(k): str(v) for k, v in easyeda['pins'].items()}
    mid_x, mid_y = float(cpl['Mid X'][:-2]), float(cpl['Mid Y'][:-2])
    theirs = auto.jlc_world([(str(n), x, y) for n, x, y in easyeda['pads']], info['cpl_rot'], mid_x, mid_y)
    ours = {}
    for p in pads:
        ours[auto.unique_key(ours, p['n'])] = (p['x'], p['y'])
    polar = bool(info.get('polar'))
    if polar:
        checks.append(auto.polarity(ours, kicad_names, theirs, jlc_names))
    else:
        checks.append(auto.check('polarity', 'na', 'not a K/A part'))
    if polar:
        checks.append(auto.check('pin names', 'na', 'K/A parts compared by function in the polarity check'))
    else:
        checks.append(auto.pin_names(kicad_names, jlc_names))
    tol = table.get('pad_tolerance') or TOLERANCE
    geometry, _ = auto.geometry(ours, theirs, kicad_names, jlc_names, polar=polar,
                                by_nearest=bool(table.get('interchangeable_pins')), tol=tol)
    checks.append(geometry)
    record = (datasheets or {}).get(lcsc)
    ring = {p['n']: (p['fx'], p['fy']) for p in exposed_free(pads)}
    checks.append(auto.datasheet_check(record, ring, kicad_names, datasheet_text_names(lcsc, record, kicad_names)))
    info['datasheet'] = record
    info['lcsc_for_ds'] = lcsc
    by_name = {c['name']: c for c in checks}
    if by_name['pin names']['status'] == 'fail' and by_name['datasheet']['status'] == 'pass':
        by_name['pin names']['detail'] += (' NOTE: our KiCad names agree with the manufacturer datasheet/pinout record, so the difference is in JLC\'s '
                                            'EasyEDA symbol names (harmless to assembly if only the labels are wrong, but it is a real disagreement in JLC\'s data).')
    if any(c['status'] == 'fail' for c in checks):
        info['auto'] = 'bad'
    elif all(c['status'] in ('pass', 'na') for c in checks):
        info['auto'] = 'verified'
    elif (by_name['pin names']['status'] == 'unknown' and by_name['datasheet']['status'] == 'pass'
          and all(c['status'] in ('pass', 'na') for c in checks if c['name'] != 'pin names')):
        info['auto'] = 'verified'       # JLC's symbol only numbers the pads; the datasheet leg covers the names
    else:
        info['auto'] = 'human'


def jlc_note(info):
    """The JLC rotation-convention note for the part's package, or a plain
    statement that it is unknown. Nothing here is guessed: it is what
    hw/parts/jlc_rotation.yaml and hw/parts/easyeda/<LCSC>.yaml record."""
    easyeda, turn = info['easyeda'], info['turn']
    if easyeda is None and turn is None:
        return 'UNKNOWN. No hw/parts/jlc_rotation.yaml entry and no EasyEDA record: nothing recorded on how JLC turns this package.'
    lines = []
    if easyeda:
        pad1 = next((p for p in easyeda['pads'] if str(p[0]) == '1'), None)
        lines.append('JLC package %s; JLC places EasyEDA footprint %s.' % (easyeda['jlc_package'] or '(none)', easyeda['easyeda_footprint']))
        if pad1:
            lines.append('In that footprint at 0 deg (x right, y up) pin 1 is at (%.2f, %.2f) mm.' % (pad1[1], pad1[2]))
    else:
        lines.append('UNKNOWN: no EasyEDA record, so JLC\'s footprint is not known.')
    if turn:
        lines.append('CPL angle = KiCad angle %.0f + package correction %s = %.0f%s. Source: %s'
                     % (info['kicad_rot'], turn['rotation'], info['cpl_rot'],
                        '; JLC origin offset %s mm' % (turn['offset'],) if turn.get('offset') else '', turn.get('source', 'none recorded')))
    else:
        lines.append('UNKNOWN: this KiCad footprint has no correction recorded in jlc_rotation.yaml.')
    lines.append('Convention used (bomcheck.py): JLC turns its footprint counterclockwise by the CPL angle, seen from the top. '
                 'Derived from EasyEDA pad data, not verified against JLC\'s own placement preview.')
    return ' '.join(lines)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#fff;--fg:#1b1f24;--mut:#59636e;--line:#d0d7de;--bad:#cf222e;--chk:#9a6700;--ok:#1a7f37;--cx:#6639ba;--rs:#0a7d8c}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--line:#30363d;--bad:#ff7b72;--chk:#e3b341;--ok:#56d364;--cx:#a371f7;--rs:#39c5cf}}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0 auto;padding:16px;max-width:1500px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 6px}
.warn{border:2px solid var(--bad);padding:8px 12px;margin:10px 0;border-radius:6px}
.mut{color:var(--mut)}code{font-size:12px}
table{border-collapse:collapse;width:100%}
td,th{border:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
th{position:sticky;top:0;background:var(--bg)}
td.sign{white-space:nowrap;min-width:150px}
td.sign label{display:block}td.sign input[type=text]{width:140px;margin-top:4px}
.print-only{display:none}
.bad{color:var(--bad);font-weight:600}.check{color:var(--chk);font-weight:600}.good{color:var(--ok)}
.ref{font-size:18px;font-weight:700}
.badge{background:var(--ok);color:#fff;padding:1px 8px;border-radius:10px;font-weight:700}
.badge.cx{background:var(--cx)}
.badge.rs{background:var(--rs)}
.resolved-text{border:1px solid var(--rs);border-radius:6px;padding:4px 8px;margin:4px 0;font-size:12px;font-weight:400;color:var(--fg)}
tr.resolved td:first-child{border-left:4px solid var(--rs)}
.codex{border:1px solid var(--cx);border-radius:6px;padding:4px 8px;margin-top:6px;font-size:12px}
.codex.problem,.codex.unanswered{border-color:var(--bad)}
.codex summary{cursor:pointer}
li.c-pass{color:var(--ok)}li.c-fail{color:var(--bad)}li.c-unknown{color:var(--chk)}ul.flags{list-style:none;padding-left:0}
tr.verified td{opacity:.92}
tr.codex-verified td:first-child{border-left:4px solid var(--cx)}
ul.flags{margin:4px 0 0;padding-left:18px}
.pic svg{width:360px;height:auto;max-height:340px;background:#0a0f1a;border:1px solid var(--line)}
.bar{position:sticky;top:0;background:var(--bg);padding:6px 0;border-bottom:1px solid var(--line);z-index:2}
button,input[type=text]{font:inherit}
@media print{.screen-only,.bar{display:none}.print-only{display:block}body{max-width:none;font-size:11px}tr{break-inside:avoid}.pic svg{width:300px}}
"""

JS = """
const KEY = 'cpl-pack:' + PACK.board + ':' + PACK.id;
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
function count() {
  const n = PACK.refs.length;
  const ok = PACK.refs.filter(r => state[r] && state[r].decision === 'ok').length;
  const other = PACK.refs.filter(r => state[r] && state[r].decision && state[r].decision !== 'ok').length;
  document.getElementById('progress').textContent = ok + ' OK, ' + other + ' wrong/unsure, ' + (n - ok - other) + ' undecided of ' + n;
}
// parts David resolved in tools/cpl_resolutions.yaml: OK plus the justification as the note, unless already decided here
for (const ref of Object.keys(PACK.resolved || {})) {
  if (!(state[ref] && state[ref].decision)) state[ref] = Object.assign(state[ref] || {}, {decision: 'ok', note: 'RESOLVED by David (tools/cpl_resolutions.yaml): ' + PACK.resolved[ref]});
}
for (const ref of PACK.refs) {
  const s = state[ref] || {};
  for (const radio of document.querySelectorAll('input[name="d-' + ref + '"]')) {
    radio.checked = radio.value === s.decision;
    radio.addEventListener('change', () => { state[ref] = Object.assign(state[ref] || {}, {decision: radio.value}); save(); count(); });
  }
  const note = document.getElementById('n-' + ref);
  note.value = s.note || '';
  note.addEventListener('input', () => { state[ref] = Object.assign(state[ref] || {}, {note: note.value}); save(); });
}
const reviewer = document.getElementById('reviewer');
try { reviewer.value = localStorage.getItem('cpl-pack:reviewer') || ''; } catch (e) {}
reviewer.addEventListener('input', () => { try { localStorage.setItem('cpl-pack:reviewer', reviewer.value); } catch (e) {} });
document.getElementById('dl').addEventListener('click', () => {
  const decisions = {};
  for (const ref of PACK.refs) decisions[ref] = {decision: (state[ref] || {}).decision || '', note: (state[ref] || {}).note || ''};
  const doc = {pack: 'cpl-review-pack', board: PACK.board, pack_id: PACK.id, reviewer: reviewer.value,
               sha256: PACK.sha256, decisions: decisions};
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2) + '\\n'], {type: 'application/json'}));
  a.download = PACK.board + '-decisions.json';
  a.click();
});
function tickAll(refs) {
  for (const ref of refs) {
    state[ref] = Object.assign(state[ref] || {}, {decision: 'ok'});
    for (const radio of document.querySelectorAll('input[name="d-' + ref + '"]')) radio.checked = radio.value === 'ok';
  }
  save(); count();
}
document.getElementById('tickauto').addEventListener('click', () => tickAll(PACK.verified));
document.getElementById('tickcodex').addEventListener('click', () => tickAll(PACK.codex));
count();
"""


def circle(x, y, r, colour, dash=''):
    return ('<circle cx="%.3f" cy="%.3f" r="%.3f" fill="none" stroke="%s" stroke-width="0.14"%s/>'
            % (x, y, r, colour, ' stroke-dasharray="0.3 0.2"' if dash else ''))


def closeup(info, origin):
    """A crop of the board plot around the part, with pad 1 (lime) and where
    JLC's footprint puts pin 1 (orange, dashed) marked."""
    ox, oy = origin
    x0, y0, x1, y1 = info['pad_box']
    x0, y0, x1, y1 = x0 - ox, y0 - oy, x1 - ox, y1 - oy
    pad = 1.6
    w, h = max(x1 - x0 + 2 * pad, 6.0), max(y1 - y0 + 2 * pad, 6.0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    view = '%.3f %.3f %.3f %.3f' % (cx - w / 2, cy - h / 2, w, h)
    key = info['key_pad']
    kx, ky = key['x'] - ox, key['y'] - oy
    radius = max(0.45, min(key['w'], key['h']) * 0.8)
    label = (min(w, h) / 22)
    marks = [circle(kx, ky, radius, '#39ff14'),
             '<text x="%.3f" y="%.3f" font-size="%.3f" fill="#39ff14" font-weight="bold">%s</text>'
             % (kx + radius, ky - radius, label * 1.6, html.escape('K' if info.get('polar') else key['n']))]
    if info.get('polar'):
        other = next(p for p in info['pads_all'] if p is not key)
        marks.append('<text x="%.3f" y="%.3f" font-size="%.3f" fill="#39ff14">A</text>'
                     % (other['x'] - ox + 0.3, other['y'] - oy - 0.5, label * 1.4))
    if info['predicted']:
        px, py, name = info['predicted']
        marks.append(circle(px - ox, py - oy, radius + 0.22, '#ff9f1c', dash=True))
    # 1 mm scale bar
    marks.append('<rect x="%.3f" y="%.3f" width="1" height="%.3f" fill="#fff"/>' % (cx - w / 2 + 0.3, cy + h / 2 - 0.6, label * 0.4))
    marks.append('<text x="%.3f" y="%.3f" font-size="%.3f" fill="#fff">1 mm</text>' % (cx - w / 2 + 1.4, cy + h / 2 - 0.35, label))
    return ('<svg viewBox="%s" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="%s close-up">'
            '<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" fill="#0a0f1a"/><use href="#board"/>%s</svg>'
            % (view, html.escape(info['ref']), cx - w / 2, cy - h / 2, w, h, ''.join(marks)))


def codex_block(codex):
    look = ('<div><b>Look at:</b> %s</div>' % html.escape(codex['look_at'])) if codex.get('look_at') else ''
    links = ''.join('<div><a href="%s">%s</a></div>' % (html.escape(u), html.escape(u[:70])) for u in codex.get('sources', []))
    verdict = codex['verdict']
    what = {'fine': 'fine', 'check': 'probably fine, confirm in the JLC preview', 'problem': 'PROBLEM: stays with you',
            'unanswered': 'no usable answer: stays with you'}[verdict]
    return ('<div class="codex %s"><b>Codex (%s): %s.</b> Language-model second opinion, NOT a datasheet or JLC check; it did not see JLC\'s preview.%s%s'
            '<details><summary>Codex\'s text</summary><div style="white-space:pre-wrap">%s</div></details></div>'
            % (verdict, html.escape(codex['model']), what, look, links, html.escape(codex['summary'])))


def part_row(info, origin):
    ref = html.escape(info['ref'])
    flags = ''.join('<li class="%s">%s</li>' % (sev, html.escape(text)) for sev, text in info['flags'])
    klass = info['class']
    verdict = {'bad': 'bad', 'human': 'check', 'verified': 'good', 'codex-verified': 'good', 'resolved': 'resolved'}[klass]
    tag = {'bad': 'MISMATCH: needs your decision', 'human': 'NEEDS YOU: could not be fully checked automatically'}.get(klass)
    if klass == 'verified':
        tag = '<span class="badge">AUTO-VERIFIED</span> ' + html.escape(', '.join(
            c['name'] for c in info['checks'] if c['status'] == 'pass'))
    elif klass == 'codex-verified':
        tag = ('<span class="badge cx">AUTO-VERIFIED (CODEX)</span> the tool checks passed except the datasheet leg; a language model '
               'said fine (verdict: %s)' % html.escape(info['codex']['verdict']))
    elif klass == 'resolved':
        res = info['resolution']
        tag = ('<span class="badge rs">RESOLVED: FINE (David)</span> %s, %s. Justification, verbatim:'
               '<div class="resolved-text">%s</div><div class="mut">Original findings stay below: the tool result was <b>%s</b>.</div>'
               % (html.escape(res['by']), html.escape(res['date']), html.escape(res['justification']), html.escape(info['auto'])))
    else:
        tag = html.escape(tag)
    if info.get('codex'):
        tag += codex_block(info['codex'])
    checks = ''.join('<li class="c-%s"><b>%s %s</b>: %s</li>' % (c['status'], html.escape(c['name']), c['status'].upper(),
                                                              html.escape(c['detail'])) for c in info['checks'] if c['status'] != 'na')
    sheet = ''
    record = info.get('datasheet')
    if record and record.get('url'):
        crop = os.path.join(CACHE, info['lcsc'] + '-crop.png')
        image = ''
        if os.path.exists(crop):
            import base64
            with open(crop, 'rb') as handle:
                image = '<img alt="datasheet drawing" style="max-width:360px;width:100%%" src="data:image/png;base64,%s">' % base64.b64encode(handle.read()).decode()
        sheet = ('<div class="mut">Datasheet: <a href="%s">%s</a>, page %s%s</div>%s'
                 % (html.escape(record['url']), html.escape(record['url'][-48:]), html.escape(str(record.get('page', '?'))),
                    '' if image else ' (crop not saved: run the datasheets command)', image))
    elif record:
        sheet = '<div class="mut">Datasheet: none available (%s)</div>' % html.escape(record.get('why', ''))
    place = ('<div>board (%.2f, %.2f) mm, KiCad %.0f deg</div><div>CPL <code>%s, %s</code>, <b>rotation %.0f</b></div>'
             % (info['board_x'], info['board_y'], info['kicad_rot'], html.escape(info['cpl_x']),
                html.escape(info['cpl_y']), info['cpl_rot']))
    pin1 = '<div><b>%s</b></div><div>%s</div>' % (html.escape(info.get('where', 'no pads')), html.escape(info.get('frame', '')))
    if info.get('polar'):
        pin1 += '<div class="bad">Polarised: %s</div>' % html.escape(info['polar'])
    if info['predicted']:
        pin1 += ('<div>JLC puts its pad %s at the orange dashed ring (KiCad pad %s = lime ring); largest pad disagreement %.2f mm (limit %.2f).</div>'
                 % (html.escape(info['predicted'][2]), html.escape(info['key_pad']['n']), info['worst'], info['tol']))
    if info.get('match_note'):
        pin1 += '<div class="mut">%s</div>' % html.escape(info['match_note'])
    sign = ('<td class="sign"><div class="screen-only">'
            '<label><input type="radio" name="d-%(r)s" value="ok"> OK</label>'
            '<label><input type="radio" name="d-%(r)s" value="wrong"> Wrong, needs fix</label>'
            '<label><input type="radio" name="d-%(r)s" value="unsure"> Unsure</label>'
            '<input type="text" id="n-%(r)s" placeholder="note"></div>'
            '<div class="print-only">[&nbsp;&nbsp;] OK<br>[&nbsp;&nbsp;] Wrong<br>[&nbsp;&nbsp;] Unsure<br><br>note:<br><br></div></td>'
            % {'r': ref})
    return ('<tr id="p-%s" class="%s"><td><div class="ref">%s</div>%s<div>%s</div><div>%s</div><div><code>%s</code></div>'
            '<div class="%s">%s</div><ul class="flags">%s</ul><ul class="flags">%s</ul></td>'
            '<td>%s</td><td>%s</td><td>%s</td><td class="pic">%s%s</td>%s</tr>'
            % (ref, info['class'], ref, html.escape(info['value']), html.escape(info['lcsc']), html.escape(info['footprint']),
               html.escape(info['fpid']), verdict, tag, flags, checks, place, pin1, html.escape(jlc_note(info)),
               closeup(info, origin), sheet, sign))


def board_page(board, infos, board_svg, origin, hashes, pack_id, generated):
    refs = [i['ref'] for i in infos]
    pack = {'board': board, 'id': pack_id, 'refs': refs, 'sha256': hashes}
    rows = '\n'.join(part_row(info, origin) for info in infos)
    counts = {k: sum(1 for i in infos if i['class'] == k) for k in ('verified', 'codex-verified', 'resolved', 'human', 'bad')}
    pack['resolved'] = {i['ref']: i['resolution']['justification'] for i in infos if i['class'] == 'resolved'}
    pack['verified'] = [i['ref'] for i in infos if i['class'] == 'verified']
    pack['codex'] = [i['ref'] for i in infos if i['class'] == 'codex-verified']
    flagged = counts['human'] + counts['bad']
    hash_lines = '\n'.join('%s  %s' % (digest, name) for name, digest in hashes.items())
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CPL review %(board)s</title><style>%(css)s</style></head><body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><g id="board">%(svg)s</g></defs></svg>
<h1>CPL review: %(board)s board, %(n)d parts</h1>
<div class="warn"><b>Unsigned. Regenerate after the board rebuild.</b> This sheet was built %(generated)s from the
build/hw/%(board)s files below, as they were. Any rebuild changes them: the sign helper then refuses this sheet.
Nothing here is a sign-off; the tool checks below are aids, and the receipt is yours.<pre>%(hashes)s</pre></div>
<p>The %(n)d placements listed are the ones a wrong rotation breaks: ICs, connectors, diodes and LEDs, transistors,
crystals, switches and resistor networks (tools/cpl_focus.py). Two-terminal R, C, L and F parts are not here: they work
either way round. Sorted by risk: tool flags first, then ICs, connectors, polarised, transistors, crystals, switches, networks.
<b>%(nv)d auto-verified (tool), %(nc)d auto-verified (Codex), %(nr)d resolved by David, %(nh)d need you, %(nb)d mismatch.</b></p>
<div class="warn" style="border-color:var(--cx)"><b>AUTO-VERIFIED (CODEX) is a language-model second opinion, not a datasheet or JLC check.</b>
Codex (%(model)s) was asked one question per part type, from facts only (LCSC number, package, JLC's EasyEDA pad data, what our footprint does, what the
checks could not settle). It did not see JLC's preview or the datasheet drawing, and it can be wrong. Parts it called fine (or fine with one thing to confirm in JLC's
preview) carry the purple badge with its "look at" note and links; parts where it found a problem, disagreed with the tool checks or gave no answer stay
with you at the top. Its answer is never a tick: the sign helper still needs every part ticked by you.</div>
<div class="warn"><b>What "auto-verified" means and does not.</b> The automatic checks compare our footprint (KiCad pads, symbol pin names, CPL row)
with the EasyEDA footprint and symbol JLC publishes for the LCSC part, and with the manufacturer datasheet drawing (pin names at each pad and the
numbering direction, transcribed from the PDF page shown in the close-up column and compared by code). <b>Nothing here proves JLC's own 3D preview or its
pick-and-place agrees</b>: it is the same EasyEDA data JLC uses, not JLC's placement. Auto-verified parts still need your tick (the sign helper
requires every part OK) but you can skim them: the button below only ticks the parts the tool verified, and it is your click.</div>
<p><b>Close-up key:</b> lime ring = pad 1 (K for the cathode of a polarised part) as the KiCad footprint on the board defines it;
orange dashed ring = where JLC's own footprint puts that pin when turned by the CPL rotation. They should sit on the same pad. Judge the
picture against the part's datasheet and the actual silk pin-1 mark; the rings only show the numbers.</p>
<div class="bar screen-only">Reviewer <input type="text" id="reviewer" placeholder="your name">
<button id="dl">Download decisions</button> <button id="tickauto" title="ticks OK on the tool-verified parts only">Tick the auto-verified as OK</button>
<button id="tickcodex" title="ticks OK on the codex-verified parts only (a language-model opinion)" style="border-color:var(--cx)">Tick codex-verified as OK</button> <span id="progress"></span>
<span class="mut"> (ticks are kept in this browser; download the file and run <code>tools/cpl_review_pack.py sign</code>)</span></div>
<table><thead><tr><th>Part</th><th>Placement</th><th>Pin 1 / polarity (footprint)</th>
<th>JLC rotation convention</th><th>Close-up</th><th>Sign-off</th></tr></thead><tbody>
%(rows)s
</tbody></table>
<script>const PACK = %(pack)s;
%(js)s</script></body></html>
""" % {'board': board, 'css': CSS, 'svg': board_svg, 'n': len(infos), 'generated': generated, 'hashes': html.escape(hash_lines),
       'flagged': flagged, 'nv': counts['verified'], 'nc': counts['codex-verified'], 'nr': counts['resolved'], 'nh': counts['human'], 'nb': counts['bad'], 'model': cpl_codex.MODEL, 'rows': rows, 'pack': json.dumps(pack), 'js': JS}


# ---------------------------------------------------------------- build

def build(args):
    build_dir = os.path.abspath(args.build_dir)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    turn_table = load_yaml(os.path.join(PARTS, 'jlc_rotation.yaml')) or {}
    manifest, index_rows, total = {}, [], 0
    totals = {'verified': 0, 'codex-verified': 0, 'resolved': 0}
    answers = cpl_codex.load_answers()
    resolutions = cpl_codex.load_resolutions(RESOLUTIONS)
    known = {'%s/%s' % (b, r['designator']) for b in args.boards for r in focus_rows(build_dir, b)}
    for key in resolutions:
        if key.split('/')[0] in args.boards and key not in known:
            sys.exit('%s: resolution names a part that is not in the pack' % key)
    autos = {}
    datasheets = load_datasheets()
    generated = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    for board in args.boards:
        rows = focus_rows(build_dir, board)
        files = bound_files(build_dir, board)
        hashes = {name: sha256(path) for name, path in files.items()}
        pack_id = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:12]
        facts, outline = read_board(files[board + '.kicad_pcb'], [r['designator'] for r in rows])
        inner, origin = plot_board(files[board + '.kicad_pcb'], os.path.join(out, board + '.plot.svg'), outline)
        net_pins = netlist_pins(os.path.join(build_dir, board, board + '.net'))
        infos = []
        for row in rows:
            ref = row['designator']
            if ref not in facts:
                infos.append({'ref': ref, 'value': row['value'], 'lcsc': row['lcsc_part'], 'footprint': row['footprint'],
                              'fpid': '?', 'flags': [('bad', 'not on the pcb')], 'predicted': None, 'easyeda': None, 'turn': None,
                              'auto': 'bad', 'class': 'bad', 'codex': None, 'checks': [], 'kicad_rot': 0, 'cpl_rot': float(row['cpl']['Rotation']), 'cpl_x': row['cpl']['Mid X'],
                              'cpl_y': row['cpl']['Mid Y'], 'board_x': 0, 'board_y': 0, 'npads': 0})
                continue
            info = analyse(ref, row, facts[ref], turn_table, net_pins.get(ref, {}))
            auto_checks(info, row, facts[ref], turn_table, net_pins.get(ref, {}), datasheets)
            info['pads_all'] = facts[ref]['pads']
            infos.append(info)
        for i in infos:
            if any(sev == 'bad' for sev, _ in i['flags']):
                i['auto'] = 'bad'
            elif i['flags'] and i['auto'] == 'verified':
                i['auto'] = 'human'
            key = cpl_codex.type_key(i['lcsc'], i['fpid'], (i.get('turn') or {}).get('rotation'))
            codex = answers.get(key) if i['auto'] != 'verified' else None
            i['codex'] = {k: codex[k] for k in ('verdict', 'summary', 'look_at', 'sources', 'model', 'timestamp')} if codex else None
            i['resolution'] = resolutions.get('%s/%s' % (board, i['ref']))
            i['class'] = cpl_codex.classify(i['auto'], i['codex'], i['resolution'])
        infos.sort(key=lambda i: ({'bad': 0, 'human': 1, 'resolved': 2, 'codex-verified': 3, 'verified': 4}[i['class']],
                                  rank({'designator': i['ref']}), -i['npads'], natural(i['ref'])))
        drawable = [i for i in infos if 'pad_box' in i]
        missing = [i['ref'] for i in infos if 'pad_box' not in i]
        if missing:
            print('%s: no pads/pcb data for %s' % (board, missing), file=sys.stderr)
        with open(os.path.join(out, board + '.html'), 'w') as handle:
            handle.write(board_page(board, drawable, inner, origin, hashes, pack_id, generated))
        os.remove(os.path.join(out, board + '.plot.svg'))
        manifest[board] = {'pack_id': pack_id, 'generated': generated, 'sha256': hashes,
                           'refs': sorted((i['ref'] for i in drawable), key=natural)}
        autos[board] = {i['ref']: {'lcsc': i['lcsc'], 'auto': i['auto'], 'class': i['class'],
                                   **({'codex': i['codex']} if i['codex'] else {}),
                                   **({'resolution': i['resolution']} if i['resolution'] else {}),
                                   'checks': [{k: c[k] for k in ('name', 'status', 'detail')} for c in i['checks']],
                                   'facts': {'value': i['value'], 'footprint': i['footprint'], 'fpid': i['fpid'],
                                             'kicad_rot': i['kicad_rot'], 'cpl_rot': i['cpl_rot'],
                                             'correction': (i.get('turn') or {}).get('rotation'),
                                             'where': i.get('where', ''), 'polar': i.get('polar', '')}}
                        for i in sorted(drawable, key=lambda i: natural(i['ref']))}
        n = {k: sum(1 for i in drawable if i['class'] == k) for k in ('verified', 'codex-verified', 'resolved', 'human', 'bad')}
        total += len(drawable)
        totals['verified'] += n['verified']
        totals['codex-verified'] += n['codex-verified']
        totals['resolved'] += n['resolved']
        index_rows.append('<tr><td><a href="%s.html">%s</a></td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td></tr>'
                          % (board, board, len(drawable), n['verified'], n['codex-verified'], n['resolved'], n['human'], n['bad']))
        print('%s: %d parts, %d auto-verified, %d codex-verified, %d resolved by David, %d need you, %d mismatch'
              % (board, len(drawable), n['verified'], n['codex-verified'], n['resolved'], n['human'], n['bad']))
    with open(os.path.join(out, 'manifest.json'), 'w') as handle:
        json.dump(manifest, handle, indent=2)
        handle.write('\n')
    with open(os.path.join(out, 'auto-checks.json'), 'w') as handle:
        json.dump(autos, handle, indent=1)
        handle.write('\n')
    with open(os.path.join(out, 'index.html'), 'w') as handle:
        handle.write('<!doctype html><meta charset="utf-8"><title>CPL review pack</title><style>%s</style>'
                     '<h1>CPL review pack: %d parts</h1><div class="warn"><b>Unsigned. Built %s from build/hw as it was: '
                     'regenerate after the board rebuild.</b></div><div class="warn">Auto-verified = the tool compared our footprint with the EasyEDA/JLC data and the datasheet drawing. '
                     '<b>It does not prove JLC\'s own 3D preview or pick-and-place agrees.</b> Nothing is signed.</div>'
                     '<div class="warn" style="border-color:var(--cx)">Auto-verified (Codex) = a language-model second opinion (%s) on parts the tool could not settle; not a datasheet or JLC check, it did not see JLC\'s preview.</div>'
                     '<table><tr><th>Board</th><th>Parts</th><th>Auto-verified (tool)</th><th>Auto-verified (Codex)</th><th>Resolved by David</th><th>Need you</th><th>Mismatch</th></tr>%s</table>'
                     '<p>Tick each part on its sheet, press <i>Download decisions</i>, then '
                     '<code>python3 tools/cpl_review_pack.py sign &lt;board&gt;-decisions.json --reviewer "Name" --write</code>.</p>'
                     % (CSS, total, generated, cpl_codex.MODEL, ''.join(index_rows)))
    print('total %d parts, %d auto-verified, %d codex-verified, %d resolved -> %s/index.html' % (total, totals['verified'], totals['codex-verified'], totals['resolved'], out))


# ---------------------------------------------------------------- sign

def sign(args):
    pack = os.path.abspath(args.pack)
    with open(os.path.join(pack, 'manifest.json')) as handle:
        manifest = json.load(handle)
    build_dir = os.path.abspath(args.build_dir)
    date = args.date or datetime.date.today().isoformat()
    failed = False
    for path in args.decisions:
        with open(path) as handle:
            doc = json.load(handle)
        board = doc.get('board')
        problems = []
        entry = manifest.get(board)
        if entry is None:
            print('%s: board %r is not in the pack manifest' % (path, board))
            failed = True
            continue
        reviewer = (args.reviewer or '').strip()
        if not reviewer:
            problems.append('--reviewer NAME is required (the tool never picks one)')
        if doc.get('pack_id') != entry['pack_id']:
            problems.append('decisions come from another pack build (%s, manifest %s)' % (doc.get('pack_id'), entry['pack_id']))
        current = {name: sha256(p) for name, p in bound_files(build_dir, board).items()}
        for name, digest in current.items():
            if entry['sha256'].get(name) != digest:
                problems.append('STALE: %s changed since the pack was built: rebuild the pack and review again' % name)
        decisions = doc.get('decisions', {})
        for ref in entry['refs']:
            got = (decisions.get(ref) or {}).get('decision', '')
            if got != 'ok':
                problems.append('%s: %s' % (ref, got or 'undecided'))
        if problems:
            print('%s: NOT signed:' % board)
            print('  ' + '\n  '.join(problems))
            failed = True
            continue
        notes = args.notes or (
            'CPL review pack (tools/cpl_review_pack.py, built %s): the %d placements needing a pin-1/polarity look '
            '(ICs, connectors, diodes and LEDs, transistors, crystals, switches, resistor networks) each checked '
            'against the KiCad footprint pin 1 / polarity on the board, the JLC footprint and the CPL rotation; '
            'two-terminal non-polar R/C/L/F parts are rotation-insensitive and not reviewed one by one.'
            % (entry['generated'], len(entry['refs'])))
        remarks = ['%s: %s' % (ref, decisions[ref]['note']) for ref in entry['refs'] if (decisions[ref].get('note') or '').strip()]
        if remarks:
            notes += ' Notes: ' + '; '.join(remarks)
        receipt = {'board': board, 'reviewer': reviewer, 'reviewed_at': date, 'result': 'approved',
                   'notes': notes, 'sha256': current}
        target = os.path.join(build_dir, board, 'fab', 'cpl-review.json')
        if not args.write:
            print('%s: all %d parts OK and hashes current; dry run, would write %s:' % (board, len(entry['refs']), target))
            print(json.dumps(receipt, indent=2))
        elif os.path.exists(target) and not args.force:
            print('%s: %s exists; --force to replace' % (board, target))
            failed = True
        else:
            with open(target, 'w') as handle:
                json.dump(receipt, handle, indent=2)
                handle.write('\n')
            print('%s: wrote %s' % (board, target))
    sys.exit(1 if failed else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--build-dir', default=os.path.join(ROOT, 'build', 'hw'))
    common.add_argument('--out', default=os.path.join(ROOT, 'build', 'cpl-review-pack'))
    one = sub.add_parser('build', parents=[common])
    one.add_argument('--boards', nargs='+', choices=BOARDS, default=list(BOARDS))
    sub.add_parser('datasheets', parents=[common])
    two = sub.add_parser('sign', parents=[common])
    two.add_argument('decisions', nargs='+')
    two.add_argument('--reviewer')
    two.add_argument('--date')
    two.add_argument('--notes')
    two.add_argument('--write', action='store_true')
    two.add_argument('--force', action='store_true')
    args = parser.parse_args()
    if args.command == 'sign':
        args.pack = args.out
        sign(args)
    elif args.command == 'datasheets':
        fetch_datasheets(args)
    else:
        build(args)


if __name__ == '__main__':
    main()

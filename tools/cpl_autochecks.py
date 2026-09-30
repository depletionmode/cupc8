"""Non-human checks for the CPL review pack (tools/cpl_review_pack.py).

Pure functions on plain data so they are unit-testable (test/test_cpl_autochecks.py).
Coordinates: "board" frame is KiCad's (x right, y DOWN, seen from the top);
JLC/EasyEDA pad data is y UP and is turned counterclockwise by the CPL angle
about the placement point (the convention hw/tools/bomcheck.py uses).

Every check returns {'name', 'status', 'detail'} with status one of
'pass', 'fail', 'unknown' (the data to decide is missing: a human must) or
'na' (does not apply to this part).

Nothing here proves JLC's own 3D preview or pick-and-place agrees: these
checks compare our footprint with the EasyEDA footprint data JLC publishes.
"""

import math
import re

TOLERANCE = 0.2      # mm, bomcheck.PAD_TOLERANCE
POLAR = {'K': 'K', 'A': 'A', 'CATHODE': 'K', 'ANODE': 'A', '-': 'K', '+': 'A', 'C': 'K'}
# names two vendors write differently for the same pin (normalised, see norm)
ALIASES = {'SWDIO': 'SWD', 'VREGVIN': 'VREGIN', 'G': 'GND', 'VSS': 'GND', 'QSPISS': 'QSPISSN', 'CRESET': 'CRESETB', 'ENABLE': 'EN'}


def check(name, status, detail):
    return {'name': name, 'status': status, 'detail': detail}


def unique_key(table, number):
    """number, or number#2, number#3 ... when several pads share it."""
    key, k = str(number), 1
    while key in table:
        k += 1
        key = '%s#%d' % (number, k)
    return key


def jlc_world(jlc_pads, rotation, mid_x, mid_y_up, assembly_side="Top"):
    """{pad: (x, y down)} of EasyEDA's pads turned by the CPL rotation."""
    if assembly_side not in ("Top", "Bottom"):
        raise ValueError("assembly side must be Top or Bottom")
    angle = math.radians(rotation)
    out = {}
    for number, x, y in jlc_pads:
        if assembly_side == "Bottom":
            y = -y
        wx = mid_x + x * math.cos(angle) - y * math.sin(angle)
        wy = mid_y_up + x * math.sin(angle) + y * math.cos(angle)
        out[unique_key(out, number)] = (wx, -wy)
    return out


def side(point, others, axis_tol=0.05):
    """Where point lies among the others as seen from the top: 'left'/'right'
    when the pads are spread more in x, 'top'/'bottom' when spread in y."""
    xs = [p[0] for p in others]
    ys = [p[1] for p in others]
    if max(xs) - min(xs) >= max(ys) - min(ys):
        return 'left' if point[0] < sum(xs) / len(xs) else 'right'
    return 'top' if point[1] < sum(ys) / len(ys) else 'bottom'


def polar_function(name):
    return POLAR.get(name.split('_')[0].upper()) if name else None


def polarity(kicad_pos, kicad_names, jlc_pos, jlc_names, tol=TOLERANCE):
    """Which physical pad is the cathode in our footprint (by the KiCad symbol
    pin name) against which one is in JLC's footprint (EasyEDA pin name), both
    as placed. kicad_pos/jlc_pos {pad: (x, y)}; *_names {pad: pin name}."""
    kf = {n: polar_function(v) for n, v in kicad_names.items()}
    jf = {n: polar_function(v) for n, v in jlc_names.items()}
    if len(kicad_pos) != 2 or sorted(v or '?' for v in kf.values()) != ['A', 'K']:
        return check('polarity', 'na', 'not a two-pad K/A part')
    if sorted(v or '?' for v in jf.values()) != ['A', 'K']:
        return check('polarity', 'unknown', "JLC's symbol does not name the pads K and A (%s)" % jlc_names)
    ours = {kf[n]: n for n in kf}
    theirs = {jf[n]: n for n in jf}
    points = list(kicad_pos.values())
    described, agree = [], True
    for function, word in (('K', 'cathode'), ('A', 'anode')):
        mine, jlc = kicad_pos[ours[function]], jlc_pos[theirs[function]]
        mine_side, jlc_side = side(mine, points), side(jlc, points)
        gap = math.hypot(mine[0] - jlc[0], mine[1] - jlc[1])
        described.append('%s: KiCad pad %s (%s) on the %s, JLC pad %s (%s) on the %s, %.2f mm apart'
                         % (word, ours[function], kicad_names[ours[function]], mine_side,
                            theirs[function], jlc_names[theirs[function]], jlc_side, gap))
        agree = agree and mine_side == jlc_side and gap <= tol
    return check('polarity', 'pass' if agree else 'fail', '; '.join(described))


# ---------------------------------------------------------------- pin names

def norm(name):
    return re.sub(r'[^A-Z0-9]', '', name.upper())


def tokens(name):
    """A name like '~{WP}/IO_{2}' (KiCad) or 'HOLD#orRESET#(IO3)' (EasyEDA)
    as its alternative functions."""
    return [norm(t) for t in re.split(r'[/()#,]|(?<=#)or', name) if norm(t)]


def name_relation(kicad_name, jlc_name, pad):
    """'match' (same function, same words), 'alias' (a known spelling
    difference), 'generic' (one side names the pad, not the function: cannot
    be compared) or 'mismatch'."""
    k, j = norm(kicad_name), norm(jlc_name)
    if k == j or j in tokens(kicad_name) or (tokens(jlc_name) and set(tokens(jlc_name)) <= set(tokens(kicad_name))):
        return 'match'
    if ALIASES.get(k) == j or ALIASES.get(j) == k or any(ALIASES.get(t) == j for t in tokens(kicad_name)):
        return 'alias'
    generic = lambda s: bool(re.fullmatch(r'[A-Z]?\d+', norm(s))) or bool(re.fullmatch(r'R\d+\.\d', s))
    if generic(jlc_name) or generic(kicad_name):
        return 'generic'
    return 'mismatch'


def pin_names(kicad_names, jlc_names):
    """Every pad's KiCad symbol pin name against JLC's EasyEDA symbol name for
    the same pad number (K/A parts are compared by function in polarity())."""
    counts = {'match': 0, 'alias': 0, 'generic': 0, 'mismatch': 0}
    bad, generic = [], []
    for pad in sorted(kicad_names, key=natural):
        other = jlc_names.get(pad)
        if other is None:
            bad.append('pad %s: KiCad %r, JLC has no such pin' % (pad, kicad_names[pad]))
            counts['mismatch'] += 1
            continue
        relation = name_relation(kicad_names[pad], other, pad)
        counts[relation] += 1
        if relation == 'mismatch':
            bad.append('pad %s: KiCad %r vs JLC %r' % (pad, kicad_names[pad], other))
        elif relation == 'generic':
            generic.append(pad)
    total = len(kicad_names)
    summary = '%d/%d same name, %d known alias, %d not comparable (a side names the pad, not the function), %d mismatch' % (
        counts['match'], total, counts['alias'], counts['generic'], counts['mismatch'])
    if bad:
        return check('pin names', 'fail', summary + ': ' + '; '.join(bad[:8]) + ('; ...' if len(bad) > 8 else ''))
    if counts['generic']:
        # not a failure: JLC's data simply has no function names for these pads
        return check('pin names', 'unknown' if counts['generic'] == total else 'pass',
                     summary + ' (JLC\'s symbol only numbers these pads)' if counts['generic'] == total else summary)
    return check('pin names', 'pass', summary)


def natural(text):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', str(text))]


# ---------------------------------------------------------------- geometry

def geometry(kicad_pos, jlc_pos, kicad_names=None, jlc_names=None, polar=False, by_nearest=False, tol=TOLERANCE):
    """Pad for pad: every KiCad pad against JLC's pad of the same number (of
    the same K/A function for a polar part; the nearest pad for interchangeable
    ones), after the CPL rotation. Reports the largest deviation. Pads that
    share a number (shell tabs) are keyed 'n', 'n#2', ...: each is paired with
    the nearest JLC pad of that number."""
    worst, worst_pad, problems = 0.0, None, []
    base = lambda key: key.split('#')[0]
    if polar:
        jf = {polar_function(v): n for n, v in jlc_names.items()}
        pairs = {n: jf.get(polar_function(kicad_names[n])) for n in kicad_pos}
    elif by_nearest:
        pairs = {n: min(jlc_pos, key=lambda m: math.dist(jlc_pos[m], p)) for n, p in kicad_pos.items()}
    else:
        pairs = {}
        for n, p in kicad_pos.items():
            same = [m for m in jlc_pos if base(m) == base(n)]
            pairs[n] = min(same, key=lambda m: math.dist(jlc_pos[m], p)) if same else None
    for pad, other in pairs.items():
        if other is None:
            problems.append('KiCad pad %s has no counterpart in JLC\'s footprint' % pad)
            continue
        gap = math.dist(kicad_pos[pad], jlc_pos[other])
        if gap > worst:
            worst, worst_pad = gap, pad
        if gap > tol + 1e-6:
            problems.append('pad %s is %.3f mm from JLC\'s pad %s' % (pad, gap, other))
    extra = sorted(set(jlc_pos) - set(pairs.values()), key=natural)
    if extra and not by_nearest:
        problems.append('JLC has pad(s) %s that KiCad does not' % ', '.join(extra[:6]))
    summary = 'all %d pads pad-for-pad within %.2f mm; largest deviation %.3f mm%s' % (
        len(kicad_pos), tol, worst, ' (pad %s)' % worst_pad if worst_pad else '')
    if problems:
        return check('pad geometry', 'fail', '; '.join(problems[:6]) + '. Largest deviation %.3f mm' % worst), worst
    return check('pad geometry', 'pass', summary), worst


# ---------------------------------------------------------------- numbering

def numbering_direction(pads):
    """'ccw' or 'cw' (seen from the top) for pads numbered 1..N around a
    package, or None when the pads do not form a ring/two rows (single row,
    staggered connector, non-numeric). pads: {number: (x, y down)}; the
    caller leaves out an exposed pad or a mechanical one."""
    numbered = {int(n): p for n, p in pads.items() if n.isdigit()}
    if len(numbered) < 3 or len(numbered) != len(pads):
        return None
    ordered = [numbered[n] for n in sorted(numbered)]
    area = 0.0
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:] + ordered[:1]):
        area += x0 * (-y1) - x1 * (-y0)          # y flipped: up
    span = max(math.dist(a, b) for a in ordered for b in ordered)
    if abs(area) / 2 < 0.02 * span * span:
        return None
    return 'ccw' if area > 0 else 'cw'


def pin1_corner(pads):
    """Where pad 1 lies among the pad field in the KiCad footprint as drawn
    (0 deg placement is not assumed: pass footprint-relative positions)."""
    if '1' not in pads:
        return None
    xs = [p[0] for p in pads.values()]
    ys = [p[1] for p in pads.values()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    dx, dy = pads['1'][0] - cx, pads['1'][1] - cy
    if math.hypot(dx, dy) < 0.05:
        return 'centre'
    return ('top' if dy < -0.05 else 'bottom' if dy > 0.05 else '') + ('-left' if dx < -0.05 else '-right' if dx > 0.05 else '')


def datasheet_check(record, kicad_pads_fp, kicad_names=None, names_found=None):
    """The datasheet leg. record: the entry of tools/cpl_datasheets.yaml (what
    the drawing on the recorded page shows, as read from the PDF: pin names at
    each pad number and the numbering direction seen from the top); the
    KiCad footprint's pad positions (footprint frame, y down) and its symbol
    pin names are compared with it here, not by eye. Result: pass (match),
    fail (mismatch) or unknown (could not determine)."""
    if not record or record.get('result') == 'could not determine':
        why = (record or {}).get('why', 'no datasheet record for this part')
        return check('datasheet', 'unknown', 'could not determine: ' + why)
    problems, agreed = [], []
    ring = record.get('ring')
    if record.get('numbering') in ('ccw', 'cw'):
        pads = kicad_pads_fp
        if isinstance(ring, int):
            pads = {n: p for n, p in pads.items() if n.isdigit() and int(n) <= ring}
        elif isinstance(ring, list):
            pads = {n: p for n, p in pads.items() if n in [str(r) for r in ring]}
        ours = numbering_direction(pads)
        if ours is None:
            return check('datasheet', 'unknown', 'could not determine: cannot derive the numbering direction of the KiCad pads')
        if ours != record['numbering'] and record.get('mirror_ok'):
            agreed.append('numbering runs %s here against the datasheet\'s %s, harmless: %s' % (ours, record['numbering'], record['mirror_ok']))
        elif ours != record['numbering']:
            problems.append('datasheet numbers pins %s from the top, our footprint numbers them %s' % (record['numbering'], ours))
        else:
            agreed.append('pins numbered %s from the top on both' % ours)
    if record.get('pins') and kicad_names is not None:
        theirs = {str(k): str(v) for k, v in record['pins'].items()}
        default = record.get('others')
        bad, count, loose = [], 0, 0
        for pad, name in kicad_names.items():
            want = theirs.get(pad, default)
            if want is None:
                continue
            relation = name_relation(name, want, pad)
            if relation == 'generic':
                loose += 1              # one side only numbers the pad (a crystal's 1/3 against OSC1/OSC2)
                continue
            count += 1
            if relation != 'match' and relation != 'alias':
                bad.append('pad %s: KiCad %r, datasheet %r' % (pad, name, want))
        if bad:
            problems.append('pin names differ from the datasheet: ' + '; '.join(bad[:8]) + ('; ...' if len(bad) > 8 else ''))
        elif count:
            agreed.append('%d pin names identical to the datasheet\'s%s' % (count, ' (%d more only numbered, not comparable)' % loose if loose else ''))
    elif names_found is not None:
        if names_found.get('missing'):
            problems.append('pin names not found as text on the datasheet page: ' + ', '.join(names_found['missing'][:10]))
        else:
            agreed.append('all %d KiCad pin names found as text on the datasheet page' % names_found['total'])
    if problems:
        return check('datasheet', 'fail', 'MISMATCH: ' + '; '.join(problems) + ' (' + record.get('seen', '') + ')')
    if not agreed:
        return check('datasheet', 'unknown', 'could not determine: record has nothing comparable (' + record.get('seen', '') + ')')
    return check('datasheet', 'pass', 'match: ' + '; '.join(agreed) + '. ' + record.get('seen', ''))

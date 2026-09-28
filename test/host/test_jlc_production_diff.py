#!/usr/bin/env python3
"""tools/jlc_production_diff.py on our own CPU-card Gerbers.

Our fab files against themselves: no differences. The same files as JLC
might return them (no X2 attributes, renamed, uppercase, zipped, origin moved
5 mm): no differences. Then one mutation at a time, each of which must be
reported: fingers trimmed 0.5 mm, the key notch moved 0.3 mm, a drill hit
dropped. A plated drill enlarged by 0.1 mm (JLC's plating allowance) is not a
difference.

    python3 test/host/test_jlc_production_diff.py
"""

import os
import re
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TOOL = os.path.join(ROOT, 'tools', 'jlc_production_diff.py')
OURS = os.path.join(ROOT, 'build', 'hw', 'cpu', 'fab')
bad = 0


def expect(cond, what, out=''):
    global bad
    if not cond:
        bad += 1
        print('FAIL', what)
        print(out)


def run(theirs):
    r = subprocess.run([sys.executable, TOOL, OURS, theirs], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def copy(dest, edit=None):
    """Copy our Gerbers and drill into dest, optionally editing one: edit(name, text)."""
    os.makedirs(dest)
    for name in os.listdir(OURS):
        if re.search(r'\.(g[a-z0-9]+|drl)$', name) and not name.endswith('.gbrjob'):
            text = open(os.path.join(OURS, name)).read()
            if edit:
                text = edit(name, text)
            open(os.path.join(dest, name), 'w').write(text)
    return dest


def as_jlc(name, text):
    """Strip X2, move the origin 5 mm in X, rename the way a CAM system might."""
    if name.endswith('.drl'):
        text = re.sub(r'^X(-?[\d.]+)', lambda m: 'X%.3f' % (float(m.group(1)) + 5),
                      text, flags=re.M)
    else:
        text = '\n'.join(line for line in text.split('\n') if not line.startswith('%T'))
        text = re.sub(r'^(G0[123])?X(-?\d+)', lambda m: '%sX%d' % (m.group(1) or '',
                                                                  int(m.group(2)) + 5000000),
                      text, flags=re.M)
    return text


if not os.path.isdir(OURS):
    print('SKIP: no build/hw/cpu/fab (build the CPU card first)')
    sys.exit(0)

with tempfile.TemporaryDirectory() as tmp:
    code, out = run(OURS)
    expect(code == 0 and 'no differences' in out, 'our files against themselves', out)

    moved = copy(os.path.join(tmp, 'moved'), as_jlc)
    archive = os.path.join(tmp, 'production.zip')
    with zipfile.ZipFile(archive, 'w') as z:
        for name in os.listdir(moved):
            stem, ext = name.rsplit('.', 1)
            z.write(os.path.join(moved, name), 'cam/Gerber_%s.%s' % (stem.split('-', 1)[-1], ext.upper()))
    code, out = run(archive)
    expect(code == 0 and '+5.000, +0.000' in out, 'renamed, zipped, X2-less, origin moved', out)

    def trim(name, text):  # clear the bottom 0.5 mm of every finger (they start at Y -2.15)
        if name.endswith(('F_Cu.gtl', 'B_Cu.gbl')):
            text = text.replace('M02*', '%LPC*%\nG36*\nX-2000000Y-3500000D02*\n'
                                'X52000000Y-3500000D01*\nX52000000Y-1650000D01*\n'
                                'X-2000000Y-1650000D01*\nX-2000000Y-3500000D01*\nG37*\n'
                                '%LPD*%\nM02*')
        return text
    code, out = run(copy(os.path.join(tmp, 'trim'), trim))
    expect(code == 1 and re.search(r'copper-top .*difference.*\n\s+EDGE removed', out)
           and re.search(r'copper-bot .*difference.*\n\s+EDGE removed', out),
           'trimmed fingers reported at the edge', out)

    def notch(name, text):  # move the key notch 0.3 mm in X
        if name.endswith('Edge_Cuts.gm1'):
            for x in ('10050000', '10550000', '12450000', '12950000'):
                text = text.replace('X%s' % x, 'X%d' % (int(x) + 300000))
        return text
    code, out = run(copy(os.path.join(tmp, 'notch'), notch))
    expect(code == 1 and re.search(r'profile .*difference.*\n\s+EDGE', out),
           'moved notch reported', out)

    def drop(name, text):  # lose the first via hit
        if name.endswith('.drl'):
            text = text.replace('X-4.51Y38.4\n', '', 1)
        return text
    code, out = run(copy(os.path.join(tmp, 'drop'), drop))
    expect(code == 1 and 'X -4.510 Y 38.400 missing' in out, 'dropped drill reported', out)

    def plate(name, text):  # JLC's production drill: plated vias 0.1 mm bigger
        return text.replace('T1C0.300', 'T1C0.400') if name.endswith('.drl') else text
    code, out = run(copy(os.path.join(tmp, 'plate'), plate))
    expect(code == 0 and 'resized within' in out, 'plating allowance is not a difference', out)

print('jlc_production_diff: %s' % ('FAIL' if bad else 'ok'))
sys.exit(1 if bad else 0)

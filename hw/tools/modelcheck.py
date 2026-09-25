"""Each 3D model's STEP must sit where its WRL does. KiCad renders (and
kicadgen.check_models checks) the .wrl a footprint names, but its STEP
export, which hw/mech/fit.py measures, swaps in the .step beside it. The
two files EasyEDA gives for a part are not always in one frame: the HDMI
receptacle's STEP (C2858275) sat 1.84 mm back and 3.42 mm down from its
WRL, so MECH put its legs 3.8 mm under the board and its face inside the
edge; the microSD socket's (C91145) was 5.27 mm off.

Run under FreeCAD (freecadcmd takes its own arguments, so ours go in MODELCHECK):

    [MODELCHECK="[--fix] [name ...]"] freecadcmd hw/tools/modelcheck.py
                                    (default: every model in hw/lib/jlc.3dshapes)

Compares the surface centroids (area weighted) of the WRL (VRML units of
0.1 inch) and the STEP, and fails when they are more than TOLERANCE mm
apart. --fix moves the STEP onto the WRL (a translation: the check fails
if the two differ by more than that, which --fix cannot mend).
"""

import glob
import os
import re
import sys

import Part

LIB = os.path.join(os.getcwd(), "hw", "lib", "jlc.3dshapes")      # run from the repository root
TOLERANCE = 0.2                    # mm between the two centroids
AREA_TOLERANCE = 0.02              # relative: the same surface, not another part


def wrl_centroid(path):
    """(centroid mm, surface area mm^2) of a VRML file's IndexedFaceSets."""
    text = open(path).read()
    tot, c = 0.0, [0.0, 0.0, 0.0]
    for m in re.finditer(r"point\s*\[([^\]]*)\]\s*\}\s*coordIndex\s*\[([^\]]*)\]", text):
        nums = [float(x) for x in re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", m.group(1))]
        pts = [(nums[i] * 2.54, nums[i + 1] * 2.54, nums[i + 2] * 2.54) for i in range(0, len(nums) - 2, 3)]
        face = []
        for i in (int(x) for x in re.findall(r"-?\d+", m.group(2))):
            if i != -1:
                face.append(i)
                continue
            for k in range(1, len(face) - 1):          # a fan of triangles
                a, b, d = pts[face[0]], pts[face[k]], pts[face[k + 1]]
                u = [b[j] - a[j] for j in range(3)]
                v = [d[j] - a[j] for j in range(3)]
                cr = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                area = 0.5 * sum(x * x for x in cr) ** 0.5
                tot += area
                for j in range(3):
                    c[j] += area * (a[j] + b[j] + d[j]) / 3
            face = []
    return [x / tot for x in c], tot


def step_centroid(shape):
    tot, c = 0.0, [0.0, 0.0, 0.0]
    for f in shape.Faces:
        a, m = f.Area, f.CenterOfMass
        tot += a
        c[0] += a * m.x
        c[1] += a * m.y
        c[2] += a * m.z
    return [x / tot for x in c], tot


def main(argv):
    fix = "--fix" in argv
    names = [a for a in argv if not a.startswith("-")]
    wrls = [os.path.join(LIB, n + ".wrl") for n in names] or sorted(glob.glob(os.path.join(LIB, "*.wrl")))
    bad = 0
    for wrl in wrls:
        step = wrl[:-4] + ".step"
        name = os.path.basename(wrl)[:-4]
        if not os.path.exists(step):
            continue
        (w, wa) = wrl_centroid(wrl)
        shape = Part.read(step)
        (s, sa) = step_centroid(shape)
        off = [w[j] - s[j] for j in range(3)]
        dist = sum(x * x for x in off) ** 0.5
        same = abs(wa - sa) <= AREA_TOLERANCE * wa
        if dist <= TOLERANCE and same:
            print("ok   %s: STEP on WRL (%.2f mm)" % (name, dist))
            continue
        if fix and same:
            shape.translate(App.Vector(*off))
            shape.exportStep(step)
            print("FIXED %s: STEP moved by (%.2f, %.2f, %.2f) mm onto the WRL" % (name, off[0], off[1], off[2]))
            continue
        bad += 1
        print("FAIL %s: the STEP is %.2f mm from the WRL (%.2f, %.2f, %.2f)%s" % (
            name, dist, off[0], off[1], off[2], "" if same else "; surface %.0f vs %.0f mm^2: not the same model" % (sa, wa)))
    print("modelcheck: %d model(s) with the STEP off the WRL" % bad)
    return 1 if bad else 0


import FreeCAD as App  # noqa: E402

# freecadcmd takes its own arguments: ours come in MODELCHECK ("--fix name ...")
_rc = main(os.environ.get("MODELCHECK", "").split())
sys.stdout.flush()                 # freecadcmd's exit drops what is still buffered
if _rc:
    sys.exit(_rc)

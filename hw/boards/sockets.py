#!/usr/bin/env python3
"""The main board's card-edge sockets, and the check that a card mates with them.

The cards use the cupc8:CUPC8_* symbols with KiCad's BUS_PCIexpress_* finger
footprints; the main board uses the footprints of the real sockets (LCSC),
imported with hw/tools/jlcimport.py:

    I/O slot     C404113   UMAX 3183-10200P1T, PCIe x1 36 contacts, THT
    CPU socket   C404111   UMAX 3183-10112P1T, PCIe x8 98 contacts, THT
    system slot  C19188869 PCIE-64P11L, PCIe x4 64 contacts, SMD with posts

The two THT sockets have their pads named A1..B49 as the UMAX drawing labels
the rows ("A PIN#1", "B PIN#1"), so the main board uses the card symbols
as they are. The SMD socket's pads are 1..64, and 65 for both hold-downs;
EasyEDA's symbol for it names 1..32 A1..A32 and 33..64 B1..B32 (x4_contact).
The main board uses a copy of cupc8:CUPC8_SystemSlot numbered that way
(hw/boards/main.py, cupc8_main:CUPC8_SystemSlot_64P11L), so JLC's own
footprint places it.

check() is the guard against the mistake that would kill every card: it
mates KiCad's card finger footprint with each socket footprint, the way the
card physically goes in (its key in the socket's key), and requires every
finger to land on the socket contact of the same name, and the main board's
symbol to give that contact's pad the card symbol's name for it.

Geometry (both footprints are top views, Y down):
  - a card footprint has its fingers at the bottom edge, pin 1 at the left,
    B fingers on F.Cu (the component side, which faces the viewer)
  - stood up in the socket with pin 1 to the west, that face looks south, so
    its B fingers touch the socket's south (+Y) contact row and the A fingers
    the north row
  - along the socket, the card's key notch sits on the socket's key: the
    widest gap between neighbouring contacts, where the key post is

    python3 hw/boards/sockets.py          the self-test, then the check
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402

EDGE = os.path.join(kg.KICAD_FOOTPRINTS, "Connector_PCBEdge.pretty")
CUPC8 = os.path.join(kg.HW_LIB, "cupc8.pretty")

# card symbol -> (socket footprint, KiCad card-edge footprint it must mate
# with, the symbol the main board uses for the socket)
SOCKETS = {
    "CUPC8_Slot": ("cupc8:UMAX_3183-10200P1T", "BUS_PCIexpress_x1", "cupc8:CUPC8_Slot"),
    "CUPC8_CPUSocket": ("cupc8:UMAX_3183-10112P1T", "BUS_PCIexpress_x8", "cupc8:CUPC8_CPUSocket"),
    "CUPC8_SystemSlot": ("cupc8:SOFNG_PCIE-64P11L", "BUS_PCIexpress_x4", "cupc8_main:CUPC8_SystemSlot_64P11L"),
}

# the JLC imports they are made from, and what changes (derive()):
#  - the UMAX sockets: EasyEDA's holes (0.91 or 0.80 mm, 1.52 or 1.30 mm
#    rings) and 2.5/2.4 mm posts leave pin A11/B11's ring 0.06-0.2 mm from
#    the key post, under JLC's 0.25 mm. The drawing's recommended layout
#    (318307001 sheet 4) is 0.70 +-0.08 mm holes and 2.35 mm posts: drill
#    0.75 mm with a 1.2 mm ring, posts 2.35 mm
#  - the Sofng socket: its hold-down pads (65) reach over the locating
#    holes' edge (mask bridge): narrowed to 1.0 mm, centre 0.2 mm outward
#    (within bomcheck's 0.2 mm of JLC's pad), 0.3 mm clear of the hole
DERIVED = {
    "UMAX_3183-10200P1T": ("CONN-TH_36P-P1.00-V_3183-XXXXXPXT", "umax"),
    "UMAX_3183-10112P1T": ("CONN-TH_98P-P1.00-V_3183-XXXXXPXT", "umax"),
    "SOFNG_PCIE-64P11L": ("PCIE-SMD_PCIE-64P11L", "sofng"),
}


def derive():
    """Write the DERIVED footprints into hw/lib/cupc8.pretty. Pad numbers and
    positions stay JLC's (hw/tools/bomcheck.py matches them)."""
    import re
    for name, (src, kind) in DERIVED.items():
        text = open(os.path.join(kg.HW_LIB, "jlc.pretty", src + ".kicad_mod")).read()
        text = text.replace("easyeda2kicad:" + src, "cupc8:" + name, 1)
        if kind == "umax":
            text = re.sub(r"(\(pad \w+ thru_hole circle \(at [^)]*\)) \(size [\d.]+ [\d.]+\) (\(layers [^)]*\))\(drill [\d.]+\)",
                          r"\1 (size 1.2 1.2) \2(drill 0.75)", text)
            text = re.sub(r'(\(pad "" np_thru_hole circle \(at [^)]*\)) \(size [\d.]+ [\d.]+\) \(drill [\d.]+\)',
                          r"\1 (size 2.35 2.35) (drill 2.35)", text)
            # the row letters "A" and "B" go: beside pin 1 they sit on the
            # outline or over the corner mounting hole, and the key already
            # fixes the card's way round
            text = re.sub(r"\n\t\(fp_text user [AB] \(at [^)]*\) \(layer F\.SilkS\)\n\t\t\(effects[^\n]*\n\t\)", "", text)
        else:
            def nail(m):
                x = float(m.group(1))
                return "(pad 65 smd rect (at %.2f %s) (size 1.00 %s)" % (x + (0.2 if x > 0 else -0.2),
                                                                         m.group(2), m.group(3))
            text = re.sub(r"\(pad 65 smd rect \(at ([-\d.]+) ([-\d.]+)(?: [-\d.]+)?\) \(size [\d.]+ ([\d.]+)\)", nail, text)
        path = os.path.join(CUPC8, name + ".kicad_mod")
        if not os.path.exists(path) or open(path).read() != text:
            with open(path, "w") as f:
                f.write(text)


def x4_contact(pad):
    """The contact of a C19188869 pad (None for the hold-downs, 65)."""
    n = int(pad)
    return None if n > 64 else ("A%d" % n if n <= 32 else "B%d" % (n - 32))


def x4_pad(contact):
    """The C19188869 pad of a system slot contact: x4_contact's inverse."""
    return str(int(contact[1:]) + (0 if contact[0] == "A" else 32))


CONTACT = {"CUPC8_SystemSlot": x4_contact}


def _load(fpid_or_dir, name=None):
    import pcbnew
    if name is None:
        lib, name = fpid_or_dir.split(":")
        fpid_or_dir = kg.footprint_dir(lib)
    fp = pcbnew.FootprintLoad(fpid_or_dir, name)
    if fp is None:
        raise SystemExit("footprint %s/%s not found" % (fpid_or_dir, name))
    return fp


def _key_centre(xs, what):
    xs = sorted(set(round(x, 3) for x in xs))
    gaps = [(b - a, (a + b) / 2) for a, b in zip(xs, xs[1:])]
    widest = max(gaps)
    if widest[0] < 2.5:
        raise SystemExit("%s: no key gap among the contacts" % what)
    return widest[1]


def check_socket(symbol, socket_fpid, card_name, sock=None):
    """Problems (empty = the card mates) for one socket footprint (or the
    footprint object `sock`, for the self-test)."""
    import pcbnew
    to = pcbnew.ToMM
    bad = []
    sock = sock or _load(socket_fpid)
    card = _load(EDGE, card_name)
    contact = CONTACT.get(symbol, lambda n: n)
    pads = {p.GetNumber() for p in sock.Pads() if p.GetNumber()}
    sp = {contact(p.GetNumber()): (to(p.GetPosition().x), to(p.GetPosition().y)) for p in sock.Pads()
          if p.GetNumber() and contact(p.GetNumber())}
    cp = {p.GetNumber(): (to(p.GetPosition().x), p.IsOnLayer(pcbnew.F_Cu)) for p in card.Pads() if p.GetNumber()}
    if set(sp) != set(cp):
        bad.append("%s: socket contacts %s vs card fingers %s differ: %s" % (
            symbol, len(sp), len(cp), sorted(set(sp) ^ set(cp))[:8]))
    # the main board's symbol has a pin for every pad, and each contact's pin
    # has the card symbol's name for that contact
    card_names = {n: p[3] for n, p in kg.symbol_pins(kg.load_symbol("cupc8:" + symbol)).items()}
    main_pins = kg.symbol_pins(kg.load_symbol(SOCKETS[symbol][2]))
    if set(main_pins) != pads:
        bad.append("%s: symbol pins and socket pads differ: %s" % (symbol, sorted(set(main_pins) ^ pads)[:8]))
    for num, p in main_pins.items():
        c = contact(num)
        if c and card_names.get(c) != p[3]:
            bad.append("%s: pad %s is contact %s (%s) but its pin is %s" % (symbol, num, c, card_names.get(c), p[3]))
    ys = sorted({round(y, 3) for _, y in sp.values()})
    mid = (ys[0] + ys[-1]) / 2
    sk = _key_centre([x for x, _ in sp.values()], socket_fpid)
    ck = _key_centre([x for x, _ in cp.values()], card_name)
    # the key post (a non-plated hole) must sit in the key gap
    posts = [to(p.GetPosition().x) for p in sock.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    if not any(abs(x - sk) < 1.0 for x in posts):
        bad.append("%s: no key post in the key gap at x=%.2f (posts at %s)" % (socket_fpid, sk, posts))
    for n, (cx, front) in sorted(cp.items()):
        if n not in sp:
            continue
        sx, sy = sp[n]
        south = sy > mid
        if south != front:
            bad.append("%s: finger %s (%s side) meets the %s contact row" % (
                symbol, n, "B/component" if front else "A/solder", "south" if south else "north"))
        if abs((sx - sk) - (cx - ck)) > 0.05:
            bad.append("%s: finger %s is %.2f mm from the key, contact %s is %.2f mm" % (
                symbol, n, cx - ck, n, sx - sk))
    # pin 1 is on the short side of the key, as on PCIe
    last = "A%d" % max(int(k[1:]) for k in sp)
    if (sp["A1"][0] - sk) * (sp[last][0] - sk) > 0:
        bad.append("%s: A1 and the last contact are on the same side of the key" % symbol)
    return bad


def check():
    bad = []
    for symbol, (fpid, card, _) in SOCKETS.items():
        bad += check_socket(symbol, fpid, card)
    return bad


def selftest():
    """The check must fail on the two ways an import can go wrong: rows
    swapped (A named B), and contacts numbered from the wrong end."""
    import pcbnew  # noqa: F401
    bad = []
    for label, rename in (("rows swapped", lambda n: {"A": "B", "B": "A"}[n[0]] + n[1:]),
                          ("numbered from the wrong end", lambda n: n[0] + str(19 - int(n[1:])))):
        fp = _load(SOCKETS["CUPC8_Slot"][0])
        for p in fp.Pads():
            if p.GetNumber():
                p.SetNumber(rename(p.GetNumber()))
        if not check_socket("CUPC8_Slot", label, "BUS_PCIexpress_x1", fp):
            bad.append("self-test: a socket with its %s passes the check" % label)
    return bad


def main():
    import pcbnew  # noqa: F401
    derive()
    bad = selftest() + check()
    for b in bad:
        print("FAIL", b)
    print("sockets: %d problems" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

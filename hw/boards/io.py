#!/usr/bin/env python3
"""The IO card (doc/hardware/io-card.md): an RP2040 as a USB host for a HID
keyboard, on a USB-A receptacle at the card's top edge.

    python3 hw/boards/io.py [outdir]      (default build/hw/io)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
sys.path.insert(0, HERE)
import kicadgen as kg  # noqa: E402
import rp2040card as rc  # noqa: E402

G = kg.GRID

# io_mcu in hw/pins.yaml (the slot pins, GPIO2-6, are rp2040card's)
GPIOS = {7: "VBUS_EN", 8: "VBUS_nFAULT", 16: "UART_TX", 24: "LED_KEY", 25: "LED_KBD"}


def schematic(path, footprint_libs):
    s = kg.Schematic("io", "CUPC/8 IO card (USB keyboard)", paper="A2")
    # LEDs: keyboard connected (GPIO25), and keyboard activity (GPIO24), the
    # one TX/RX-style LED an input-only link needs (milestone-1.md)
    rc.core(s, GPIOS, leds=[("LED_KBD", "red"), ("LED_KEY", "green")], usb=True)

    # ---- the keyboard port's 5 V (power.md, "IO card keyboard boost"): the
    # slot's +5V can sag to 3.97 V at the card, under USB's 4.40 V, so a
    # TPS61023 boosts it to 5.06 V (750k/100k: 0.595 V x 8.5), and passes
    # its input straight through above ~5.1 V. Always on (EN at VIN).
    u7 = s.add("jlc:TPS61023DRLR", "U7", "TPS61023DRLR", "jlc:SOT-563_L1.6-W1.2-P0.50-LS1.6-BR",
               at=(204 * G, 124 * G), fields={"LCSC": "C919459"})
    s.connect(u7, "VIN", "+5V")
    s.connect(u7, "EN", "+5V")
    s.connect(u7, "GND", "GND")
    s.connect(u7, "SW", "BOOST_SW")
    s.connect(u7, "VOUT", "VBOOST")
    s.connect(u7, "FB", "BOOST_FB")
    l1 = s.add("Device:L", "L1", "1u", "jlc:IND-SMD_L4.4-W4.2", at=(184 * G, 124 * G),
               fields={"LCSC": "C167203"})
    rc.two(s, l1, "+5V", "BOOST_SW")
    r16 = rc.passive(s, "R", "R16", "750k", (218 * G, 120 * G), fp=rc.R0603, lcsc="C23240")
    r17 = rc.passive(s, "R", "R17", "100k", (218 * G, 138 * G), fp=rc.R0603, lcsc="C25803")
    rc.two(s, r16, "VBOOST", "BOOST_FB")
    rc.two(s, r17, "BOOST_FB", "GND")
    c23 = rc.passive(s, "C", "C23", "22u", (222 * G, 118 * G))
    c24 = rc.passive(s, "C", "C24", "22u", (228 * G, 118 * G))
    rc.two(s, c23, "VBOOST", "GND")
    rc.two(s, c24, "VBOOST", "GND")

    # ---- VBUS: TPS2553DBVR-1 from the boost's output (IC-005,
    # doc/hardware/io-port-switch-proposal.md). IOS(min) = 25230/R^1.016,
    # IOS(max) = 22980/R^0.94 mA (R in kOhm): 45.3k 1 % -> 514..647 mA
    # guaranteed. Latches off 5..10 ms into an overcurrent with FAULT low;
    # toggling EN restarts it (the card's firmware retries).
    u5 = s.add("jlc:TPS2553DBVR-1", "U5", "TPS2553DBVR-1", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",
               at=(200 * G, 20 * G), fields={"LCSC": "C111738"})
    s.connect(u5, "IN", "VBOOST")
    s.connect(u5, "OUT", "VBUS")
    s.connect(u5, "GND", "GND")
    s.connect(u5, "ILIM", "ILIM")
    s.connect(u5, "EN", "VBUS_EN")
    s.connect(u5, "FAULT", "VBUS_nFAULT")
    r10 = rc.passive(s, "R", "R10", "45k3", (186 * G, 30 * G), lcsc="C26980")
    rc.two(s, r10, "ILIM", "GND")
    r11 = rc.passive(s, "R", "R11", "100k", (186 * G, 46 * G))       # EN must not float (RP2040 in reset)
    rc.two(s, r11, "VBUS_EN", "GND")
    c20 = rc.passive(s, "C", "C20", "10u", (214 * G, 12 * G))        # the boost's input (TPS61023: 10 uF at VIN)
    rc.two(s, c20, "+5V", "GND")
    c21 = rc.passive(s, "C", "C21", "100u", (222 * G, 12 * G))       # USB host port bulk (spec: >= 120 uF-ish, 100 uF ceramic)
    rc.two(s, c21, "VBUS", "GND")
    c22 = rc.passive(s, "C", "C22", "100n", (228 * G, 30 * G))
    rc.two(s, c22, "VBUS", "GND")
    c25 = rc.passive(s, "C", "C25", "1u", (206 * G, 12 * G))         # at U5 IN: 100 nF rings IN to 8.5 V in a short (T5)
    rc.two(s, c25, "VBOOST", "GND")
    # FAULT is open drain, active low: pulled up to the card's 3V3 for GPIO8
    r12 = rc.passive(s, "R", "R12", "10k", (200 * G, 46 * G))
    rc.two(s, r12, "3V3", "VBUS_nFAULT")

    # ---- USB-A receptacle, ESD, 27 ohm series (design guide). The RP2040's
    # USB PHY switches its own 15k host pull-downs on in host mode.
    j2 = s.add("jlc:USB-302S", "J2", "USB-A", "cupc8:USB_A_SOFNG_USB-302S-T", at=(212 * G, 80 * G),
               fields={"LCSC": "C112455"})
    for pin, net in ((1, "VBUS"), (2, "USB_CONN_DM"), (3, "USB_CONN_DP"), (4, "GND"), (5, "GND"), (6, "GND")):
        s.connect(j2, pin, net)
    u6 = s.add("Power_Protection:USBLC6-2SC6", "U6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
               at=(212 * G, 110 * G), fields={"LCSC": "C7519"})
    s.connect(u6, "1", "USB_CONN_DM")
    s.connect(u6, "6", "USB_CONN_DM")
    s.connect(u6, "3", "USB_CONN_DP")
    s.connect(u6, "4", "USB_CONN_DP")
    s.connect(u6, "VBUS", "VBUS")
    s.connect(u6, "GND", "GND")
    r14 = rc.passive(s, "R", "R14", "27R", (190 * G, 96 * G))
    r15 = rc.passive(s, "R", "R15", "27R", (196 * G, 96 * G))
    rc.two(s, r14, "USB_DM", "USB_CONN_DM")
    rc.two(s, r15, "USB_DP", "USB_CONN_DP")

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


POWER_NETS = rc.POWER_NETS + ("/VBUS", "/VBOOST")   # the boost IC's own pins are laid by hand (prepare)
# J2's opening is 12.04 mm in front of its footprint origin (the pegs are
# 2.54 mm in front, the shell face 9.5 mm beyond them: C112455 drawing), so
# turned to face up, the origin sits 12.04 mm below the top edge
PLACEMENT = dict(rc.core_placement(26.5, -17.5), **{
    "J1": (0, 0, 0),
    "C2": (3, -11.5, 90),                # the slot's +3V3 comes in at B4/A4
    "R3": (8.5, -12.5, 90),              # RUN (CARD_RST_n, B9) pull-up: by its finger, clear of the SWD pins
    # the crystal right of the finger tab: nothing but its ground ties within
    # 5 mm above the tab (slot.md, Mechanical)
    "Y1": (22.6, -8.2, 0),
    "C16": (20.5, -12.6, 90),
    "C17": (25.4, -8.2, 90),
    "U4": (16.5, -18, 0),
    "C18": (13.3, -18, 90),
    "R5": (19, -38.5, 0),
    "D2": (19, -41, 0),
    "R6": (25, -38.5, 0),
    "D3": (25, -41, 0),
    "J2": (39.5, -44 + 12.04, 180),
    "U6": (41.4, -25.3, 0),
    "R14": (36.8, -19.6, 0),            # USB_DM, DP: by the ESD, over the cap column from pins 46/47
    "R15": (36.8, -22.6, 0),
    "U5": (50, -22, 180),                # TPS2553 (SOT-23-6): IN top right, as the old SY6280 kept IN on top
    "C25": (52.6, -25.6, 90),            # 1 uF at U5 IN (pad 1), <= ~10 mm from C23/C24
    # the boost (TPS61023 layout guide: caps at VIN and VOUT, short SW loop)
    "U7": (43, -11.5, 180),
    "L1": (47.5, -10.8, 0),
    "C20": (40.3, -9.8, 90),
    "C23": (45.2, -15.0, 90),
    "C24": (47.9, -15.0, 90),
    "R16": (40.8, -13.3, 0),
    "R17": (40.8, -15.5, 180),
    "C21": (53.6, -17.5, 90),
    "C22": (44.9, -25.5, 90),
    "R10": (46.3, -22.6, 90),
    "R11": (42.6, -18.3, 90),
    "R12": (33.5, -10.5, 90),
    # bring-up pads down the left edge, the SWD ones nearest the fingers they share
    "TP1": (-4, -36), "TP2": (-4, -18.5), "TP3": (-4, -22), "TP4": (-4, -25.5), "TP5": (-4, -29), "TP6": (-4, -32.5),
})
PLACEMENT.update({k: v + (0,) for k, v in PLACEMENT.items() if len(v) == 2})
LOGO_MM = 12
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 7, -25, 0)]
TITLE, REVISION = "CUPC/8 IO", "A"


def prepare(board):
    """The RP2040 card's own (TESTEN, DVDD), then the boost's pins, which are
    0.3 mm pads at 0.5 mm pitch that Freerouting's power-class tracks can't
    reach: VIN and EN to the input cap, SW to the inductor, VOUT to the
    output caps, FB to its divider (TPS61023 layout guide: short loops)."""
    import pcbnew
    # The body marks are clipped with the 0.01 mm mask expansion beyond
    # the 0.15 mm silk clearance from pad copper.
    # Adjust these instances after the common footprint pad clipper runs.
    edits = 0
    for ref in ("U4", "L1"):
        fp = next(f for f in board.GetFootprints() if f.GetReference() == ref)
        for i in range(fp.GraphicalItems().size()):
            g = pcbnew.Cast_to_PCB_SHAPE(fp.GraphicalItems()[i])
            if not g or g.GetLayer() != pcbnew.F_SilkS:
                continue
            a, b = g.GetStart(), g.GetEnd()
            ax, ay, bx, by = map(pcbnew.ToMM, (a.x, a.y, b.x, b.y))
            if ref == "U4" and g.GetShape() == pcbnew.SHAPE_T_SEGMENT and abs(ay + 18.88) < .001 and abs(by + 18.88) < .001:
                g.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(16.3), a.y))
                g.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(16.7), b.y))
                edits += 1
            elif ref == "L1" and g.GetShape() == pcbnew.SHAPE_T_SEGMENT and abs(ax - bx) < .001 and any(abs(ax - x) < .001 for x in (45.22, 49.78)):
                if abs(ay + 12.104999) < .001:
                    g.SetStart(pcbnew.VECTOR2I(a.x, pcbnew.FromMM(-12.135)))
                elif abs(by + 12.104999) < .001:
                    g.SetEnd(pcbnew.VECTOR2I(b.x, pcbnew.FromMM(-12.135)))
                elif abs(ay + 9.495) < .001:
                    g.SetStart(pcbnew.VECTOR2I(a.x, pcbnew.FromMM(-9.465)))
                elif abs(by + 9.495) < .001:
                    g.SetEnd(pcbnew.VECTOR2I(b.x, pcbnew.FromMM(-9.465)))
                else:
                    continue
                edits += 1
    if edits != 5:
        raise ValueError("U4/L1 silk geometry changed")
    rc.io_preroute(board)
    at = lambda ref, n: rc.pad_at(board, ref, n)          # noqa: E731
    vin, en, fb = at("U7", 3), at("U7", 2), at("U7", 1)
    sw, vout = at("U7", 5), at("U7", 6)
    rc.track(board, "/+5V", vin, at("C20", 1), width=0.3)
    rc.track(board, "/+5V", en, vin, width=0.25)
    lsw = at("L1", 2)
    corner = (lsw[0] - 0.4, sw[1])
    rc.track(board, "/BOOST_SW", sw, corner, width=0.3)
    rc.track(board, "/BOOST_SW", corner, (corner[0], lsw[1]), width=0.3)
    rc.track(board, "/VBOOST", vout, at("C23", 1), width=0.3)
    rc.track(board, "/VBOOST", at("C23", 1), at("C24", 1), width=0.3)
    # Take the supply around the right side of the port switch. Its IN
    # moved to pin 1 with TPS2553; leaving this last branch to the router
    # strands VBOOST in every tested ordering. Keep clear of C21 and U5's
    # output/limit pads, and finish at the actual IN pad.
    boost_in = at("U5", 1)
    boost_cap = at("C24", 1)
    if boost_in != (50.95, -23.15) or boost_cap != (47.9, -14.05):
        raise ValueError("TPS2553 VBOOST escape geometry changed")
    rc.track(board, "/VBOOST", boost_cap, (51.8, boost_cap[1]), width=0.3)
    rc.track(board, "/VBOOST", (51.8, boost_cap[1]), (51.8, boost_in[1]), width=0.3)
    rc.track(board, "/VBOOST", (51.8, boost_in[1]), boost_in, width=0.3)
    local_cap = at("C25", 1)
    if local_cap != (52.6, -25.12):
        raise ValueError("TPS2553 local input capacitor moved")
    rc.track(board, "/VBOOST", local_cap, (51.8, local_cap[1]), width=0.3)
    rc.track(board, "/VBOOST", (51.8, local_cap[1]), (51.8, boost_in[1]), width=0.3)
    rc.track(board, "/BOOST_FB", fb, at("R16", 2), width=0.2)
    rc.track(board, "/BOOST_FB", at("R16", 2), at("R17", 1), width=0.2)


if __name__ == "__main__":
    rc.build("io", schematic, PLACEMENT, POWER_NETS, GRAPHICS, {"D1": "PWR", "D2": "KBD", "D3": "KEY"}, GPIOS,
             TITLE, REVISION, usb=True, layers=4, passes=100, preroute=prepare)

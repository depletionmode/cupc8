#!/usr/bin/env python3
"""HW-000: a small board that runs the whole KiCad pipeline end to end.

USB-C power in, AP2112K 3.3 V LDO, power LED, 3V3 header. Each step must pass:
schematic generation, ERC, netlist, board build, Freerouting, zone fill, DRC
with schematic parity, Gerbers + drill, BOM + CPL, 3D render.

    python3 hw/smoke/smoke.py [outdir]      (default build/hw/smoke)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402
import logo  # noqa: E402

G = kg.GRID


def schematic(path):
    s = kg.Schematic("smoke", "CUPC/8 KiCad pipeline smoke test")
    j1 = s.add("Connector:USB_C_Receptacle_PowerOnly_6P", "J1", "USB-C power",
               "Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal",
               at=(20 * G, 30 * G))
    r1 = s.add("Device:R", "R1", "5.1k", "Resistor_SMD:R_0603_1608Metric", at=(40 * G, 24 * G),
               fields={"LCSC": "C23186"})
    r2 = s.add("Device:R", "R2", "5.1k", "Resistor_SMD:R_0603_1608Metric", at=(44 * G, 24 * G),
               fields={"LCSC": "C23186"})
    u1 = s.add("Regulator_Linear:AP2112K-3.3", "U1", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
               at=(60 * G, 30 * G), fields={"LCSC": "C51118"})
    c1 = s.add("Device:C", "C1", "1u", "Capacitor_SMD:C_0603_1608Metric", at=(52 * G, 36 * G),
               fields={"LCSC": "C15849"})
    c2 = s.add("Device:C", "C2", "1u", "Capacitor_SMD:C_0603_1608Metric", at=(70 * G, 36 * G),
               fields={"LCSC": "C15849"})
    r3 = s.add("Device:R", "R3", "1k", "Resistor_SMD:R_0603_1608Metric", at=(80 * G, 30 * G),
               fields={"LCSC": "C21190"})
    d1 = s.add("Device:LED", "D1", "green", "LED_SMD:LED_0603_1608Metric", at=(80 * G, 46 * G),
               rot=90, fields={"LCSC": "C72043"})
    j2 = s.add("Connector_Generic:Conn_01x02", "J2", "3V3 out",
               "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", at=(92 * G, 30 * G))
    f1 = s.add("power:PWR_FLAG", "#FLG01", "PWR_FLAG", at=(30 * G, 44 * G))
    f2 = s.add("power:PWR_FLAG", "#FLG02", "PWR_FLAG", at=(36 * G, 44 * G))

    for p in ("A9", "B9"):
        s.connect(j1, p, "VBUS")
    for p in ("A12", "B12", "SH"):
        s.connect(j1, p, "GND")
    s.connect(j1, "A5", "CC1")
    s.connect(j1, "B5", "CC2")
    s.connect(r1, 1, "CC1")
    s.connect(r1, 2, "GND")
    s.connect(r2, 1, "CC2")
    s.connect(r2, 2, "GND")
    s.connect(u1, "VIN", "VBUS")
    s.connect(u1, "EN", "VBUS")
    s.connect(u1, "GND", "GND")
    s.connect(u1, "VOUT", "3V3")
    s.nc(u1, "NC")
    s.connect(c1, 1, "VBUS")
    s.connect(c1, 2, "GND")
    s.connect(c2, 1, "3V3")
    s.connect(c2, 2, "GND")
    s.connect(r3, 1, "3V3")
    s.connect(r3, 2, "LED_A")
    s.connect(d1, "A", "LED_A")
    s.connect(d1, "K", "GND")
    s.connect(j2, 1, "3V3")
    s.connect(j2, 2, "GND")
    s.connect(f1, 1, "VBUS")
    s.connect(f2, 1, "GND")

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=("cupc8",))


PLACEMENT = {
    "J1": (4, 15, 270),
    "R1": (12, 9, 0),
    "R2": (12, 21, 0),
    "C1": (18, 15, 90),
    "U1": (24, 15, 0),
    "C2": (30, 15, 90),
    "R3": (34, 9, 0),
    "D1": (34, 21, 0),
    "J2": (40, 13.73, 0),
}
OUTLINE = (0, 0, 45, 40)
LOGO_MM = 12


def main():
    import pcbnew  # noqa: F401 - first, so its start-up noise comes before the step lines
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "hw", "smoke"))
    os.makedirs(out, exist_ok=True)
    sch = os.path.join(out, "smoke.kicad_sch")
    pcb = os.path.join(out, "smoke.kicad_pcb")
    pro = os.path.join(out, "smoke.kicad_pro")

    def step(name, fn):
        print("%-28s" % name, end=" ", flush=True)
        r = fn()
        print("ok" + (" (%s)" % r if r else ""))

    step("schematic", lambda: schematic(sch))

    def erc():
        rpt = os.path.join(out, "erc.json")
        kg.run(["kicad-cli", "sch", "erc", "--format", "json", "--severity-all",
                "--exit-code-violations", "-o", rpt, sch])
    step("ERC", erc)

    nets = {}

    def netlist():
        c, n = kg.export_netlist(sch, os.path.join(out, "smoke.net"))
        nets["c"], nets["n"] = c, n
        return "%d parts, %d nets" % (len(c), len(n))
    step("netlist", netlist)

    board = {}

    def build():
        import pcbnew
        comps = {r: c for r, c in nets["c"].items() if not r.startswith("#")}
        logo.footprint(LOGO_MM)
        b = kg.build_board(comps, nets["n"], PLACEMENT, OUTLINE, zones=("/GND",),
                           graphics=[("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 22.5, 32.5, 0)])
        # save without settings (a plain save writes, and caches, a default
        # project), then reload so the board picks up the project's rules
        kg.write_project(pro, power_nets=("/VBUS", "/3V3", "/GND"))
        pcbnew.SaveBoard(pcb, b, True)
        board["b"] = pcbnew.LoadBoard(pcb)
    step("board", build)
    step("autoroute", lambda: kg.autoroute(board["b"], out))

    def fill():
        import pcbnew
        kg.fill_zones(board["b"])
        pcbnew.SaveBoard(pcb, board["b"])
    step("zones + save", fill)

    def drc():
        rpt = os.path.join(out, "drc.json")
        kg.run(["kicad-cli", "pcb", "drc", "--format", "json", "--schematic-parity",
                "--severity-all", "--exit-code-violations", "-o", rpt, pcb])
    step("DRC + schematic parity", drc)

    fab = os.path.join(out, "fab")
    os.makedirs(fab, exist_ok=True)

    def gerbers():
        kg.run(["kicad-cli", "pcb", "export", "gerbers", "-o", fab + "/", pcb])
        kg.run(["kicad-cli", "pcb", "export", "drill", "-o", fab + "/", pcb])
        return "%d files" % len(os.listdir(fab))
    step("gerbers + drill", gerbers)

    def bom_cpl():
        kg.run(["kicad-cli", "sch", "export", "bom", "--fields", "Reference,Value,Footprint,LCSC",
                "--group-by", "Value,Footprint,LCSC", "--exclude-dnp", "-o", os.path.join(fab, "bom.csv"), sch])
        kg.run(["kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                "-o", os.path.join(fab, "cpl.csv"), pcb])
    step("BOM + CPL", bom_cpl)

    def render():
        for side in ("top", "bottom"):
            kg.run(["kicad-cli", "pcb", "render", "--width", "1200", "--height", "800", "--quality", "high",
                    "--side", side, "-o", os.path.join(out, "smoke-%s.png" % side), pcb])
    step("3D render", render)
    print("all steps passed; outputs in", out)


if __name__ == "__main__":
    main()

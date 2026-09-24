#!/usr/bin/env python3
"""POW-002 (1V2, RT9013) and POW-003 (Wi-Fi card 3V3, AMS1117): the linear
regulators, on the behavioural model in models/behavioural.lib.

    python3 hw/power/ldo.py 1v2
    python3 hw/power/ldo.py wifi

Each run first re-simulates the datasheet load-step figure its model was
fitted to, so a change to the model or its parameters can't pass silently.

1v2   The chipset core (and the CPU card's own RT9013, which sees the same
      3V3 less the socket). Start-up as the 3V3 buck ramps, a 0 -> 40 mA core
      step, dropout at the lowest 3V3, and the buck's ripple through the
      PSRR (AC analysis at the ripple frequencies POW-001 measures).
wifi  hw/boards/wifi.py as built: AMS1117-3.3 from the slot's +5V, 22 uF in,
      22 uF + 100 nF out. The feed is the whole chain (source, cable, input
      path, slot PTC, link, sense, contacts), so the slot's +5V sags with the
      burst as it will. An ESP32-C3 TX burst, 10 -> 350 mA in 1 us and held
      for 2 ms (a TX frame is 0.1-12 ms), at the typical and worst corners.
      The regulator runs at its lowest set point (3.201 V) and highest
      dropout; the ESP32-C3 needs 3.0 V.
"""

import sys

import budget
import design as d
import spice
from spice import Checks


def model_check(c, ident, name, p, vin, cout, esr, i0, i1, fig_dip):
    p = dict(p, TSS=20e-6)          # settled well before the step at 100 us
    deck = """
V1 in 0 {vin}
X1 in out 0 LDO_BEH params: {p}
C1 out e {c}
R1 e 0 {esr}
I1 out 0 PWL(0 {i0} 100u {i0} 101u {i1})
.tran 20n 130u
.control
run
meas tran vpre find v(out) at=99u
meas tran vmin min v(out) from=100u to=130u
.endc
""".format(vin=vin, p=spice.params(p), c=cout, esr=esr, i0=i0, i1=i1)
    m = spice.run(name, deck)
    dip = m["vpre"] - m["vmin"]
    c.check(ident, "model vs its datasheet load-step figure: dip %.0f mV vs %.0f mV (within 25%%)" % (
        1e3 * dip, 1e3 * fig_dip), abs(dip - fig_dip) / fig_dip, 0.25, "<=", "", fmt="%.2f")


def run_1v2(c):
    p = dict(d.RT9013)
    model_check(c, "L0", "pow002_fit", dict(p, VSET=1.5, VIN_NOM=2.5), 2.5, 1e-6, 0.005, 0.010, 0.300, 0.025)
    v3_lo, v3_hi = d.buck_vout_range()
    vset_lo, vset_hi = 1.2 * (1 - d.RT9013_TOL), 1.2 * (1 + d.RT9013_TOL)
    # start-up behind the buck's 0.8 ms soft start, then a core step
    deck = """
V1 in 0 PWL(0 0 0.8m {v3})
X1 in out 0 LDO_BEH params: {p}
Cout out 0 {cout}
Iload out 0 PWL(0 0.005 1.5m 0.005 1.501m {imax})
.tran 50n 1.8m
.control
run
meas tran vpeak max v(out) from=0 to=1.49m
meas tran vss find v(out) at=1.49m
meas tran vmin min v(out) from=1.5m to=1.8m
meas tran t95 when v(out)={v95} rise=1
.endc
""".format(v3=v3_lo, p=spice.params(dict(p, VIN_NOM=3.3)), cout=d.RT9013_COUT, imax=d.I_1V2_MAX,
           v95=0.95 * 1.2)
    m = spice.run("pow002_step", deck)
    c.check("L1", "1V2 up to 95% within the 3V3 soft start + 1 ms", 1e3 * m["t95"], 1.8, "<=", "ms", fmt="%.2f")
    c.check("L2", "start-up peak at the DC high corner (iCE40 VCC max)", m["vpeak"] - 1.2 + vset_hi,
            d.V1V2_MAX, "<=")
    c.check("L3", "0->40 mA core step, minimum at the DC low corner (droop %.1f mV)" % (
        1e3 * (m["vss"] - m["vmin"])), m["vmin"] - 1.2 + vset_lo, d.V1V2_MIN, ">=")
    drop = d.RT9013["RDROP"] * d.I_1V2_MAX
    c.check("L4", "dropout: lowest 3V3 (DC low - 50 mV step and ripple) - 1V2 max vs dropout at 40 mA",
            v3_lo - 0.050 - vset_hi, drop, ">=")
    c.check("L5", "RT9013 input range: lowest 3V3 vs its 2.2 V minimum", v3_lo - 0.050, 2.2, ">=")
    # the buck's ripple through the PSRR, at the ripple POW-001 reports
    worst = 0.0
    for f, vpp in d.BUCK_RIPPLE:
        deck = """
V1 in 0 DC 3.3 AC 1
X1 in out 0 LDO_BEH params: {p}
Cout out 0 {cout}
Iload out 0 {i}
.ac dec 20 1k 10meg
.control
run
meas ac g find vm(out) at={f}
.endc
""".format(p=spice.params(dict(p, VIN_NOM=3.3)), cout=d.RT9013_COUT, i=d.I_1V2_MAX, f=f)
        g = spice.run("pow002_psrr", deck)["g"]
        c.info("PSRR at %.0f kHz" % (f / 1e3), "%.1f dB: %.1f mVpp in -> %.2f mVpp on 1V2" % (
            20 * __import__("math").log10(g), 1e3 * vpp, 1e3 * vpp * g))
        worst = max(worst, vpp * g)
    c.check("L6", "1V2 total at the DC low corner: 1.2 V - 2 % - step droop - ripple/2",
            m["vmin"] - 1.2 + vset_lo - worst / 2, d.V1V2_MIN, ">=")
    c.info("CPU card", "its RT9013 sees the same 3V3 through the socket (< 20 mV at 40 mA), so L1-L6 cover it")


def run_wifi(c):
    p = dict(d.AMS1117)
    model_check(c, "W0", "pow003_fit", dict(p, VSET=5.0, VIN_NOM=6.5, DROP0=1.0, RDROP=0.2), 6.5, 10e-6, 0.3,
                0.1, 0.5, 0.13)
    for corner in ("typical", "worst"):
        ch = budget.chain(corner)
        worst = corner == "worst"
        vbus = d.VBUS_MIN if worst else d.VBUS_NOM
        k = 1.0 if worst else 0.5
        r_in = (k * (d.CABLE_R_VBUS + d.CABLE_R_GND) + d.R_RECEPTACLE
                + (d.FUSE_IN_R_MAX if worst else d.FUSE_IN_R_MIN)
                + (d.SY6280_RON_MAX if worst else d.SY6280_RON_TYP) + d.R_5VSYS)
        i_other = ch["itot"] - d.I_WIFI_5V
        vset = d.AMS1117_VOUT_MIN if worst else d.AMS1117_VOUT_NOM
        deck = """
Vs src 0 {vbus}
Rin src v5 {rin}
Cbulk v5 0 {cbulk}
Iother v5 0 {iother}
Rslot v5 card {rslot}
C1 card 0 {cin}
X1 card out 0 LDO_BEH params: {p}
C2 out 0 {cout}
C3 out 0 {chf}
Iesp out 0 PWL(0 {i0} 1m {i0} 1.001m {i1} 3m {i1} 3.001m {i0})
.tran 50n 4m
.control
run
meas tran vss find v(out) at=0.99m
meas tran vmin min v(out) from=1m to=3m
meas tran vtx find v(out) at=2.99m
meas tran vcard min v(card) from=1m to=3m
.endc
""".format(vbus=vbus, rin=r_in, cbulk=dict(d.C_5VSYS)["main 5V_SYS bulk"] + d.BUCK_CIN, iother=i_other,
           rslot=ch["r_slot"], cin=d.WIFI_CIN * d.CERAMIC_DERATE, p=spice.params(dict(p, VSET=vset)),
           cout=d.WIFI_COUT * d.CERAMIC_DERATE, chf=d.WIFI_COUT_HF, i0=d.ESP32_I_IDLE + d.WIFI_I_LEDS,
           i1=d.ESP32_I_TX + d.WIFI_I_LEDS)
        m = spice.run("pow003_" + corner, deck)
        c.info(corner, "slot +5V at the card %.3f V during TX; 3V3 %.3f V before, %.3f V at the end of the "
               "burst (set point %.3f V)" % (m["vcard"], m["vss"], m["vtx"], vset))
        c.check("W1" + corner[0], "%s: ESP32-C3 supply minimum during a 350 mA TX burst" % corner, m["vmin"],
                d.ESP32_VDD_MIN, ">=")
        head = m["vcard"] - (p["DROP0"] + p["RDROP"] * (d.ESP32_I_TX + d.WIFI_I_LEDS))
        c.check("W2" + corner[0], "%s: slot +5V at the card - AMS1117 dropout (1.3 V max at 0.8 A, scaled)"
                % corner, head, d.ESP32_VDD_MIN, ">=")
    c.info("stability", "AMS1117 wants 22 uF tantalum (LM1117: ESR 0.3-22 ohm); the card has ceramic "
           "22 uF + 100 nF (ESR ~ mOhm). The behavioural model has no loop, so this is not checked here.")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which == "1v2":
        c = Checks("POW-002 1V2 LDO, RT9013 behavioural model (hw/power/ldo.py 1v2)")
        run_1v2(c)
    elif which == "wifi":
        c = Checks("POW-003 Wi-Fi card 3V3, AMS1117 behavioural model (hw/power/ldo.py wifi)")
        run_wifi(c)
    else:
        sys.exit(__doc__)
    return c.done()


if __name__ == "__main__":
    sys.exit(main())

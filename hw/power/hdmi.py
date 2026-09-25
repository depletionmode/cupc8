#!/usr/bin/env python3
"""POW-008: the GPU card's HDMI +5V pin through its TPS63802 buck-boost.

    python3 hw/power/hdmi.py        (seconds)

The circuit is design.GPUB_* (the GPU board agent builds it, power.md): slot
+5V -> PTC SMD0805P020TF -> 10 uF -> TPS63802 (0.47 uH, 2 x 22 uF, 825k/91k)
-> HDMI pin 18. The card's +5V is fed through the whole chain (source,
cable, input path, 5V_SYS with the other loads, slot PTC, link, sense,
contacts), so it sags as the converter draws.

The converter is behavioural (models/behavioural.lib BB_BEH), fitted to the
datasheet's load-transient figure; G0 re-checks the fit. TI's TPS63802 PSpice
model (SLVMCX1C, fetched by models/fetch.py) does not run in ngspice-47: with
its switches ported, its SR latches given a solvable hold and its capacitor
ICs applied, the control starts (soft start, PWM) but its buck-boost timer
never fires the first high-side pulse, so the output stays at 0 V.

Runs, each with a 10 -> 55 mA step at 1.3 ms (1 us edge), released at 1.6 ms
(10 mA: the sink's EDID ROM, the DDC pull-ups, the HPD divider):
  worst, typical   the corners of budget.py, the PTC at R1max / Rmin
  high             vSafe5V max, the lightest loads elsewhere: the input is
                   above the output, and the converter bucks

The model regulates at the nominal set point. The pin is compared with HDMI's
4.8-5.3 V after moving it to the DC corners (VFB +-1 %, the divider's 1 %)
and widening it by half the datasheet's power-save ripple band each way.
"""

import concurrent.futures
import sys

import budget
import design as d
import spice
from spice import Checks

T_STEP, T_REL, T_END = 1.3e-3, 1.6e-3, 1.9e-3
T_APPLY = 120e-6
I_FLOOR = 0.010


def bb_params(vset):
    return spice.params(dict(d.GPUB_BEH, VSET=vset, ETA=d.GPUB_ETA, VINMIN=d.GPUB_VIN_MIN,
                             VOVP=d.GPUB_VIN_OVP[0]))


def deck(corner):
    worst = corner == "worst"
    light = {"wifi_3v3": budget.WIFI_IDLE_3V3, "keyboard": 0.0} if corner == "high" else {}
    ch = budget.chain("worst" if worst else "typical", vbus=d.VBUS_MAX if corner == "high" else None, **light)
    ptc = d.GPU_PTCS[d.GPU_PTC]
    return """
Vs src 0 PWL(0 0 {ton} {vbus})
Rin src v5 {rin}
Cbulk v5 0 {cbulk}
Iother v5 0 PWL(0 0 {ton} {iother})
Rslot v5 cardin {rslot}
Rptc cardin card {rptc}
C1 card 0 {cin}
X1 card pin 0 BB_BEH params: {bb}
C2 pin 0 {cout}
Rfloor pin 0 {rfloor}
Iload pin 0 PWL(0 0 {t1} 0 {t1e} {i1} {t2} {i1} {t2e} 0)
.tran 100n {tend}
.control
run
wrdata {{name}}.dat v(pin) v(card)
.endc
""".format(vbus=ch["vbus"], ton=T_APPLY, rin=d.r_in(worst), cbulk=dict(d.C_5VSYS)["main 5V_SYS bulk"] + d.BUCK_CIN,
           iother=ch["itot"] - ch["igpu"], rslot=ch["r_slot"], rptc=ptc[3] if worst else ptc[2],
           cin=d.GPUB_CIN * d.CERAMIC_DERATE, bb=bb_params(d.gpub_vout_range()[1]),
           cout=d.GPUB_COUT * d.CERAMIC_DERATE, rfloor=d.gpub_vout_range()[1] / I_FLOOR,
           t1=T_STEP, t1e=T_STEP + 1e-6, i1=d.I_HDMI_PIN - I_FLOOR, t2=T_REL, t2e=T_REL + 1e-6, tend=T_END)


def run(corner):
    name = "pow008_" + corner
    spice.run(name, deck(corner).replace("{name}", name))
    return spice.wave(name)


def window(t, v, a, b):
    return [v[k] for k in range(len(t)) if a <= t[k] <= b]


def model_check(c):
    """G0: the fitted model against DS figure 10-21 (2.5 V in, 3.3 V out,
    0.1 -> 1 A, 15 uF effective): the dip within 25 % of the figure's 130 mV."""
    deck = """
V1 in 0 2.5
X1 in out 0 BB_BEH params: {bb}
C1 out 0 15u
I1 out 0 PWL(0 0.1 700u 0.1 701u 1.0)
.tran 50n 900u
.control
run
meas tran vpre find v(out) at=699u
meas tran vmin min v(out) from=700u to=900u
.endc
""".format(bb=bb_params(3.3))
    m = spice.run("pow008_fit", deck)
    dip = m["vpre"] - m["vmin"]
    c.check("G0", "model vs DS figure 10-21: dip %.0f mV vs 130 mV (within 25%%)" % (1e3 * dip),
            abs(dip - 0.13) / 0.13, 0.25, "<=", "", fmt="%.2f")


def main():
    c = Checks("POW-008 GPU card HDMI +5V, TPS63802 buck-boost, behavioural model (hw/power/hdmi.py)")
    model_check(c)
    lo, nom, hi = d.gpub_vout_range()
    name, lcsc, rmin, rmax, hold = d.GPU_PTCS[d.GPU_PTC]
    c.info("set point", "%.3f V nominal; %.3f..%.3f V with VFB +-1 %%, the 1 %% divider and the %.0f mVpp "
           "power-save band; PTC %s (%s) %.2f..%.1f ohm, hold %.2f A at 40 C" % (
               nom, lo, hi, 1e3 * d.GPUB_PFM_RIPPLE, name, lcsc, rmin, rmax, hold))
    corners = ("worst", "typical", "high")
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        res = dict(zip(corners, pool.map(run, corners)))
    for corner in corners:
        t, pin, card = res[corner]
        n = corner[0]
        vmin = min(window(t, pin, T_STEP, T_REL)) - (nom - lo)
        vmax = max(window(t, pin, 0.5e-3, T_END)) + (hi - nom)
        c.info(corner, "converter input %.3f V in the step, %.3f V at most; pin %.3f V before it" % (
            min(window(t, card, T_STEP, T_REL)), max(window(t, card, 0.5e-3, T_END)),
            spice.at(t, pin, T_STEP - 10e-6)))
        c.check("H1" + n, "%s: HDMI pin minimum in a 10->55 mA step, DC low corner" % corner, vmin,
                d.HDMI_PIN_MIN, ">=")
        c.check("H2" + n, "%s: HDMI pin maximum (start-up, release), DC high corner" % corner, vmax,
                d.HDMI_PIN_MAX, "<=")
        if corner == "worst":
            c.info("PTC after the converter", "the pin would be %.3f V at the worst corner (%.1f ohm R1max x "
                   "55 mA = %.2f V off %.3f V): under %.1f V, so the PTC goes ahead of it" % (
                       vmin - rmax * d.I_HDMI_PIN, rmax, rmax * d.I_HDMI_PIN, vmin, d.HDMI_PIN_MIN))
        if corner == "high":
            vin_max = max(window(t, card, 0.5e-3, T_END))
            c.check("H4", "converter input at vSafe5V max vs its input over-voltage threshold (min)", vin_max,
                    d.GPUB_VIN_OVP[0], "<=", fix="the TPS63802 stops above 5.5 V: add a series drop")
    ch = budget.chain("worst")
    c.check("H3", "PTC ahead of the converter: its current (worst corner) vs %s hold at 40 C" % name, ch["igpu"],
            hold, "<=", "A", need=0.10)
    c.check("H5", "converter input at the worst corner vs its 1.3 V minimum",
            d.gpu_i_5v(ch["gpu_in"])[1], d.GPUB_VIN_MIN, ">=")
    c.info("above vSafe5V", "a (non-compliant) source up to the eFuse's OVLO (%.2f V) can take the input past "
           "the TPS63802's 5.5 V OVP; it then stops and the pin drops, which is safe" % d.insw_ovlo()[1])
    return c.done()


if __name__ == "__main__":
    sys.exit(main())

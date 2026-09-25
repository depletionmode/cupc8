#!/usr/bin/env python3
"""POW-007: the IO card's keyboard-port boost (TPS61023, TI's PSpice transient
model in ngspice) and the port voltage the keyboard gets.

    python3 hw/power/boost.py       (~1 min; the three decks run in parallel)

The circuit is design.IOB_* (the IO board agent builds it, power.md): slot
+5V -> 10 uF -> TPS61023 (1 uH, 2 x 22 uF, 750k/100k) -> SY6280 (its RON,
hot) -> USB-A VBUS. The card's +5V is fed through the whole chain (source,
cable, input path, 5V_SYS with the other loads, slot PTC, link, sense,
contacts), as POW-003 does for the Wi-Fi card, so it sags as the boost draws.

Runs:
  worst, typical   the corners of budget.py: boost start-up with no load, then
                   a 0 -> 500 mA keyboard step at 1.3 ms (1 us edge), released
                   at 1.6 ms
  high             vSafe5V max and light loads elsewhere: the boost's input
                   is above its set point, so it passes through; the same step

The model regulates at VREF's typical 0.595 V. Its output is scaled to the
low and high DC corners (VREF 0.580-0.610 V, the divider's 1 %) before the
SY6280's drop is taken off, and compared with USB's port limits.

Model fixes (models/fetch.py): a current source's "10A" and near-ideal
diodes. G0 checks the ported model still regulates where the datasheet says.
"""

import concurrent.futures
import sys

import budget
import design as d
import spice
from spice import Checks

T_STEP, T_REL, T_END = 1.3e-3, 1.6e-3, 1.9e-3
T_APPLY = 120e-6
I_KBD = d.I_KEYBOARD


def deck(corner, card="io", ptc_pos=None):
    """The card's +5V fed through the whole chain at a corner, into the boost.
    io: the keyboard's 500 mA step through the SY6280 to the port.
    gpu: the HDMI pin's 55 mA step, the card's PTC ahead of the boost
    (ptc_pos "ahead") or between it and the pin ("after")."""
    worst = corner == "worst"
    vbus = d.VBUS_MAX if corner == "high" else None
    # "high": vSafe5V max with the lightest loads elsewhere (the radio idle,
    # and for the GPU card no keyboard), so the card's +5V is as high as it gets
    light = {"wifi_3v3": budget.WIFI_IDLE_3V3}
    if card == "gpu":
        light["keyboard"] = 0.0
    ch = budget.chain("worst" if worst else "typical", vbus=vbus, **(light if corner == "high" else {}))
    r_in = d.r_in(worst)
    if card == "io":
        mine, r_ahead, r_after, i1, rpre = ch["iio"], 0.0, d.SY6280_RON_MAX if worst else d.SY6280_RON_TYP, I_KBD, 1e9
        r1, r2, _ = d.boost_divider("io")
    else:
        ptc = d.GPU_PTCS[d.GPU_PTC]
        r_ptc = ptc[3] if worst else ptc[2]
        # the pin is never unloaded (the sink's EDID ROM, the DDC pull-ups, the
        # HPD divider). A 10 mA floor, as a resistor so it draws nothing before
        # the boost is up; with the PTC ahead, the model stalls ngspice in
        # power-save below about that
        mine, i1, rpre = ch["igpu"], d.I_HDMI_PIN - 0.010, 500.0
        r1, r2, _ = d.boost_divider("gpu")
        r_ahead, r_after = (r_ptc, 1e-3) if ptc_pos == "ahead" else (1e-3, r_ptc)
    return """
.param ss=0
Vs src 0 PWL(0 0 {ton} {vbus})
Rin src v5 {rin}
Cbulk v5 0 {cbulk}
Iother v5 0 PWL(0 0 {ton} {iother})
Rslot v5 cardin {rslot}
Rahead cardin card {rahead}
C1 card 0 {cin}
X1 card fb 0 sw card vout TPS61023_schematic
Rdcr card l {dcr}
L1 l sw {l}
C2 vout 0 {cout}
R1 vout fb {r1}
R2 fb 0 {r2}
Rsw vout port {rafter}
Rpre port 0 {rpre}
Iload port 0 PWL(0 0 {t1} 0 {t1e} {i1} {t2} {i1} {t2e} 0)
.options method=gear reltol=1e-3
.tran 20n {tend} 0 {tmax}
.control
run
wrdata {{name}}.dat v(vout) v(port) v(card)
.endc
""".format(vbus=ch["vbus"], ton=T_APPLY, rin=r_in, cbulk=dict(d.C_5VSYS)["main 5V_SYS bulk"] + d.BUCK_CIN,
           iother=ch["itot"] - mine, rslot=ch["r_slot"], rahead=max(r_ahead, 1e-3),
           cin=d.IOB_CIN * d.CERAMIC_DERATE, dcr=d.IOB_L_DCR, l=d.IOB_L, cout=d.IOB_COUT * d.CERAMIC_DERATE,
           r1=r1, r2=r2, rafter=r_after,
           t1=T_STEP, t1e=T_STEP + 1e-6, rpre=rpre, i1=i1, t2=T_REL, t2e=T_REL + 1e-6, tend=T_END,
           # at the GPU's light load, with its PTC ahead, the model's one-shot
           # stalls ngspice at 20 ns; 10 ns converges
           tmax="20n" if card == "io" else "10n")


def run(corner, card="io", ptc_pos=None):
    name = ("pow007_" if card == "io" else "pow008_%s_" % ptc_pos) + corner
    spice.run(name, deck(corner, card, ptc_pos).replace("{name}", name), libs=("TPS61023_TRANS.lib",))
    return spice.wave(name)


def window(t, v, a, b):
    return [v[k] for k in range(len(t)) if a <= t[k] <= b]


def main():
    if sys.argv[1:] == ["gpu"]:
        return gpu()
    c = Checks("POW-007 IO card keyboard boost, TPS61023 TI model (hw/power/boost.py)")
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        res = dict(zip(("worst", "typical", "high"), pool.map(run, ("worst", "typical", "high"))))
    lo, nom, hi = d.iob_vout_range()
    c.info("boost set point", "%.3f V nominal, DC range %.3f..%.3f V" % (nom, lo, hi))

    # G0: the ported model against the datasheet: its regulated output at 0.5 A
    # (typical corner, before the step's release) within 3 % of VREF x divider
    t, vout, port, card = res["typical"]
    v_load = sum(window(t, vout, T_REL - 100e-6, T_REL)) / len(window(t, vout, T_REL - 100e-6, T_REL))
    c.check("G0", "model check: output at 500 mA vs the set point %.3f V (within 3%%)" % nom,
            abs(v_load - nom) / nom, 0.03, "<=", "", fmt="%.3f")

    for corner in ("worst", "typical", "high"):
        t, vout, port, card = res[corner]
        n = corner[0]
        vin = min(window(t, card, T_STEP, T_REL))
        through = min(window(t, card, T_STEP - 100e-6, T_STEP)) >= nom * 1.01
        # regulating: scale the whole output to the DC corners; passing through
        # the output is the input, which needs no scaling
        k_lo, k_hi = (1.0, 1.0) if through else (lo / nom, hi / nom)
        drop = I_KBD * (d.SY6280_RON_MAX if corner == "worst" else d.SY6280_RON_TYP)
        vmin = min(window(t, vout, T_STEP, T_REL)) * k_lo - drop
        vmax = max(window(t, port, 0.2e-3, T_END)) * k_hi
        c.info(corner, "card +5V %.3f V in the step (%s); boost output %.3f V before it" % (
            vin, "pass-through" if through else "boosting", spice.at(t, vout, T_STEP - 10e-6)))
        c.check("P1" + n, "%s: keyboard VBUS minimum in a 0->500 mA step, DC low corner (USB 2.0 low-power "
                "port)" % corner, vmin, d.USB_PORT_MIN, ">=")
        c.check("P2" + n, "%s: keyboard VBUS maximum (start-up, release), DC high corner" % corner, vmax,
                d.USB_PORT_MAX, "<=")
        t_up = next((t[k] for k in range(len(t)) if vout[k] >= 0.95 * min(nom, spice.at(t, card, 1.2e-3))), 1.0)
        c.check("P3" + n, "%s: boost output at 95%% after the card's +5V is applied" % corner, 1e3 * t_up, 2.0,
                "<=", "ms", fmt="%.2f")
    ch = budget.chain("worst")
    il = d.iob_vout_range()[2] * I_KBD / (d.IOB_ETA * ch["io_in"])
    c.check("P4", "inductor DC current at 500 mA from the worst card input vs the 2.7 A valley limit (min)", il,
            d.IOB_ILIM_VALLEY_MIN, "<=", "A", need=0.10)
    return c.done()


def gpu():
    """POW-008: the GPU card's HDMI +5V pin through the same boost, the card's
    PTC ahead of it, at every corner. The alternative, the PTC between the
    boost and the pin, is the worst-corner result less 55 mA x the PTC's
    R1max (its boost would see a slightly higher input, which only helps it
    regulate: the estimate errs low)."""
    c = Checks("POW-008 GPU card HDMI +5V, TPS61023 TI model (hw/power/boost.py gpu)")
    lo, nom, hi = d.iob_vout_range("gpu")
    name, lcsc, rmin, rmax, hold = d.GPU_PTCS[d.GPU_PTC]
    jobs = [("worst", "ahead"), ("typical", "ahead"), ("high", "ahead")]
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        res = dict(zip(jobs, pool.map(lambda j: run(j[0], "gpu", j[1]), jobs)))
    c.info("boost set point", "%.3f V nominal, DC range %.3f..%.3f V (732k/100k 0.1 %%); PTC %s (%s): %.2f..%.1f ohm, "
           "hold %.2f A at 40 C" % (nom, lo, hi, name, lcsc, rmin, rmax, hold))
    for corner, pos in jobs:
        t, vout, pin, card = res[(corner, pos)]
        n = corner[0]
        through = min(window(t, card, T_STEP - 100e-6, T_STEP)) >= nom * 1.01
        k_lo, k_hi = (1.0, 1.0) if through else (lo / nom, hi / nom)
        # the pin: the boost's output, less the PTC's drop if it sits after it
        drop_lo = min(window(t, vout, T_STEP, T_REL)) - min(window(t, pin, T_STEP, T_REL))
        vmin = min(window(t, vout, T_STEP, T_REL)) * k_lo - drop_lo
        vmax = max(window(t, pin, 0.2e-3, T_END)) * k_hi
        tag = "%s, PTC %s the boost" % (corner, pos)
        c.info(tag, "card +5V %.3f V at the boost (%s); pin %.3f V before the step" % (
            min(window(t, card, T_STEP, T_REL)), "pass-through" if through else "boosting",
            spice.at(t, pin, T_STEP - 10e-6)))
        c.check("H1" + n, "%s: HDMI pin minimum with a 10->55 mA step, DC low corner" % tag, vmin, d.HDMI_PIN_MIN,
                ">=")
        if corner == "worst":
            c.info("PTC after the boost", "the pin would be %.3f V at the worst corner: %.1f ohm (R1max) x 55 mA "
                   "= %.2f V off %.3f V, under %.1f V; the PTC goes ahead of the boost" % (
                       vmin - rmax * d.I_HDMI_PIN, rmax, rmax * d.I_HDMI_PIN, vmin, d.HDMI_PIN_MIN))
        c.check("H2" + n, "%s: HDMI pin maximum, DC high corner" % tag, vmax, d.HDMI_PIN_MAX, "<=",
                fix="a decision: above its set point the TPS61023 passes its input through, so the pin "
                    "follows a high source; a buck-boost (TPS63802DLAR, C2845237) regulates both ways")
    # the PTC ahead of the boost carries the boost's input current
    ch = budget.chain("worst")
    c.check("H3", "PTC ahead of the boost: its current (worst corner) vs %s hold at 40 C" % name, ch["igpu"],
            hold, "<=", "A", need=0.10, fix="SMD0805P020TF (C20976): the 100 mA part holds only 0.08 A at 40 C")
    # where the pin passes 5.3 V: the source voltage above which the boost passes through
    for vb in [5.0 + 0.01 * k for k in range(51)]:
        chh = budget.chain("typical", keyboard=0.0, wifi_3v3=budget.WIFI_IDLE_3V3, vbus=vb)
        _, v_b = d.gpu_i_5v(chh["gpu_in"], d.I_HDMI_PIN, False)
        if d.iob_vout(v_b, d.I_HDMI_PIN, "hi", "gpu") > d.HDMI_PIN_MAX:
            c.info("pass-through", "the pin exceeds %.1f V for a source above %.2f V at light load (USB 2.0 "
                   "allows 5.25 V, Type-C vSafe5V 5.5 V)" % (d.HDMI_PIN_MAX, vb))
            break
    return c.done()


if __name__ == "__main__":
    sys.exit(main())

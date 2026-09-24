#!/usr/bin/env python3
"""POW-001: the 3V3 buck (TLV62569, TI's PSpice transient model in ngspice).

    python3 hw/power/buck.py            (~1 min; the three decks run in parallel)
    python3 hw/power/buck.py wifi-card  a PROPOSAL, not a check of any board:
                                        a TLV62569 in place of the Wi-Fi card's
                                        AMS1117 (see POW-003 and THM-001)

The buck's input is 5V_SYS as budget.py builds it: the source behind the
whole input path's resistance, with the other 5 V loads drawing their share,
so 5V_SYS droops as it would. Two corners: the worst-case low 5V_SYS and
vSafe5V max. The output capacitance is the buck's own (design.BUCK_COUT,
DC-bias derated) plus the least decoupling the main board must fit
(design.C_3V3_DECOUPLE_MIN).

Runs:
  low, high   5V_SYS applied at t = 0 (ramping in 120 us, as the SY6280 does),
              10 mA load; at 1.3 ms a 0 -> 500 mA step (1 us edge), released
              at 1.6 ms
  full        start-up at the low corner into the full M1 3V3 load and all
              the 3V3 capacitance (design.C_3V3_TOTAL)

The simulated regulator sits at its nominal set point. Every waveform is
scaled to the DC corner (VFB +-2 % and the divider's 1 % resistors,
design.buck_vout_range) before it is compared with the rail limits, since
those errors scale the whole output, power-save offset and ripple included.

The TI model's switches are 10 mOhm, not the datasheet's 100/60 mOhm, so it
flatters efficiency: losses are computed in thermal.py, not taken from here.
"""

import concurrent.futures
import sys

import budget
import design as d
import spice
from spice import Checks

T_STEP, T_REL, T_END = 1.3e-3, 1.6e-3, 1.9e-3
I_LIGHT, I_STEP = 0.010, 0.500


def deck(v5_src, r_in, i_other, cout, load):
    return """
Vs src 0 PWL(0 0 {ton} {v5})
Rin src vin {rin}
Cbulk vin 0 {cbulk}
Iother vin 0 PWL(0 0 {ton} {iother})
X1 vin fb sw vin 0 TLV62569_TRANS
L1 sw out {l}
Cout out 0 {cout}
R1 out fb {r1}
R2 fb 0 {r2}
{load}
.options method=gear reltol=1e-3
.tran 20n {tend} 0 20n
.control
run
wrdata {{name}}.dat v(out) v(sw) v(vin)
.endc
""".format(v5=v5_src, ton=d.SY6280_TON, rin=r_in, cbulk=dict(d.C_5VSYS)["main 5V_SYS bulk"] + d.BUCK_CIN,
           iother=i_other, l=d.BUCK_L, cout=cout, r1=d.BUCK_R1, r2=d.BUCK_R2, load=load, tend="{tend}")


def corner(name):
    """(source V, input R, other 5 V loads A) so that 5V_SYS lands where budget.py puts it."""
    worst = budget.chain("worst")
    if name in ("low", "full"):
        r_in = d.CABLE_R_VBUS + d.CABLE_R_GND + d.R_RECEPTACLE + d.FUSE_IN_R_MAX + d.SY6280_RON_MAX + d.R_5VSYS
        i_other = worst["itot"] - budget.i_buck_in(worst["v5"])
        return d.VBUS_MIN, r_in, i_other
    return d.VBUS_MAX, 0.05, 0.0


def run(name):
    v5, r_in, i_other = corner(name)
    if name == "full":
        r_load = 3.318 / budget.i_3v3()
        load = "Rload out 0 %g\nCdec out 0 %g" % (r_load, d.C_3V3_TOTAL - d.BUCK_COUT - d.C_3V3_DECOUPLE_MIN)
        tend = 1.6e-3
    else:
        load = "Iload out 0 PWL(0 {a} {t1} {a} {t1e} {b} {t2} {b} {t2e} {a})".format(
            a=I_LIGHT, b=I_LIGHT + I_STEP, t1=T_STEP, t1e=T_STEP + 1e-6, t2=T_REL, t2e=T_REL + 1e-6)
        tend = T_END
    cout = d.BUCK_COUT * d.BUCK_COUT_EFF + d.C_3V3_DECOUPLE_MIN
    text = deck(v5, r_in, i_other, cout, load).replace("{tend}", "%g" % tend)
    spice.run("pow001_" + name, text.replace("{name}", "pow001_" + name), libs=("TLV62569_TRANS.lib",))
    return spice.wave("pow001_" + name)


def window(t, v, a, b):
    return [v[k] for k in range(len(t)) if a <= t[k] <= b]


def edges(t, v, a, b, level):
    ts = [t[k] for k in range(1, len(t)) if a <= t[k] <= b and v[k - 1] < level <= v[k]]
    return ts


def wifi_card():
    """The proposed Wi-Fi card regulator at POW-003's worst corner: the card's
    feed is the whole worst-case chain (the other loads' current is put
    through the slot's resistance too, which is pessimistic)."""
    c = Checks("PROPOSAL: TLV62569 on the Wi-Fi card, worst corner (hw/power/buck.py wifi-card)")
    w = budget.chain("worst")
    r_in = (d.CABLE_R_VBUS + d.CABLE_R_GND + d.R_RECEPTACLE + d.FUSE_IN_R_MAX + d.SY6280_RON_MAX + d.R_5VSYS
            + w["r_slot"])
    i_other = w["itot"] - d.I_WIFI_5V
    i0, i1 = d.ESP32_I_IDLE + d.WIFI_I_LEDS, d.ESP32_I_TX + d.WIFI_I_LEDS
    load = "Iesp out 0 PWL(0 {a} {t1} {a} {t1e} {b} {t2} {b} {t2e} {a})\nC3 out 0 100n".format(
        a=i0, b=i1, t1=T_STEP, t1e=T_STEP + 1e-6, t2=T_REL, t2e=T_REL + 1e-6)
    text = deck(d.VBUS_MIN, r_in, i_other, d.WIFI_COUT * d.CERAMIC_DERATE, load).replace("{tend}", "%g" % T_END)
    spice.run("wifi_card_buck", text.replace("{name}", "wifi_card_buck"), libs=("TLV62569_TRANS.lib",))
    t, vout, vsw, vin = spice.wave("wifi_card_buck")
    k_lo = d.buck_vout_range()[0] / d.buck_vout()
    c.info("card +5V", "%.3f V during the burst" % min(window(t, vin, T_STEP, T_REL)))
    c.check("F1", "ESP32-C3 supply minimum in a 350 mA burst, DC low corner", min(window(t, vout, T_STEP, T_REL))
            * k_lo, d.ESP32_VDD_MIN, ">=")
    return c.done()


def main():
    if sys.argv[1:] == ["wifi-card"]:
        return wifi_card()
    c = Checks("POW-001 3V3 buck, TLV62569 TI model (hw/power/buck.py)")
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        res = dict(zip(("low", "high", "full"), pool.map(run, ("low", "high", "full"))))
    vnom = d.buck_vout()
    lo_dc, hi_dc = d.buck_vout_range()
    c.info("3V3 set point", "%.3f V nominal, DC range %.3f..%.3f V (VFB +-2%%, %.1f%% divider)" % (
        vnom, lo_dc, hi_dc, 100 * d.BUCK_RES_TOL))
    c.check("P1", "3V3 DC low vs MAX811T reset threshold (max)", lo_dc, d.MAX811T_VTH_MAX, ">=")

    for name in ("low", "high"):
        t, vout, vsw, vin = res[name]
        v_ss = sum(window(t, vout, T_STEP - 100e-6, T_STEP)) / len(window(t, vout, T_STEP - 100e-6, T_STEP))
        k_lo, k_hi = lo_dc / vnom, hi_dc / vnom                # sim -> worst DC corner
        t95 = next(t[k] for k in range(len(t)) if vout[k] >= 0.95 * v_ss)
        peak_start = max(window(t, vout, 0, T_STEP - 100e-6))
        vmin = min(window(t, vout, T_STEP, T_REL))
        vmax = max(window(t, vout, T_STEP - 100e-6, T_END))
        c.info("corner %s" % name, "5V_SYS %.3f V at the step; 3V3 settles at %.4f V at 10 mA (set point "
               "%.4f V)" % (spice.at(t, vin, T_STEP + 50e-6), v_ss, vnom))
        c.check("P2" + name[0], "%s: start-up, 3V3 at 95%% after 5V_SYS applied" % name, 1e3 * t95, 2.0, "<=",
                "ms", fmt="%.2f")
        c.check("P3" + name[0], "%s: start-up peak, at the DC high corner" % name, peak_start * k_hi,
                d.V3V3_MAX, "<=")
        c.check("P4" + name[0], "%s: 0->500 mA step, minimum at the DC low corner (droop %.0f mV)" % (
            name, 1e3 * (v_ss - vmin)), vmin * k_lo, d.V3V3_MIN, ">=")
        c.check("P5" + name[0], "%s: light load and 500->0 mA release, maximum at the DC high corner" % name,
                vmax * k_hi, d.V3V3_MAX, "<=")
        below = [t[k] for k in range(len(t)) if t[k] >= T_STEP and vout[k] * k_lo < d.MAX811T_VTH_MAX]
        dur = (below[-1] - below[0]) if below else 0.0
        c.check("P6" + name[0], "%s: time the step spends below the MAX811T threshold (DC low corner)" % name,
                1e6 * dur, 1e6 * d.MAX811_GLITCH_S, "<=", "us", fmt="%.1f")
        # ripple and switching frequency: PWM at 510 mA, power-save at 10 mA
        for label, a, b in (("510 mA", T_REL - 150e-6, T_REL), ("10 mA", T_STEP - 200e-6, T_STEP)):
            w = window(t, vout, a, b)
            n = edges(t, vsw, a, b, 1.0)
            f = (len(n) - 1) / (n[-1] - n[0]) if len(n) > 2 else 0.0
            c.info("ripple %s %s" % (name, label), "%.1f mVpp at %.0f kHz" % (1e3 * (max(w) - min(w)), f / 1e3))
    t, vout, vsw, vin = res["full"]
    t95 = next((t[k] for k in range(len(t)) if vout[k] >= 0.95 * vnom), 1.0)
    c.check("P7", "start-up into the full M1 load and %.0f uF: 3V3 at 95%%" % (1e6 * d.C_3V3_TOTAL),
            1e3 * t95, 2.0, "<=", "ms", fmt="%.2f")
    up = next(k for k in range(len(t)) if vin[k] >= 0.95 * vin[-1])
    c.check("P8", "5V_SYS minimum once up, while the buck starts into it (buck UVLO 2.45 V max + 10%)",
            min(vin[up:]), 2.45 * 1.1, ">=")
    c.check("P9", "dropout: 5V_SYS worst low vs VOUT + I x (RDS(on) hot + DCR)", budget.chain("worst")["v5"],
            vnom + budget.i_3v3() * (d.BUCK_RHS * d.BUCK_RDS_HOT + d.BUCK_DCR), ">=")
    return c.done()


if __name__ == "__main__":
    sys.exit(main())

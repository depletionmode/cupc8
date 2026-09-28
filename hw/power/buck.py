#!/usr/bin/env python3
"""POW-001: the 3V3 buck (TLV62569, TI's PSpice transient model in ngspice).

    python3 hw/power/buck.py            (~1 min; the three decks run in parallel)
    python3 hw/power/buck.py wifi-card  POW-003: the Wi-Fi card's own TLV62569
                                        (hw/boards/wifi.py U2) in an ESP32-C3 TX
                                        burst, at the typical and worst corners

The buck's input is 5V_SYS as budget.py builds it: the source behind the
whole input path's resistance, with the other 5 V loads drawing their share,
so 5V_SYS droops as it would. Two corners: the worst-case low 5V_SYS and
vSafe5V max. The output capacitance is the buck's own (design.BUCK_COUT,
DC-bias derated) plus the least decoupling the main board must fit
(design.C_3V3_DECOUPLE_MIN).

Runs:
  low, high   5V_SYS applied at t = 0 (ramping in 120 us: the attach itself, with
              the eFuse's slower dVdt ramp, is POW-004's),
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
from pathlib import Path
import sys

import budget
import design as d
import spice
import wifi_board
import wifi_ground
import wifi_parts
from spice import Checks

T_APPLY = 120e-6         # 5V_SYS rise in these decks (see the docstring)
T_STEP, T_REL, T_END = 1.3e-3, 1.6e-3, 1.9e-3
I_LIGHT, I_STEP = 0.010, 0.500
WIFI_CAP_ESR_SCENARIO = 0.100  # ohm each; sensitivity scenario, no vendor maximum yet


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
""".format(v5=v5_src, ton=T_APPLY, rin=r_in, cbulk=dict(d.C_5VSYS)["main 5V_SYS bulk"] + d.BUCK_CIN,
           iother=i_other, l=d.BUCK_L, cout=cout, r1=d.BUCK_R1, r2=d.BUCK_R2, load=load, tend="{tend}")


def corner(name):
    """(source V, input R, other 5 V loads A) so that 5V_SYS lands where budget.py puts it."""
    worst = budget.chain("worst")
    if name in ("low", "full"):
        r_in = d.r_in(True)
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


def wifi_deck(corner, r_board5, r_board3, r_ground, esr=WIFI_CAP_ESR_SCENARIO,
              r_contact=0.0, r_board_return=0.0, caps=None, divider=None, i_load=None):
    """POW-003: hw/boards/wifi.py as built. The source, the input path and the
    other loads feed 5V_SYS; the card hangs off it through the slot's feed
    (PTC, link, sense, contacts), so the slot's +5V sags with the burst as it
    will.

    TI's TLV62569_TRANS subcircuit references its reference, soft start,
    comparators and drivers to global node 0, not to its GND pin. Node 0 is
    therefore U2's GND pin (C1/C2/R10 return there, as on the board), and the
    slot/main-board side sits at `slot_gnd`, below it by the J1 return. Lifting
    the GND pin above node 0 instead makes the model regulate FB against the
    far ground, which multiplies the return drop by 1 + R9/R10."""
    ch = budget.chain(corner)
    worst = corner == "worst"
    r_in = d.r_in(worst)
    i0, i1 = d.ESP32_I_IDLE + d.WIFI_I_LEDS, d.WIFI_I_3V3 if i_load is None else i_load
    r1, r2 = divider or (d.WIFI_BUCK_R1, d.WIFI_BUCK_R2)
    # effective (C1, C2, C3); default: the 60 % scenario and nominal C3
    cin, cout, chf = caps or (d.WIFI_CIN * d.CERAMIC_DERATE, d.WIFI_COUT * d.CERAMIC_DERATE, d.WIFI_COUT_HF)
    return """
Vs src slot_gnd PWL(0 0 {ton} {vbus})
Rin src v5 {rin}
Cbulk v5 slot_gnd {cbulk}
Iother v5 slot_gnd PWL(0 0 {ton} {iother})
Rslot v5 card {rslot}
Rboard5 card vin {rboard5}
Rboardreturn 0 slot_gnd {rboardreturn:.9g}
Rcesr1 vin c1term {esr}
C1 c1term 0 {cin}
X1 vin fb sw vin 0 TLV62569_TRANS
L1 sw buck {l}
Rcesr2 buck c2term {esr}
C2 c2term 0 {cout}
Rboard3 buck out {rboard3}
Rcesr3 out c3term {esr}
C3 c3term return {chf}
Rground return 0 {rground}
R9 buck fb {r1}
R10 fb 0 {r2}
Iesp out return PWL(0 {i0} {t1} {i0} {t1e} {i1} {t2} {i1} {t2e} {i0})
.options method=gear reltol=1e-3
.tran 20n {tend} 0 20n
.control
run
wrdata {{name}}.dat v(out,return) v(sw) v(card)
.endc
""".format(vbus=ch["vbus"], ton=T_APPLY, rin=r_in, cbulk=dict(d.C_5VSYS)["main 5V_SYS bulk"] + d.BUCK_CIN,
           iother=ch["itot"] - ch["iwifi"], rslot=ch["r_slot"], rboard5=r_board5,
           rboard3=r_board3, rground=r_ground, rboardreturn=r_board_return + r_contact, esr=esr,
           cin=cin, l=d.WIFI_BUCK_L, cout=cout, chf=chf, r1=r1,
           r2=r2, i0=i0, i1=i1, t1=T_STEP, t1e=T_STEP + 1e-6, t2=T_REL, t2e=T_REL + 1e-6, tend=T_END)


def run_wifi(corner, r_board5, r_board3, r_ground, *, esr=WIFI_CAP_ESR_SCENARIO,
             r_contact=0.0, r_board_return=0.0, caps=None, divider=None, i_load=None, tag=''):
    name = "pow003_" + corner + tag
    spice.run(name, wifi_deck(corner, r_board5, r_board3, r_ground, esr, r_contact,
                              r_board_return, caps, divider, i_load).replace("{name}", name),
              libs=("TLV62569_TRANS.lib",))
    return spice.wave(name)


def wifi_card(out=None):
    """POW-003: the Wi-Fi card's TLV62569 (U2, L1, C1-C3, R9/R10), an ESP32-C3
    TX burst at the typical and worst corners."""
    c = Checks("POW-003 Wi-Fi card 3V3, TLV62569 TI model (hw/power/buck.py wifi-card)")
    bad = d.wifi_board_mismatches()
    for ref, want, got in bad:
        c.info(ref, "hw/boards/wifi.py has %s, these checks model %s (design.WIFI_BOARD)" % (got, want))
    c.check("F0", "Wi-Fi card regulator parts in hw/boards/wifi.py that differ from the model", len(bad), 0, "<=",
            "", fmt="%d")
    out = Path(out) if out else Path(spice.ROOT) / 'build/hw/wifi'
    import boardevidence
    from boardcheck import check_report
    import json
    boardevidence.validate('wifi', out)
    check_report(json.loads((out / 'drc.json').read_text()), 'drc')
    circuit = wifi_board.topology(out / 'wifi.net')
    unbound = wifi_parts.binding_errors(out / 'wifi.net')
    for ref, want, got in unbound:
        c.info(ref, 'netlist LCSC %s, manufacturer data in hw/power/wifi_parts.py is for %s' % (got, want))
    c.check('F0p', 'fitted U1/U2/L1/C1-C3/R9/R10 LCSC parts without the sourced data used here',
            len(unbound), 0, '<=', '', fmt='%d')
    r_board5, r_board3 = wifi_board.routes(out / 'wifi.kicad_pcb', out / 'fab/order.json', circuit)
    r_ground, coarse, fine, discrepancy = wifi_ground.compare(out / 'wifi.kicad_pcb')
    edge, _, _, edge_errors = wifi_ground.compare_card_edge(out / 'wifi.kicad_pcb')
    r_board_return = max(edge['buck_to_J1_A'], edge['buck_to_J1_B'])
    c.info('routed board', '2-layer 1.6 mm, +5V %.1f mOhm, 3V3 %.1f mOhm, GND return %.1f mOhm; '
           '%d GND vias' %
           (1e3 * r_board5, 1e3 * r_board3, 1e3 * r_ground, coarse[1]))
    c.info('GND mesh', '0.25 mm %.1f mOhm (%d/%d cells); 0.125 mm %.1f mOhm (%d/%d cells); '
           'discrepancy %.0f%%' %
           (1e3 * coarse[0], *coarse[2], 1e3 * fine[0], *fine[2], 100 * discrepancy))
    c.info('J1 return sensitivity', 'U2.2 to J1 GND %.1f mOhm worst of two face/path scenarios; '
           'U1.1 to J1 GND %.1f/%.1f mOhm A/B; maximum mesh discrepancy %.1f%%. '
           'Contact and shared-plane resistance are unbounded' %
           (1e3 * r_board_return, 1e3 * edge['esp_to_J1_A'],
            1e3 * edge['esp_to_J1_B'], 100 * max(edge_errors.values())))
    vnom = d.buck_vout(d.WIFI_BUCK_R1, d.WIFI_BUCK_R2)
    lo_dc, hi_dc = wifi_parts.vout_range()
    k_lo, k_hi = lo_dc / vnom, hi_dc / vnom                    # sim -> worst DC corner
    # stress corner: minimum tolerance, typical DC-bias loss (Samsung data) at
    # the highest card input / DC high output, full TCC and life-test drift
    fitted = wifi_parts.FITTED
    stress = (wifi_parts.stress_capacitance(fitted['C1'], d.VBUS_MAX),
              wifi_parts.stress_capacitance(fitted['C2'], hi_dc),
              wifi_parts.stress_capacitance(fitted['C3'], hi_dc))
    c.info('capacitors', 'C1/C2/C3 each %.0f mOhm ESR sensitivity scenario; C1/C2 at 60%% nominal '
           'capacitance, and a stress corner of %.2f/%.2f/%.3f uF; manufacturer typical ESR at '
           '1.5 MHz %.1f mOhm (C1/C2), no published maximum' % (
               1e3 * WIFI_CAP_ESR_SCENARIO, *(1e6 * x for x in stress),
               1e3 * wifi_parts.CAPACITORS[fitted['C2']]['esr_typ'][1.5e6]))
    runs = (("typical", None), ("worst", None), ("worst", stress))
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        waves = list(pool.map(lambda run: run_wifi(
            run[0], r_board5, r_board3, r_ground, r_board_return=r_board_return, caps=run[1],
            tag='_stress' if run[1] else ''), runs))
    res = {"typical": waves[0], "worst": waves[1], "stress": waves[2]}
    c.info("3V3 set point", "%.3f V nominal, DC range %.3f..%.3f V (VFB %.3f..%.3f V at 25 C, "
           "+-%.1f%% typical over temperature; R9/R10 tolerance + TCR to %.0f C)" % (
               vnom, lo_dc, hi_dc, wifi_parts.TLV62569['vfb_min'], wifi_parts.TLV62569['vfb_max'],
               100 * wifi_parts.TLV62569['vfb_temp_typ'], wifi_parts.RESISTOR_T_MAX))
    for corner in ("typical", "worst", "stress"):
        t, vout, vsw, vcard = res[corner]
        n = corner[0]
        vcard_min = min(window(t, vcard, T_STEP, T_REL))
        c.info(corner, "+5V at U2 (VIN to U2 GND) %.3f V during the burst; 3V3 %.3f V before it" % (
            vcard_min, spice.at(t, vout, T_STEP - 10e-6)))
        c.check("F1" + n, "%s: ESP32-C3 supply minimum in a %.0f mA TX burst, DC low corner" % (
            corner, 1e3 * d.WIFI_I_3V3), min(window(t, vout, T_STEP, T_REL)) * k_lo, d.ESP32_VDD_MIN, ">=")
        c.check("F2" + n, "%s: start-up, light load and burst release, maximum at the DC high corner" % corner,
                max(vout) * k_hi, d.ESP32_VDD_MAX, "<=")
        # 100 % duty: the input must still cover VOUT + I x (high side hot + DCR)
        c.check("F3" + n, "%s: +5V at U2 in the burst vs VOUT high + I x (RDS(on) hot + DCR)" % corner,
                vcard_min, hi_dc + d.WIFI_I_3V3 * (d.BUCK_RHS * d.BUCK_RDS_HOT + d.WIFI_BUCK_DCR), ">=")
    # The GND raster is a fixed-width path scenario, not a solved effective
    # resistance. The vendor's published capacitor data has no maximum ESR;
    # neither pad/contact resistance nor local thermal coupling is calibrated.
    c.check('F4', 'GND mesh discrepancy <= 10%', discrepancy, 0.10, '<=', '', fmt='%.3f')
    c.check('F4e', 'J1 return mesh discrepancy <= 10%',
            max(edge_errors.values()), 0.10, '<=', '', fmt='%.3f')
    c.check('F5', 'C1/C2/C3 guaranteed ESR maximum available for the fitted parts',
            int(wifi_parts.guaranteed('esr_max')), 1, '>=', '', fmt='%d')
    c.check('F6', 'routed GND pad/spoke/contact resistance validated', 0, 1, '>=', '', fmt='%d')
    c.check('F7', 'C1/C2/C3 minimum effective capacitance at bias, temperature and age validated',
            int(wifi_parts.guaranteed('min_effective_c')), 1, '>=', '', fmt='%d')
    c.check('F8', 'ESP32 and other 3V3 load-current envelope validated over operating corners',
            int(wifi_parts.load_envelope_bounded()), 1, '>=', '', fmt='%d')
    return c.done()


def main():
    if sys.argv[1:2] == ["wifi-card"]:
        if len(sys.argv) not in (2, 3):
            sys.exit('usage: buck.py wifi-card [board-build-directory]')
        return wifi_card(sys.argv[2] if len(sys.argv) == 3 else None)
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

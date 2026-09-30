#!/usr/bin/env python3
"""IC-005: the IO card's keyboard-port switch, a TPS2553DBVR-1
(doc/hardware/io-port-switch-proposal.md), on the board since David approved it
with the 45.3k set resistor.

    python3 hw/power/io_port_switch.py      (~25 s, 5 behavioural + 8 TI-model ngspice runs in build/power)

S checks use only guaranteed datasheet limits (TI SLVS841F, sha256 88e45370...):
the IOS min/max equations of section 9.5.1 (which cover process and
temperature, -40..125 C) widened to enclose the tested table rows of 7.5,
with the ILIM resistor's tolerance and TCR on top. T checks run a behavioural
ngspice model of the switch between the TPS61023's output capacitors and the
port: its current limit, the soft start, a hard short with the published
(typical-only) response time and a 10x stress value, and the latch-off
after the FAULT deglitch. The deglitch (5..10 ms), turn-on and reverse
figures are guaranteed; the response time and peak current are not.
"""
import concurrent.futures
import sys

import boost
import budget
import design as d
import spice
from spice import Checks

# ---- TPS2553DBVR-1 (C111738), SLVS841F. The -1 is the latch-off version. ----
PART, LCSC = "TPS2553DBVR-1", "C111738"
IOS_EQ = {"min": (25230.0, 1.016), "max": (22980.0, 0.94)}   # 9.5.1: IOS(mA) = k / RILIM(kOhm)^n
# 7.5 tested rows (RILIM kOhm, min mA, max mA) over -40..125 C (15k: -40..105 C)
IOS_TABLE = ((15.0, 1610, 1800), (20.0, 1200, 1375), (49.9, 475, 565), (210.0, 110, 150))
RILIM_RANGE = (15e3, 232e3)          # recommended, 1 %
RDS_MAX = 0.135                      # DBV, -40..125 C
RDS_PEAK = 0.060                     # assumed: no minimum published: 70 % of the 85 mOhm typ, for the peak current
T_RESP_TYP = 2e-6                    # tIOS, VIN = 5 V: typical only (no max)
T_RESP_STRESS = 20e-6                # 10 x: the top of figure 15 (typical curve); an assumed stress bound
T_DEGLITCH = (5e-3, 10e-3)           # FAULT deglitch on overcurrent, min/max (guaranteed)
T_REVERSE = (2e-3, 6e-3)             # reverse-voltage deglitch, min/max
V_REVERSE = (0.095, 0.190)           # VOUT - VIN trip
T_ON_MAX = 3e-3                      # turn-on time, 1 uF / 100 ohm
T_RISE = (0.7e-3, 1.5e-3)            # 10..90 % rise, 1 uF / 100 ohm, VIN 2.5..6.5 V (0.7 typ at 2.5 V)
VIN_ABS, VIN_MAX = 7.0, 6.5          # absolute max (IN, OUT, FAULT), recommended max
VIN_ABS_MIN = -0.3
UVLO_MIN = 2.35                      # IN rising threshold 2.35 typ, 2.45 max; the model turns off below 2.35 V
FAULT_VOL, FAULT_VOL_I = 0.180, 1e-3 # VOL max at 1 mA sink
FAULT_ILEAK = 1e-6
EN_VIH, EN_VIL, EN_I = 1.1, 0.66, 0.5e-6
THETA_JA = 182.6
OTSD_LIMIT_MIN = 135.0               # thermal shutdown while in current limit (min)

# ---- the circuit (hw/boards/io.py) ----
R_ILIM = 45.3e3                      # 0402WGF4532TCE (C26980), 1 %, 100 ppm/C
R_ILIM_TOL = 0.01
R_ILIM_TCR = 100e-6
R_ILIM_DT = 60.0                     # resistor at 0..85 C: <= 60 K from the 25 C rating
R_PULLUP = 10e3                      # FAULT to 3V3 (C25744), GPIO8
R_EN = 100e3                         # R11, kept
C_IN_LOCAL = 1e-6                    # new C25 1 uF at IN (7.3 asks >= 0.1 uF; 100 nF rings to 8.5 V, T5)
L_IN = 20e-9                         # engineering bound: 13.85 mm C24-to-U5 route, with ground return
C_PORT = (120e-6, 10e-6)             # C21 100 uF +20 %, and a USB device's 10 uF maximum
C_BOOST = 26e-6                      # C23/C24 2 x 22 uF derated at 5 V (power.md)

# ---- RP2040 GPIO8 (datasheet 5.5.3, IOVDD 3.3 V) and the card's 3V3 ----
GPIO_VIL, GPIO_VIH, GPIO_ILEAK = 0.8, 2.0, 1e-6
V33 = (3.135, 3.465)
I_KBD_ATTACH = 0.100                 # USB 2.0: an unconfigured device draws <= 100 mA
TPS61023_ABS = d.IOB_VIN_ABS         # 6.0 V on its VOUT, which is U5 IN
VBOOST_MAX = 5.431                   # POW-007 P2: the port maximum in pass-through at vSafe5V max


def ios_eq(rilim, which):
    k, n = IOS_EQ[which]
    return k / (rilim / 1e3) ** n / 1e3


def envelope():
    """How far the tested rows sit outside the equations (min factor <= 1, max factor >= 1)."""
    return (min(1.0, min(lo / 1e3 / ios_eq(r * 1e3, "min") for r, lo, _ in IOS_TABLE)),
            max(1.0, max(hi / 1e3 / ios_eq(r * 1e3, "max") for r, _, hi in IOS_TABLE)))


def ios_window(rilim=R_ILIM, tol=R_ILIM_TOL, tcr=R_ILIM_TCR, dt=R_ILIM_DT):
    """Guaranteed current limit (min, max) in A for a nominal RILIM: the highest
    resistance gives the lowest limit."""
    spread = tol + tcr * dt
    lo_env, hi_env = envelope()
    return ios_eq(rilim * (1 + spread), "min") * lo_env, ios_eq(rilim * (1 - spread), "max") * hi_env


def fault_levels(r_pullup=R_PULLUP):
    """GPIO8 (low max, high min) with FAULT asserted / released. VOL is only
    specified at 1 mA: a pull-up that sinks more is unbounded (inf)."""
    i_sink = V33[1] / r_pullup
    vol = FAULT_VOL if i_sink <= FAULT_VOL_I else float("inf")
    voh = V33[0] - (FAULT_ILEAK + GPIO_ILEAK) * r_pullup
    return vol, voh


def analytic_checks(c, rilim=R_ILIM, tol=R_ILIM_TOL, r_pullup=R_PULLUP):
    lo, hi = ios_window(rilim, tol)
    c.info("current limit", "RILIM %.1fk %.0f %% + %.0f ppm/C over %.0f K: guaranteed %.1f..%.1f mA "
           "(equation envelope %.4f / %.4f)" % (rilim / 1e3, 100 * tol, R_ILIM_TCR * 1e6, R_ILIM_DT,
                                               1e3 * lo, 1e3 * hi, *envelope()))
    c.check("S0", "RILIM within the recommended range", rilim / 1e3, RILIM_RANGE[0] / 1e3, ">=", "k", fmt="%.1f")
    c.check("S1", "minimum current limit vs the keyboard's 500 mA (USB 2.0 high-power device)", lo,
            d.I_KEYBOARD, ">=", "A", fix="a lower RILIM")
    ch = budget.chain("worst", keyboard=hi)
    il = d.iob_vout_range()[2] * hi / (d.IOB_ETA * ch["io_in"])
    c.check("S2", "boost inductor DC current at the maximum limit, worst card input %.2f V, vs the 2.7 A "
            "valley limit" % ch["io_in"], il, d.IOB_ILIM_VALLEY_MIN, "<=", "A", need=0.10)
    c.check("S3", "machine VBUS current, worst corner, keyboard port at the maximum limit, vs the eFuse's "
            "minimum limit", ch["itot"], d.insw_ilim()[0], "<=", "A", need=0.10)
    c.info("residual", "a non-compliant device drawing up to %.0f mA is not limited or flagged: the IO card's "
           "+5V is then %.3f A at the worst corner (slot.md 0.80 A; slot PTC hold %.2f A at 40 C). Only the "
           "boost is on the slot's +5V, so a PTC trip drops the port alone." % (
               1e3 * hi, ch["iio"], d.SLOT_PTC_IHOLD_40C))
    w = budget.chain("worst")
    c.check("S4", "IO card +5V with a 500 mA keyboard vs slot.md's %.2f A (as B10)" % d.SLOT_5V_MAX,
            w["iio"], d.SLOT_5V_MAX, "<=", "A")
    port = w["kbd_port"] + d.I_KEYBOARD * (d.IOSW_RON_MAX - RDS_MAX)
    c.check("S5", "keyboard VBUS, worst DC corner, 500 mA through RDS(on) max %.0f mOhm" % (1e3 * RDS_MAX),
            port, d.USB_PORT_MIN, ">=")
    c.check("S6", "U5 IN highest (the eFuse's OVLO trip, max, in pass-through) vs its 6.5 V recommended max",
            d.insw_ovlo()[1], VIN_MAX, "<=")
    vol, voh = fault_levels(r_pullup)
    c.check("S7", "GPIO8 low with FAULT asserted (VOL at <= 1 mA sink) vs RP2040 VIL", vol, GPIO_VIL, "<=",
            need=0.10, fix="a pull-up that sinks <= 1 mA at 3.465 V (>= 3.5 kOhm)")
    c.check("S8", "GPIO8 high with FAULT released (3V3 min less leakage x pull-up) vs RP2040 VIH", voh,
            GPIO_VIH, ">=", need=0.10)
    v_en = EN_I * R_EN
    c.check("S9", "EN held off by R11 while the RP2040 is in reset (leakage x 100k) vs VIL", v_en, EN_VIL,
            "<=", need=0.10)
    p = d.I_KEYBOARD ** 2 * RDS_MAX
    c.check("S10", "junction at 500 mA, RDS(on) max, %.0f C ambient" % d.AMBIENT_C, d.AMBIENT_C + p * THETA_JA,
            125.0, "<=", "C", fmt="%.1f")
    return lo, hi


# ---------------------------------------------------------------------------
# Behavioural transient model
# ---------------------------------------------------------------------------
T_SHORT = 5e-3
I_BOOST_STANDIN = 4.0                # the boost as a current-limited source (T1-T3 only; T4/T5 use TI's model)


def deck(case, vb, ios, t_resp=T_RESP_TYP, l_short=1e-12, t_rise=T_RISE[0] / 2, t_deg=T_DEGLITCH[1],
         r_load=5.0 / d.I_KEYBOARD, latch=True):
    """case 'short': 500 mA steady, a hard short at T_SHORT; the limit is off
    (100 A) for t_resp, then falls to ios in 0.1 us; the -1 latches off
    t_deg after the limit engages. case 'start': EN at 0.1 ms into the port
    capacitance and a 100 mA attach load, ios the minimum limit."""
    t_en = 0.1e-3 if case == "start" else 0.0
    if case == "short":
        ilim = "PWL(0 {i} {a} {i} {b} 100 {c} 100 {e} {i})".format(
            i=ios, a=T_SHORT, b=T_SHORT + 1e-9, c=T_SHORT + t_resp, e=T_SHORT + t_resp + 1e-7)
        t_off = T_SHORT + t_resp + t_deg
        en = "PWL(0 1 {a} 1 {b} 0)".format(a=t_off, b=t_off + 1e-6) if latch else "DC 1"
        short = "PWL(0 0 {a} 0 {b} 1)".format(a=T_SHORT, b=T_SHORT + 1e-9)
        t_end, r_load = t_off + 1e-3, r_load
    else:
        ilim, en, short, t_end = "DC %g" % ios, "DC 1", "DC 0", 8e-3
        r_load = 5.0 / I_KBD_ATTACH
    return """
Bbst 0 bcap I = min(max(({vb} - V(bcap)) * 50, 0), {ibst})
Cbst bcap bx {cb}
Rbesr bx 0 0.003
Lin bcap bin {lin}
Rtrk bin vin 0.005
Cin vin cx {cin}
Rcin cx 0 0.01
Vilim ilim 0 {ilim}
Ven en 0 {en}
Vg g 0 PWL(0 0 {ten} 0 {tr} 10)
Bsw vin vs I = V(en) * min(max(min(V(g), V(vin)) - V(vs), 0) / {rds}, V(ilim))
Vsense vs vout 0
Cport vout px {cport}
Rpesr px 0 0.005
Ckbd vout kx {ckbd}
Rkesr kx 0 0.05
Rload vout 0 {rl}
Vshort sc 0 {short}
S1 vout sh sc 0 SSHORT
Lsh sh 0 {lsh}
.model SSHORT SW(Ron=0.02 Roff=1e9 Vt=0.5 Vh=0.1)
.tran 0.05u {tend} 0 0.2u uic
.meas tran ipk MAX I(Vsense) FROM={t0} TO={t1}
.meas tran vinmax MAX V(vin) FROM={t0} TO={t1}
.meas tran vbmax MAX V(bcap) FROM={t0} TO={t1}
.meas tran vinmin MIN V(vin) FROM={t0} TO={t1}
.meas tran iset FIND I(Vsense) AT={tset}
.meas tran ioff FIND I(Vsense) AT={tend}
.meas tran vend FIND V(vout) AT={tend}
.meas tran vpre FIND V(vout) AT={t0}
""".format(vb=vb, ibst=I_BOOST_STANDIN, cb=C_BOOST, lin=L_IN, cin=C_IN_LOCAL, ilim=ilim, en=en, ten=t_en, tr=t_en + t_rise,
           rds=RDS_PEAK if case == "short" else RDS_MAX, cport=C_PORT[0], ckbd=C_PORT[1], rl=r_load,
           short=short, lsh=l_short, tend=t_end,
           t0=T_SHORT - 1e-6 if case == "short" else 1e-6, t1=T_SHORT + 1e-3 if case == "short" else t_end,
           tset=T_SHORT + 1e-3 if case == "short" else t_end)


def start_up(ios):
    """EN into the port capacitance with a 100 mA attach load at the minimum
    limit: how long the switch sits in current limit (must end before the
    shortest FAULT deglitch, or the -1 latches off at every attach)."""
    tag = "io_port_switch_start"
    m = spice.run(tag, deck("start", d.iob_vout_range()[0], ios).replace(
        ".meas tran ipk", ".meas tran tlim_on WHEN I(Vsense)={a} RISE=1\n"
        ".meas tran tlim_off WHEN I(Vsense)={a} FALL=LAST\n"
        ".meas tran tup WHEN V(vout)={u} RISE=1\n"
        ".meas tran ipk".format(a=0.98 * ios, u=d.USB_PORT_MIN)))
    return m


def short(vb, ios, t_resp, l_short, tag):
    return spice.run("io_port_switch_" + tag, deck("short", vb, ios, t_resp, l_short))


TI_ON, TI_SHORT, TI_END = 0.45e-3, 0.8e-3, 1.0e-3
T_FALL = 1e-7                        # the limit's clamp from the overdriven peak to IOS: not published
RESPONSES = ((T_RESP_TYP, "typ"), (T_RESP_STRESS, "stress"))
FALLS = ((1e-7, "fast"), (1e-6, "slow"))
SHORTS = ((50e-9, "plug"), (0.5e-6, "cable"))   # a short at the receptacle, and at the end of a cable


def ti_deck(corner, ios, t_resp, l_short, l_in=L_IN, c_in=C_IN_LOCAL, t_fall=T_FALL):
    """POW-007's chain (source, input path, slot, TI's TPS61023 model, 2 x 22 uF)
    with this switch (the earlier design fitted an SY6280AAC). The port capacitance is held at
    5.0 V until the switch turns on at 0.45 ms (the attach itself is T1's), a
    500 mA keyboard, then a short at 0.8 ms. For the peak current and the
    boost output / U5 IN excursions only."""
    base = boost.deck(corner)
    head = base.split("Rsw vout port")[0]
    return head + """Lin vout bin {lin}
Rtrk bin vin 0.005
Cin vin cx {cin}
Rcin cx 0 0.01
Vilim ilim 0 PWL(0 {i} {a} {i} {b} 100 {c} 100 {e} {i})
Vg g 0 PWL(0 0 {ton} 0 {tr} 1)
Bsw vin vs I = V(g) * 0.5 * (1 + tanh((V(vin) - {uvlo}) / 0.02)) * V(ilim) * tanh(V(vin, vs) / ({rds} * V(ilim)))
Vpc pc 0 5.0
Vpcc pcc 0 PWL(0 1 {ton} 1 {tr} 0)
Spc pc port pcc 0 SPC
.model SPC SW(Ron=0.05 Roff=1e9 Vt=0.5 Vh=0.1)
Vsense vs port 0
Cport port px {cport}
Rpesr px 0 0.005
Ckbd port kx {ckbd}
Rkesr kx 0 0.05
Rload port 0 {rl}
Vshort sc 0 PWL(0 0 {a} 0 {b} 1)
S1 port sh sc 0 SSHORT
Lsh sh 0 {lsh}
.model SSHORT SW(Ron=0.02 Roff=1e9 Vt=0.5 Vh=0.1)
.options method=gear reltol=1e-3
.tran 20n {tend} 0 20n
.meas tran ipk MAX I(Vsense) FROM={t0} TO={tend}
.meas tran vinmax MAX V(vin) FROM={t0} TO={tend}
.meas tran vinmin MIN V(vin) FROM={t0} TO={tend}
.meas tran vbmax MAX V(vout) FROM={t0} TO={tend}
.meas tran vbpre FIND V(vout) AT={t0}
.meas tran vpre FIND V(port) AT={t0}
.meas tran iend FIND I(Vsense) AT={tend}
""".format(lin=l_in, cin=c_in, i=ios, a=TI_SHORT, b=TI_SHORT + 1e-9, c=TI_SHORT + t_resp,
           e=TI_SHORT + t_resp + t_fall, ton=TI_ON, tr=TI_ON + 20e-6, uvlo=UVLO_MIN, rds=RDS_PEAK, cport=C_PORT[0],
           ckbd=C_PORT[1], rl=5.0 / d.I_KEYBOARD, lsh=l_short, tend=TI_END, t0=TI_SHORT - 1e-6)


def ti_short(args):
    """One TI-model short. TI's TPS61023 model fails to converge for some
    limit values above ~0.637 A ("timestep too small", typical response, cable
    short, fast clamp): the run is then repeated with the limit lowered in 5 mA
    steps (at most 4 times). The excursions do not depend on the limit
    there (U5 IN max 5.216..5.218 V from 0.55 to 0.636 A), and 'ios_run'
    reports the limit actually simulated."""
    tag, kw = args
    for step in range(5):
        ios = kw["ios"] - 5e-3 * step
        try:
            m = spice.run("io_port_switch_ti_" + tag, ti_deck(**dict(kw, ios=ios)),
                          libs=("TPS61023_TRANS.lib",))
            m["ios_run"] = ios
            return m
        except SystemExit:
            if step == 4:
                raise


def transient_checks(c, lo, hi):
    s = start_up(lo)
    t_lim = s["tlim_off"] - s["tlim_on"]
    c.info("start-up", "EN into %.0f uF + %.0f uF, 100 mA, at the %.0f mA minimum limit: in limit %.2f ms, "
           "VBUS at %.2f V %.2f ms after EN" % (C_PORT[0] * 1e6, C_PORT[1] * 1e6, lo * 1e3, t_lim * 1e3,
                                                 d.USB_PORT_MIN, (s["tup"] - 0.1e-3) * 1e3))
    c.check("T1", "time in current limit at attach vs the shortest FAULT deglitch (5 ms): no false "
            "fault or latch-off", t_lim * 1e3, T_DEGLITCH[0] * 1e3, "<=", "ms", fmt="%.2f", need=0.25)
    for t_resp, tr_name in RESPONSES:
        for l_short, l_name in SHORTS:
            m = short(VBOOST_MAX, hi, t_resp, l_short, "short_%s_%s" % (tr_name, l_name))
            n = tr_name[0] + l_name[0]
            c.check("T2" + n, "%s response, %s short: 1 ms later the switch holds its limit (<= max %.0f mA)"
                    % (tr_name, l_name, hi * 1e3), m["iset"], hi * 1.001, "<=", "A")
            c.check("T3" + n, "%s response, %s short: latched off after the deglitch (<= 1 mA)"
                    % (tr_name, l_name), m["ioff"], 1e-3, "<=", "A")
    # T4-T6: TI's TPS61023 model; each excursion is moved up by the gap between
    # the model's regulated output and the pass-through maximum (VBOOST_MAX)
    cases = [("%s_%s_%s" % (tr_name, f_name, l_name),
              dict(corner="high", ios=hi, t_resp=t_resp, l_short=l_short, t_fall=t_fall))
             for t_resp, tr_name in RESPONSES for t_fall, f_name in FALLS for l_short, l_name in SHORTS]
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        res = list(pool.map(ti_short, cases))
    for n, ((tag, kw), m) in enumerate(zip(cases, res)):
        up = max(0.0, VBOOST_MAX - m["vbpre"])
        c.info("short (TI boost model) " + tag.replace("_", " "),
               "peak %.1f A; boost output %.3f -> %.3f V; U5 IN %.2f..%.2f V (+%.3f V to the pass-through "
               "maximum)%s" % (m["ipk"], m["vbpre"], m["vbmax"], m["vinmin"], m["vinmax"], up,
                                 "" if m["ios_run"] == hi else "; limit simulated %.0f mA (the model "
                                 "does not converge at %.0f mA)" % (1e3 * m["ios_run"], 1e3 * hi)))
        m["vbmax"] += up
        m["vinmax"] += up
    typ = [m for (tag, _), m in zip(cases, res) if tag.startswith("typ")]
    c.check("T4", "boost output (TPS61023 VOUT) maximum through a port short vs its %.1f V absolute max"
            % TPS61023_ABS, max(m["vbmax"] for m in res), TPS61023_ABS, "<=")
    c.check("T5", "U5 IN maximum through a port short vs its %.1f V absolute max" % VIN_ABS,
            max(m["vinmax"] for m in res), VIN_ABS, "<=", fix="more capacitance at U5 IN (C25)")
    c.check("T6", "U5 IN minimum through a port short, typical response, vs its %.1f V absolute min" % VIN_ABS_MIN,
            min(m["vinmin"] for m in typ), VIN_ABS_MIN, ">=", fix="U5 IN nearer C23/C24")
    c.info("T6 at the stress response", "U5 IN minimum %.2f V with a 10x slower response than TI's typical "
           "(not bounded by the datasheet); the model's UVLO (typical %.2f V) turns the switch off there" %
           (min(m["vinmin"] for m in res), UVLO_MIN))
    e = VBOOST_MAX * hi * (T_DEGLITCH[1] + T_RESP_STRESS)
    c.info("fault energy", "at most %.1f mJ in U5 from a short to the latch (%.2f W for <= %.0f ms); "
           "FAULT low %.0f..%.0f ms after the limit engages (sooner on thermal shutdown, which is not "
           "deglitched)" % (e * 1e3, VBOOST_MAX * hi, T_DEGLITCH[1] * 1e3, T_DEGLITCH[0] * 1e3,
                            T_DEGLITCH[1] * 1e3))


def main():
    c = Checks("IC-005: %s (%s) keyboard-port switch (hw/power/io_port_switch.py)" % (PART, LCSC))
    lo, hi = analytic_checks(c)
    transient_checks(c, lo, hi)
    return c.done()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""POW-004: USB-C attach inrush, against the SY6280's soft start and current
limit and the capacitance behind it.

    python3 hw/power/inrush.py

USB 2.0 (7.2.4.1) allows 10 uF directly across VBUS. More must sit behind
"VBUS surge current limiting", which here is the SY6280: its output ramps in
~120 us, and it holds the current at its limit while the 5V_SYS capacitance
charges. So the checks are:
  I1  capacitance ahead of the switch <= 10 uF
  I2  the surge through the switch is held to its limit (its max, +10 %)
  I3  5V_SYS is up (95 %) within 2 ms, so the start-up completes
  I4  VBUS at the receptacle stays above the SY6280's UVLO (+20 %) through
      the surge, so the switch doesn't restart itself
The charge drawn in excess of the final load current, and the capacitance it
equals at 5 V, are printed for reference: power.md's "10 uF effective" is met
by I1 and I2, not by that charge.

At attach: 5V_SYS capacitance (design.C_5VSYS, nominal values: the most
charge), the 3V3 buck starting (drawing its soft-start charge and the 3V3
load), the Wi-Fi card's TLV62569 starting the same way into its 22 uF and a booting
ESP32 (100 mA),
HDMI 5 V. The IO card's keyboard port stays off until its firmware turns it
on. The cable is its IR-drop resistance and 1 uH (ASSUME: ~1 m).
"""

import sys

import budget
import design as d
import spice
from spice import Checks

L_CABLE = 1e-6


def run(corner, rset):
    vbus = d.VBUS_MAX if corner == "high" else d.VBUS_MIN
    lo, nom, hi = d.sy6280_ilim(rset)
    ilim = hi if corner == "high" else lo
    c_main = sum(c for n, c in d.C_5VSYS if n != "Wi-Fi card C1")
    i_buck = (d.C_3V3_TOTAL * 3.3 / 0.8e-3 + budget.i_3v3()) * 3.3 / (d.BUCK_ETA_BUDGET * 5.0)
    i_wifi = ((d.WIFI_COUT + d.WIFI_COUT_HF) * 3.3 / 0.8e-3 + 0.100) * 3.3 / (d.BUCK_ETA_BUDGET * 5.0)
    deck = """
Vs src 0 PWL(0 0 1u {vbus})
Lc src a {lc}
Rc a rcpt {rc}
Cpre rcpt 0 {cpre}
Rf rcpt swin {rf}
Vm swin swm 0
X1 swm v5 0 SW_BEH params: RON={ron} ILIM={ilim} TON={ton} TDLY=5u
C5 v5 0 {c5}
* the 3V3 buck: soft-start charge + load, once 5V_SYS is past its UVLO
Bbuck v5 0 i = {ib} * min(1, max(0, (v(v5) - 2.45) / 2.5))
Rhdmi v5 0 {rh}
Rslot v5 card {rslot}
Cwin card 0 {cwin}
* the Wi-Fi card's buck: the same, into its 22 uF and a booting ESP32
Bwifi card 0 i = {iw} * min(1, max(0, (v(card) - 2.45) / 2.5))
.tran 100n 5m
.control
run
let ivbus = -i(vs)
meas tran ipk max i(vm) from=10u to=5m
meas tran ivpk max ivbus from=0 to=5m
meas tran ifinal find ivbus at=4.9m
wrdata {{name}}.dat v(v5)
meas tran vrcpt min v(rcpt) from=10u to=5m
meas tran q integ ivbus from=0 to=5m
let pw = (v(swin) - v(v5)) * ivbus
meas tran esw integ pw from=0 to=5m
.endc
""".format(vbus=vbus, lc=L_CABLE, rc=d.CABLE_R_VBUS + d.CABLE_R_GND + d.R_RECEPTACLE, cpre=d.C_VBUS_PRE,
           rf=d.FUSE_IN_R_MIN, ron=d.SY6280_RON_TYP, ilim=ilim, ton=d.SY6280_TON, c5=c_main, ib=i_buck,
           rh=5.0 / d.I_HDMI_5V, rslot=d.SLOT_PTC_R_MIN + d.R_SLOT_LINK + d.R_SLOT_SENSE + d.R_SLOT_CONTACTS,
           cwin=d.WIFI_CIN, iw=i_wifi)
    name = "pow004_%s_%d" % (corner, rset)
    m = spice.run(name, deck.replace("{name}", name))
    tt, v5 = spice.wave(name)
    m["t95"] = next(tt[k] for k in range(len(tt)) if v5[k] >= 0.95 * v5[-1])
    m["v5"] = v5[-1]
    m["q_excess"] = m["q"] - m["ifinal"] * 5e-3
    m.update(vbus=vbus, ilim=ilim, lo=lo, hi=hi)
    return m


def main():
    c = Checks("POW-004 USB-C inrush (hw/power/inrush.py)")
    c.check("I1", "capacitance on VBUS ahead of the SY6280 (USB 2.0: 10 uF)", 1e6 * d.C_VBUS_PRE, 10.0, "<=",
            "uF", fmt="%.1f")
    c_total = sum(c for _, c in d.C_5VSYS)
    rsets = [d.SY6280_MAIN_RSET]
    proposed = budget.proposed_rset(budget.chain("worst")["itot"])
    if proposed != d.SY6280_MAIN_RSET:
        rsets.append(proposed)
    for rset in rsets:
        tag = "RSET %.2fk" % (rset / 1e3) + ("" if rset == d.SY6280_MAIN_RSET else " (budget.py's proposal)")
        for corner in ("high", "low"):
            m = run(corner, rset)
            n = "%s/%s" % ("h" if corner == "high" else "l", "a" if rset == d.SY6280_MAIN_RSET else "b")
            c.info("%s, VBUS %.2f V" % (tag, m["vbus"]),
                   "limit %.2f A; %.0f uF behind the switch; charge above the final %.0f mA: %.0f uC "
                   "(= %.0f uF at 5 V); switch energy %.1f mJ; VBUS peak %.2f A (cable LC ringing "
                   "with the pre-switch capacitor included)" % (
                       m["ilim"], 1e6 * c_total, 1e3 * m["ifinal"], 1e6 * m["q_excess"],
                       1e6 * m["q_excess"] / 5.0, 1e3 * m["esw"], m["ivpk"]))
            c.check("I2" + n, "%s VBUS %.2f V: surge through the switch vs its limit max + 10%%" % (
                tag, m["vbus"]), m["ipk"], m["hi"] * 1.1, "<=", "A")
            c.check("I3" + n, "%s VBUS %.2f V: 5V_SYS at 95%% of its final %.2f V" % (tag, m["vbus"], m["v5"]), 1e3 * m["t95"], 2.0,
                    "<=", "ms", fmt="%.2f")
            c.check("I4" + n, "%s VBUS %.2f V: receptacle minimum vs SY6280 UVLO + 20%%" % (tag, m["vbus"]),
                    m["vrcpt"], d.SY6280_UVLO * 1.2, ">=")
    return c.done()


if __name__ == "__main__":
    sys.exit(main())

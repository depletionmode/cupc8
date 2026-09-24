#!/usr/bin/env python3
"""POW-004: USB-C attach inrush, against the input eFuse's (TPS25947) dVdt
soft start and current limit and the capacitance behind it.

    python3 hw/power/inrush.py

USB 2.0 (7.2.4.1) allows 10 uF directly across VBUS. More must sit behind
"VBUS surge current limiting", which here is the eFuse: its output rises at
the slew rate its dVdt capacitor sets (design.insw_ramp), so the 5V_SYS
capacitance charges at C x SR, well under its current limit. The checks:
  I1  capacitance ahead of the eFuse <= 10 uF
  I2  the surge through the eFuse stays under its minimum limit, so the
      soft start, not the limit, sets it (no limit cycling at attach)
  I3  5V_SYS is up (95 %) within 10 ms at the slowest slew rate
  I4  VBUS at the receptacle stays above the eFuse's UVLO (+20 %)

Two corners: vSafe5V max with the fastest slew rate (the dVdt pin current at
its max) and the eFuse's highest limit; vSafe5V min with the slowest slew rate
and the lowest limit. At attach: 5V_SYS capacitance (design.C_5VSYS, nominal
values: the most charge), the 3V3 buck starting (drawing its soft-start
charge and the 3V3 load), the Wi-Fi card's TLV62569 starting the same way
into its 22 uF and a booting ESP32 (100 mA), HDMI 5 V. The IO card's
keyboard port stays off until its firmware turns it on. The cable is its
IR-drop resistance and 1 uH (ASSUME: ~1 m).
"""

import sys

import budget
import design as d
import spice
from spice import Checks

L_CABLE = 1e-6


def run(corner):
    vbus = d.VBUS_MAX if corner == "high" else d.VBUS_MIN
    lo, nom, hi = d.insw_ilim()
    ilim = hi if corner == "high" else lo
    fast, typ, slow = d.insw_ramp(vbus)
    ton = fast if corner == "high" else slow
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
.tran 1u {tend}
.control
run
let ivbus = -i(vs)
meas tran ipk max i(vm) from=10u to={tend}
meas tran ivpk max ivbus from=0 to={tend}
meas tran ifinal find ivbus at={tfin}
wrdata {{name}}.dat v(v5)
meas tran vrcpt min v(rcpt) from=10u to={tend}
let pw = (v(swin) - v(v5)) * ivbus
meas tran esw integ pw from=0 to={tend}
.endc
""".format(vbus=vbus, lc=L_CABLE, rc=d.CABLE_R_VBUS + d.CABLE_R_GND + d.R_RECEPTACLE, cpre=d.C_VBUS_PRE,
           rf=d.FUSE_IN_R_MIN, ron=d.INSW_RON_TYP, ilim=ilim, ton=ton, tend="%g" % (ton + 3e-3),
           tfin="%g" % (ton + 2.9e-3), c5=c_main, ib=i_buck,
           rh=5.0 / d.I_HDMI_5V, rslot=d.SLOT_PTC_R_MIN + d.R_SLOT_LINK + d.R_SLOT_SENSE + d.R_SLOT_CONTACTS,
           cwin=d.WIFI_CIN, iw=i_wifi)
    name = "pow004_%s" % corner
    m = spice.run(name, deck.replace("{name}", name))
    tt, v5 = spice.wave(name)
    m["t95"] = next(tt[k] for k in range(len(tt)) if v5[k] >= 0.95 * v5[-1])
    m["v5"] = v5[-1]
    m.update(vbus=vbus, ilim=ilim, lo=lo, hi=hi, ton=ton)
    return m


def main():
    c = Checks("POW-004 USB-C inrush (hw/power/inrush.py)")
    c.check("I1", "capacitance on VBUS ahead of the eFuse (USB 2.0: 10 uF)", 1e6 * d.C_VBUS_PRE, 10.0, "<=",
            "uF", fmt="%.1f")
    c_total = sum(c for _, c in d.C_5VSYS)
    for corner in ("high", "low"):
        m = run(corner)
        n = corner[0]
        tag = "VBUS %.2f V, %s slew (%.1f ms to VBUS)" % (m["vbus"], "fastest" if n == "h" else "slowest",
                                                          1e3 * m["ton"])
        c.info(tag, "limit %.2f A; %.0f uF behind the eFuse charge at %.0f mA (C x SR), the rest of the "
               "surge is the loads starting (final %.0f mA); eFuse energy %.1f mJ; VBUS peak %.2f A (the "
               "cable ringing with the pre-switch capacitor, before the eFuse starts)" % (
                   m["ilim"], 1e6 * c_total, 1e3 * c_total * m["vbus"] / m["ton"], 1e3 * m["ifinal"],
                   1e3 * m["esw"], m["ivpk"]))
        c.check("I2" + n, "%s: surge through the eFuse vs its minimum limit %.2f A" % (tag, m["lo"]),
                m["ipk"], m["lo"], "<=", "A", need=0.10, fix="a larger dVdt capacitor (design.INSW_CDVDT)")
        c.check("I3" + n, "%s: 5V_SYS at 95%% of its final %.2f V" % (tag, m["v5"]), 1e3 * m["t95"], 10.0,
                "<=", "ms", fmt="%.2f", fix="a smaller dVdt capacitor")
        c.check("I4" + n, "%s: receptacle minimum vs eFuse UVLO + 20%%" % tag, m["vrcpt"], d.INSW_UVLO * 1.2, ">=")
    return c.done()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""RP2040 package heat at 40 C ambient on the RP2040 cards (GC/IC/SC/EC/YC-006).

    python3 hw/power/thermal.py rp2040 BOARD BUILD_DIR

The internal core regulator shares the RP2040 die, so its junction is the
package junction. It is bounded with everything else the package can
dissipate, from rated limits only (no typical figures):

  core regulator path  VREG_VIN max x the regulator's rated IMAX. This is
                       the LDO's loss plus all core power, so it holds at
                       any clock and any VSEL (the GPU card's 252 MHz at
                       1.20 V included). The LDO loss alone is reported.
  GPIO/QSPI drivers    all sourced current at IOVDD max (as if the whole
                       supply voltage dropped in the driver), plus all sunk
                       current at the absolute maximum pin voltage, at the
                       rated totals IIOVDD_MAX and IIOVSS_MAX
  USB PHY              worst-case device bias, both lines held against the
                       strongest pull-up, and both lines charging a
                       full-length full-speed cable at every bit
  ADC                  an assumed ADC_AVDD maximum (the datasheet has none)

Tj = 40 C + P x theta_JA must stay under both the project's 100 C and the
RP2040's 85 C case rating (Tc <= Tj). The IO term rests on the board
keeping within the rated IO totals. The steady currents are computed from
the netlist here (LED, pull and TMDS resistors); switching current into pad
and trace capacitance is not, because the datasheet gives no pad
capacitance. The GPU card's TMDS lines carry most of IIOVSS_MAX before
switching is counted, so that card fails until switching current is bounded
or measured.

RP2040 datasheet build 2025-02-20 (3184e62-clean), cited by table.
"""

import csv
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / 'tools'))

import design as d
from spice import Checks

VIN_MAX = 3.63            # Table 192 VVREG_VIN max; Table 622 IOVDD abs max
I_VREG_MAX = 0.100        # Table 192 IMAX ("can supply up to 100mA", 2.10)
I_VREG_LIMIT_MAX = 0.450  # Table 192 ILIMIT max (a fault, reported only)
VSEL_MIN = 0.80           # 2.10: output settable 0.80-1.30 V
VOUT_TOL = 0.03           # Table 192 output voltage variation
I_IOVDD_MAX = 0.050       # Table 625 IIOVDD_MAX, sum sourced by GPIO + QSPI
I_IOVSS_MAX = 0.050       # Table 625 IIOVSS_MAX, sum sunk by GPIO + QSPI
VPIN_MAX = VIN_MAX + 0.5  # Table 622 VPIN max IOVDD + 0.5
I_USB_VDD_MAX = 0.0020    # Table 637 max average USB_VDD, worst-case device
USB_RPU_MIN = 873.0       # Table 626 RPU2 min, the strongest bus pull-up
THETA_JA = 48.0           # Table 611 (5.1.1)
TC_MAX = 85.0             # Table 624 case temperature max
# USB 2.0 specification, chapter 7: full-speed cable one-way delay <= 26 ns,
# 90 ohm +-15 % differential impedance (45 ohm per line), 20 pF transceiver
# input capacitance at each end; 12 Mb/s NRZI is at most one edge per bit.
FS_CABLE_DELAY = 26e-9
FS_Z_LINE_MIN = 0.85 * 90 / 2
FS_C_TRANSCEIVER = 20e-12
FS_FULL_CYCLES = 6e6
ADC_AVDD_MAX = d.assume('RP2040 cards', 'RP2040 ADC_AVDD current <= 2 mA (the datasheet '
                        'gives no maximum; only +40 uA for the temperature sensor)', 2e-3)
R_TOL = 0.05              # chip resistors: the BOM's widest (RN1/RN2 C425067 +-5 %)
# LED forward voltage minimum by LCSC code, less 4 mV/K from 25 C to TC_MAX.
# KT-0603G (C12624) DS: VF 2.6 V min at IF = 5 mA; more current raises VF.
LED_VF_MIN = {'C12624': 2.6 - 0.004 * (TC_MAX - 25)}
LED_VF_I = 0.005
# DVI 1.0: TMDS sink AVcc 3.3 V +-5 %, termination RT 50 ohm +-10 %
TMDS_AVCC_MAX = 3.3 * 1.05
TMDS_RT_MIN = 50 * 0.9

RAILS = {'/3V3': VIN_MAX, '/+3V3': VIN_MAX, '/GND': 0.0,
         '/VBUS': d.VBUS_MAX, '/HPD_5V': d.VBUS_MAX}
SUPPLY_PINS = {'1', '10', '22', '33', '42', '43', '44', '45', '48', '49', '23', '50', '57',
               '19', '20', '21', '46', '47', '26'}  # supplies, TESTEN, XIN/XOUT, USB, RUN


def vreg_path_w():
    return VIN_MAX * I_VREG_MAX


def ldo_loss_w(vin=VIN_MAX, vsel=VSEL_MIN, i=I_VREG_MAX):
    return (vin - vsel * (1 - VOUT_TOL)) * i


def usb_w():
    c_line = FS_CABLE_DELAY / FS_Z_LINE_MIN + 2 * FS_C_TRANSCEIVER
    dynamic = 2 * c_line * VIN_MAX ** 2 * FS_FULL_CYCLES
    held = 2 * VIN_MAX * VIN_MAX / USB_RPU_MIN
    return VIN_MAX * I_USB_VDD_MAX + held + dynamic


def io_w():
    return VIN_MAX * I_IOVDD_MAX + VPIN_MAX * I_IOVSS_MAX


def package_w():
    return vreg_path_w() + io_w() + usb_w() + VIN_MAX * ADC_AVDD_MAX


def tj(p):
    return d.AMBIENT_C + p * THETA_JA


def ohms(value):
    text = value.upper().replace('Ω', '').replace('OHM', '').rstrip('R')
    scale = 1.0
    for suffix, factor in (('K', 1e3), ('M', 1e6)):
        if suffix in text:
            text, scale = text.replace(suffix, '.'), factor
    return float(text.rstrip('.')) * scale


def bom_codes(path):
    codes = {}
    with open(path) as source:
        for row in csv.DictReader(source):
            for ref in row['Designator'].split(','):
                codes[ref.strip()] = row['LCSC Part #']
    return codes


def static_io(circuit, codes):
    """Worst steady GPIO/QSPI source and sink currents, from each resistor on
    an RP2040 signal net. Returns (source A, sink A, lines, unmodelled)."""
    source = sink = 0.0
    lines, unknown, pairs = [], [], {}
    for (ref, pin), net in sorted(circuit.pins.items()):
        if ref != 'U1' or pin in SUPPLY_PINS or net.startswith('unconnected'):
            continue
        for res in circuit.resistors:
            if net not in res.ends:
                continue
            far = res.ends[1] if res.ends[0] == net else res.ends[0]
            rmin = ohms(res.value) * (1 - R_TOL)
            members = circuit.nets.get(far, ())
            leds = [r for r, p in members if p == '2' and
                    circuit.components[r][1] == ('Device', 'LED')]
            if far in RAILS:
                v = RAILS[far]
                if v:
                    sink += v / rmin
                    lines.append((res.ref, far, 'sink', v / rmin))
                else:
                    source += VIN_MAX / rmin
                    lines.append((res.ref, far, 'source', VIN_MAX / rmin))
            elif leds:
                vf = min(LED_VF_MIN.get(codes.get(r), 0.0) for r in leds)
                i = max(LED_VF_I, (VIN_MAX - vf) / rmin)
                source += i
                lines.append((res.ref, far, 'LED source', i))
            elif far.startswith('/HD_') and far[-1] in 'PN':
                # a TMDS pair drives P and N complementary: one line sinks
                i = TMDS_AVCC_MAX / (rmin + TMDS_RT_MIN)
                pairs[far[:-1]] = max(pairs.get(far[:-1], 0.0), i)
                lines.append((res.ref, far, 'TMDS sink (one per pair)', i))
            elif ohms(res.value) >= 1e3:
                # a weak resistor to an unmodelled node: rail at either end
                source += VIN_MAX / rmin
                sink += VIN_MAX / rmin
                lines.append((res.ref, far, 'source+sink', VIN_MAX / rmin))
            else:
                unknown.append((res.ref, far))
    return source, sink + sum(pairs.values()), lines, unknown


def tmds_lines(circuit):
    return sorted(net for (ref, pin), net in circuit.pins.items()
                  if ref == 'U1' and net.startswith('/TMDS_'))


def check_board(board, out):
    from cosim.netlist import read
    import boardevidence
    import thermal_bind

    out = Path(out)
    boardevidence.validate(board, out)
    refs, pins = thermal_bind.bind(board, out)
    circuit = read(out / f'{board}.net')
    codes = bom_codes(out / 'fab/bom.csv')
    c = Checks('RP2040 package heat, %s card, at %.0f C ambient (hw/power/rp2040_thermal.py)' %
               (board, d.AMBIENT_C))
    c.info('binding', '%d PCB references and %d model pins match (U1 RP2040 QFN-56, VREG_VIN '
           'and IOVDD on the 3V3 rail, VREG_VOUT only to DVDD and its decouplers)' % (refs, pins))
    rail_max = d.buck_vout_range()[1]
    c.check('R1', 'card 3V3 (the main buck, the only source on the slot) max vs VREG_VIN/IOVDD max',
            rail_max, VIN_MAX, '<=', 'V')
    c.info('LDO loss', '(%.2f V - %.3f V) x %.0f mA = %.0f mW at the lowest VSEL; at the '
           'default 1.10 V from %.3f V: %.0f mW' % (
               VIN_MAX, VSEL_MIN * (1 - VOUT_TOL), 1e3 * I_VREG_MAX, 1e3 * ldo_loss_w(),
               rail_max, 1e3 * ldo_loss_w(rail_max, 1.10)))
    c.info('fault', 'at the ILIMIT maximum %.0f mA (VREG overloaded, out of rating) the '
           'regulator path is %.0f mW' % (1e3 * I_VREG_LIMIT_MAX, 1e3 * VIN_MAX * I_VREG_LIMIT_MAX))
    source, sink, lines, unknown = static_io(circuit, codes)
    for ref, far, kind, i in lines:
        c.info(ref, '%s to %s: <= %.2f mA' % (kind, far, 1e3 * i))
    for ref, far in unknown:
        c.info(ref, 'series resistor to logic net %s: no steady current modelled' % far)
    c.check('R2', 'steady GPIO/QSPI source current vs IIOVDD_MAX', 1e3 * source,
            1e3 * I_IOVDD_MAX, '<=', 'mA', fmt='%.1f')
    c.check('R3', 'steady GPIO/QSPI sink current vs IIOVSS_MAX', 1e3 * sink,
            1e3 * I_IOVSS_MAX, '<=', 'mA', fmt='%.1f')
    c.info('premise', 'the GPIO/QSPI heat term uses the rated totals; switching current '
           'into pad, trace and load capacitance must fit the remaining %.1f mA source / '
           '%.1f mA sink headroom (not computed: no RP2040 pad capacitance in the datasheet)' % (
               1e3 * (I_IOVDD_MAX - source), 1e3 * (I_IOVSS_MAX - sink)))
    tmds = tmds_lines(circuit)
    if tmds:
        # 252 Mb/s edges into pad, trace and RN pad capacitance: the RP2040
        # datasheet gives no pad capacitance, so the switching current is open
        c.check('R4', '%d TMDS lines: switching current at 252 Mb/s bounded within the '
                'IIOVDD/IIOVSS headroom' % len(tmds), 0, 1, '>=', '', fmt='%d')
    p = package_w()
    c.info('package heat', 'VREG path %.0f + GPIO/QSPI %.0f + USB %.0f + ADC %.0f = %.0f mW' % (
        1e3 * vreg_path_w(), 1e3 * io_w(), 1e3 * usb_w(), 1e3 * VIN_MAX * ADC_AVDD_MAX, 1e3 * p))
    c.check('R5', 'RP2040 junction, %.0f mW x %.0f C/W (Table 611)' % (1e3 * p, THETA_JA),
            tj(p), min(d.TJ_LIMIT_C, TC_MAX), '<=', 'C', fmt='%.1f')
    return c.done()


def main(argv):
    if len(argv) != 2:
        print('usage: thermal.py rp2040 BOARD BUILD_DIR', file=sys.stderr)
        return 2
    try:
        return check_board(*argv)
    except (OSError, ValueError, KeyError) as error:
        print('FAIL %s RP2040 thermal: %s' % (argv[0], error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

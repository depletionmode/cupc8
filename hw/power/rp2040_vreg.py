#!/usr/bin/env python3
"""RP2040 core regulator (VREG -> DVDD) operating point on a routed card.

    python3 hw/power/rp2040_vreg.py CARD BOARD_BUILD

Binds the card's netlist (VREG_VIN, VREG_VOUT, both DVDD pins and their
capacitors) and its firmware's VREG/clock settings to the RP2040 data sheet
limits. Source: Raspberry Pi, "RP2040 Datasheet", build-date 2025-02-20,
build-version 3184e62-clean (datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf):

- 2.10.1: 1 uF close to VREG_VIN and to VREG_VOUT.
- Table 192: output voltage variation -3 % .. +3 % of the selected voltage;
  IMAX 100 mA; VREG_VIN 1.63 .. 3.63 V.
- Table 634: DVDD 1.05 .. 1.16 V; short-term transients within +/-100 mV;
  "If using 200MHz for clk_sys ... set DVDD to 1.15V".
- Overview: up to 133 MHz, or 200 MHz at 1.15 V (2.15.3).

This is the DC operating point only. The data sheet publishes no load-step
response, output impedance or loop bandwidth for the regulator and no
maximum DVDD current at the card's clock and workload, so a droop bound
cannot be derived from it; boardcheck keeps that gap red.
"""
import re
import sys
from pathlib import Path

import design as d
from spice import Checks

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from cosim.netlist import read  # noqa: E402

VREG_VAR = 0.03                 # Table 192
DVDD_MIN, DVDD_MAX = 1.05, 1.16  # Table 634
VIN_MAX = 3.63                  # Table 192
CLK_MAX_KHZ = {None: 133000, 1.15: 200000}   # overview; 200 MHz only at 1.15 V
DEFAULT_VSEL = 1.10             # 2.10.3: 1.1 V at power-on/reset
DEFAULT_CLK_KHZ = 125000        # pico-sdk SYS_CLK_KHZ default
# PicoDVI timings the firmware may name: 640x480p60 is a 25.2 MHz pixel
# clock x 10 bits (CEA-861 / PicoDVI dvi_timing.c)
DVI_BIT_CLK_KHZ = {'dvi_timing_640x480p_60hz': 252000}

CARDS = {'gpu': ('gpu', '/3V3'), 'io': ('io', '/3V3'), 'storage': ('storage', '/3V3'),
         'eink': ('eink', '/3V3'), 'system': ('sysctl', '/+3V3')}
VREG_VIN, VREG_VOUT, DVDD = '44', '45', ('23', '50')


def farads(value):
    m = re.fullmatch(r'([0-9.]+)([pnu])', value)
    if not m:
        raise ValueError('capacitor value %r not understood' % value)
    return float(m.group(1)) * {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}[m.group(2)]


def caps_on(circuit, net):
    """Nameplate capacitance from `net` straight to /GND."""
    total = 0.0
    for (ref, pin), got in circuit.pins.items():
        if got != net or not ref.startswith('C'):
            continue
        other = circuit.net(ref, '2' if pin == '1' else '1')
        value, lib = circuit.components[ref]
        if other == '/GND' and lib == ('Device', 'C'):
            total += farads(value)
    return total


def topology(path, rail):
    circuit = read(path)
    mcus = [r for r, v in circuit.components.items() if v[0] == 'RP2040']
    if mcus != ['U1']:
        raise ValueError('expected one RP2040 as U1, got %s' % mcus)
    if circuit.net('U1', VREG_VIN) != rail:
        raise ValueError('VREG_VIN (U1.44) is on %s, not %s' % (circuit.net('U1', VREG_VIN), rail))
    core = circuit.net('U1', VREG_VOUT)
    if not core or core == rail or any(circuit.net('U1', p) != core for p in DVDD):
        raise ValueError('VREG_VOUT (U1.45) does not feed both DVDD pins (U1.23/U1.50)')
    # capacitors are counted below; a test point is a bare pad, not a load
    loads = {pin for pin, net in circuit.pins.items()
             if net == core and not pin[0].startswith(('C', 'TP'))}
    if loads != {('U1', VREG_VOUT), *(('U1', p) for p in DVDD)}:
        raise ValueError('core rail %s has loads besides RP2040 DVDD: %s' % (core, sorted(loads)))
    return caps_on(circuit, rail), caps_on(circuit, core)


def firmware(directory):
    """(selected VREG voltage, clk_sys kHz) from the card's main.c."""
    text = (ROOT / 'fw/rp2040' / directory / 'main.c').read_text()
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    vsel = [m.groups() for m in re.finditer(r'vreg_set_voltage\(\s*VREG_VOLTAGE_(\d)_(\d\d)\s*\)', text)]
    if len(vsel) > 1 or (not vsel and 'vreg_set_voltage' in text):
        raise ValueError('%s: VREG setting not a single literal' % directory)
    volts = float('%s.%s' % vsel[0]) if vsel else DEFAULT_VSEL
    clocks = re.findall(r'set_sys_clock_khz\(\s*([^,]+),', text)
    if 'clock_configure' in text or 'set_sys_clock_pll' in text or len(clocks) > 1:
        raise ValueError('%s: clk_sys set in a way this check does not parse' % directory)
    if not clocks:
        return volts, DEFAULT_CLK_KHZ
    expr = clocks[0].strip()
    if expr.isdigit():
        return volts, int(expr)
    m = re.fullmatch(r'DVI_TIMING\.bit_clk_khz', expr)
    timing = re.search(r'#define\s+DVI_TIMING\s+(\w+)', text)
    if not m or not timing or timing.group(1) not in DVI_BIT_CLK_KHZ:
        raise ValueError('%s: clk_sys %r not understood' % (directory, expr))
    return volts, DVI_BIT_CLK_KHZ[timing.group(1)]


def check(card, out, c):
    directory, rail = CARDS[card]
    c_in, c_out = topology(Path(out) / (card + '.net'), rail)
    vsel, khz = firmware(directory)
    c.info('binding', '%s.net: VREG_VIN on %s with %.2f uF nameplate to GND; VREG_VOUT -> DVDD '
           'with %.2f uF; firmware fw/rp2040/%s: VSEL %.2f V, clk_sys %.0f MHz'
           % (card, rail, 1e6 * c_in, 1e6 * c_out, directory, vsel, khz / 1e3))
    c.check('V0', 'VREG_VOUT nameplate capacitance vs the 1 uF of DS 2.10.1', 1e6 * c_out, 1.0,
            '>=', 'uF', fmt='%.2f')
    c.check('V1', 'VREG_VIN rail: total nameplate capacitance (placement not checked) vs the 1 uF of DS 2.10.1', 1e6 * c_in, 1.0,
            '>=', 'uF', fmt='%.2f')
    c.check('V2', 'VREG_VIN: 3V3 maximum POW-001 holds the rail to (no socket drop) vs 3.63 V max',
            d.V3V3_MAX, VIN_MAX, '<=')
    c.check('V3', 'DVDD high: VSEL %.2f V + 3 %% vs DVDD max 1.16 V' % vsel,
            vsel * (1 + VREG_VAR), DVDD_MAX, '<=',
            fix='the data sheet documents no DVDD above 1.16 V (1.15 V nominal for 200 MHz)')
    c.check('V4', 'DVDD low: VSEL %.2f V - 3 %% vs DVDD min 1.05 V' % vsel,
            vsel * (1 - VREG_VAR), DVDD_MIN, '>=')
    limit = CLK_MAX_KHZ.get(vsel if vsel == 1.15 else None)
    c.check('V5', 'clk_sys vs the data sheet maximum at VSEL %.2f V' % vsel, khz / 1e3, limit / 1e3,
            '<=', 'MHz', fmt='%.0f',
            fix='133 MHz, or 200 MHz at VSEL 1.15 V, are the only documented operating points')


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in CARDS:
        sys.exit(__doc__)
    c = Checks('RP2040 VREG/DVDD operating point, %s card (hw/power/rp2040_vreg.py)' % sys.argv[1])
    check(sys.argv[1], sys.argv[2], c)
    return c.done()


if __name__ == '__main__':
    sys.exit(main())

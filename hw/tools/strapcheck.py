#!/usr/bin/env python3
"""Verify the Wi-Fi card ESP32-C3 reset and boot straps from its netlist.

Espressif ESP32-C3 datasheet v2.4, Tables 3-2/3-3 and 5-4:
https://documentation.espressif.com/esp32-c3_datasheet_en.html
The manufacturer recommends a 10 kOhm / 1 uF CHIP_EN RC circuit:
https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c3/schematic-checklist.html
"""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cosim.netlist import read


VDD = 3.3
VIH = 0.75 * VDD
VIL = 0.25 * VDD
HOLD_MS = 3.0
RELEASE_MS = 1.0


def quantity(value, suffix):
    match = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)' + suffix, value)
    if not match:
        raise ValueError('unsupported component value: ' + value)
    return float(match.group(1))


def topology(c):
    """Return netlist values only after checking all sampled pad connections."""
    expected = {
        'R1': ('/3V3', '/EN', '10k'),
        'R2': ('/3V3', '/BOOT', '10k'),
        'R3': ('/3V3', '/STRAP8', '10k'),
        'R4': ('/3V3', '/STRAP2', '10k'),
        'C5': ('/EN', '/GND', '1u'),
    }
    for ref, (high, low, value) in expected.items():
        actual = (c.net(ref, '1'), c.net(ref, '2'))
        if actual != (high, low) or c.components.get(ref, (None,))[0] != value:
            raise ValueError(f'{ref} expected {value} between {high} and {low}; got {actual}')
        source = c.components[ref][1]
        if source != ('Device', 'C' if ref == 'C5' else 'R'):
            raise ValueError(f'{ref} has wrong component type {source}')
    expected_pins = {
        ('U1', '3'): '/3V3', ('U1', '8'): '/EN',
        ('U1', '5'): '/STRAP2', ('U1', '22'): '/STRAP8',
        ('U1', '23'): '/BOOT', ('J1', 'B9'): '/EN',
        ('J1', 'A18'): '/BOOT',
    }
    for pin, net in expected_pins.items():
        if c.net(*pin) != net:
            raise ValueError(f'{pin} expected on {net}; got {c.net(*pin)}')
    allowed = {
        '/EN': {('R1', '2'), ('C5', '1'), ('U1', '8'), ('J1', 'B9')},
        '/BOOT': {('R2', '2'), ('U1', '23'), ('J1', 'A18')},
        '/STRAP8': {('R3', '2'), ('U1', '22')},
        '/STRAP2': {('R4', '2'), ('U1', '5')},
    }
    for net, nodes in allowed.items():
        if set(c.nets.get(net, ())) != nodes:
            raise ValueError(f'{net} contains an unexpected or missing connection')
    return quantity(c.components['R1'][0], 'k') * 1e3, quantity(c.components['C5'][0], 'u') * 1e-6


def simulate(r_ohm, c_farad, download):
    """Release open-drain reset at 1 ms and retain PROG_n through tH."""
    with tempfile.TemporaryDirectory(prefix='cupc8-strap-') as directory:
        directory = Path(directory)
        deck = directory / 'strap.cir'
        data = directory / 'wave.dat'
        # SRESET represents CARD_RST_n's open-drain pull-down. SBOOT is
        # PROG_n; in download mode it stays low past the 3 ms sample hold.
        control = ('PWL(0 1 30m 1 30.001m 0)' if download else 'DC 0')
        deck.write_text(f'''ESP32-C3 Wi-Fi card reset and straps
VDD vdd 0 {VDD}
R1 vdd en {r_ohm}
C5 en 0 {c_farad} ic=0
VRESET reset 0 PWL(0 1 {RELEASE_MS}m 1 {RELEASE_MS + 0.001}m 0)
SRESET en 0 reset 0 SWOD
R2 vdd boot 10k
R3 vdd strap8 10k
R4 vdd strap2 10k
VPROG prog 0 {control}
SBOOT boot 0 prog 0 SWOD
.model SWOD SW(Ron=1 Roff=1e12 Vt=0.5 Vh=0)
.tran 10u 35m uic
.control
set wr_singlescale
tran 10u 35m uic
wrdata {data} v(en) v(boot) v(strap8) v(strap2)
quit
.endc
.end
''')
        result = subprocess.run(['ngspice', '-b', str(deck)], capture_output=True, text=True)
        if result.returncode or not data.is_file():
            raise ValueError('ngspice failed: ' + (result.stderr or result.stdout)[-800:])
        rows = []
        for line in data.read_text().splitlines():
            values = [float(v) for v in line.split()]
            if len(values) == 5:
                rows.append(values)
        if not rows:
            raise ValueError('ngspice produced no samples')
        crossing = next((row[0] for row in rows if row[0] > RELEASE_MS / 1000 and row[1] >= VIH), None)
        if crossing is None or crossing <= RELEASE_MS / 1000:
            raise ValueError('EN never released high')
        sample = next((row for row in rows if row[0] >= crossing + HOLD_MS / 1000), None)
        if sample is None:
            raise ValueError('strap hold interval not simulated')
        _, en, boot, strap8, strap2 = sample
        if en < VIH or strap8 < VIH or strap2 < VIH:
            raise ValueError(f'EN/GPIO8/GPIO2 not high after reset: {sample}')
        if download and boot > VIL:
            raise ValueError(f'GPIO9 not low in download mode: {boot:.3f} V')
        if not download and boot < VIH:
            raise ValueError(f'GPIO9 not high in SPI boot mode: {boot:.3f} V')
        return crossing, sample


def check(path):
    r_ohm, c_farad = topology(read(path))
    normal_t, normal = simulate(r_ohm, c_farad, False)
    download_t, download = simulate(r_ohm, c_farad, True)
    print('PASS WC-006 %s sha256=%s' % (path, hashlib.sha256(path.read_bytes()).hexdigest()))
    print('  normal: EN high at %.3f ms, sample GPIO9/8/2 = %.3f/%.3f/%.3f V' %
          (normal_t * 1000, normal[2], normal[3], normal[4]))
    print('  download: EN high at %.3f ms, sample GPIO9/8/2 = %.3f/%.3f/%.3f V' %
          (download_t * 1000, download[2], download[3], download[4]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist', type=Path)
    args = parser.parse_args()
    try:
        check(args.netlist)
    except (ValueError, OSError, KeyError) as error:
        print('FAIL WC-006: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

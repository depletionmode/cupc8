#!/usr/bin/env python3
"""BUS-005B: routed main-board SRAM/ROM timing at 12 MHz.

The chipset drives address, data and CE at edge n; /WE falls at n+1 and
rises at n+2. Reads are sampled at n+2. The RTL then holds writes for m_3
and inserts m_gap before another transaction (soc/chipset.vhd).

Datasheet maxima/minima:
  ISSI IS62WV5128EBLL-45HLI, rev A4, AC table p8:
    https://www.issi.com/WW/pdf/62-65WV5128EALL-BLL.pdf
  Microchip SST39VF040-70, DS20005023E, tables 7-1/7-2 p10:
    https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/SST39LF010-SST39LF020-SST39LF040-SST39VF010-SST39VF020-SST39VF040-Data-Sheet-DS20005023.pdf
"""
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/timing'))
from extract_lengths import copper_lengths  # noqa: E402
from cpubus_budget import io_delays, ALLOW, PERIOD, PS_PER_MM  # noqa: E402

MEMORY = {
    # tAA/tCE, tOE, tWP, tDS, tAH, tWPH; all ns over operating range.
    'SRAM': {'access': 45, 'oe': 20, 'we_low': 35, 'data_setup': 20,
             'addr_hold': 0, 'addr_setup': 35, 'ce_setup': 35,
             'we_high': 0, 'hz': 15, 'cycle': 45},
    'ROM': {'access': 70, 'oe': 35, 'we_low': 40, 'data_setup': 40,
            'addr_hold': 30, 'addr_setup': 0, 'ce_setup': 0,
            'we_high': 30, 'hz': 25, 'cycle': 70},
}
MARGIN = 0.20


def routed_lengths(path):
    got = copper_lengths(path)
    names = ([f'MEM_A{i}' for i in range(19)] + [f'MEM_D{i}' for i in range(8)] +
             ['MEM_nOE', 'MEM_nWE', 'MEM_nCE_RAM', 'MEM_nCE_ROM'])
    absent = [name for name in names if not isinstance(got.get(name), (int, float)) or got[name] <= 0]
    if absent:
        raise ValueError('missing routed memory nets: ' + ', '.join(absent))
    return got


def margins(lengths, io):
    """Return every limiting external-memory timing margin as (name, margin)."""
    launch_in, launch_out = io
    address_ns = max(lengths[f'MEM_A{i}'] for i in range(19)) * PS_PER_MM / 1000
    data_ns = max(lengths[f'MEM_D{i}'] for i in range(8)) * PS_PER_MM / 1000
    oe_ns = lengths['MEM_nOE'] * PS_PER_MM / 1000
    we_ns = lengths['MEM_nWE'] * PS_PER_MM / 1000
    common = ALLOW['clk_insertion'] + launch_out + ALLOW['out_pad']
    capture = ALLOW['in_pad'] + launch_in + ALLOW['setup'] + ALLOW['clk_mismatch']
    result = []
    for memory, t in MEMORY.items():
        ce = lengths['MEM_nCE_RAM' if memory == 'SRAM' else 'MEM_nCE_ROM'] * PS_PER_MM / 1000
        ready = max(address_ns + t['access'], ce + t['access'], oe_ns + t['oe'])
        arrival = common + ready + data_ns + capture
        result.append((memory + ' read setup (two clocks)', 1 - arrival / (2 * PERIOD)))
        # The m_1 state gives a full clock of /WE low. Pessimistically charge
        # both edges the pad/trace variation, even though both use one pin.
        edge_uncertainty = ALLOW['clk_mismatch'] + ALLOW['out_pad'] + we_ns
        pulse = PERIOD - 2 * edge_uncertainty
        result.append((memory + ' /WE low', 1 - t['we_low'] / pulse))
        if memory == 'ROM':
            # m_3 + m_gap keep the address and /WE high before a new request.
            high = 2 * PERIOD - 2 * edge_uncertainty
            result.append((memory + ' /WE high', 1 - t['we_high'] / high))
            hold = 2 * PERIOD - common - address_ns - edge_uncertainty
            result.append((memory + ' address hold', 1 - t['addr_hold'] / hold))
        # Address, CE and data launched at edge n, /WE ends at n+2.
        address_setup = 2 * PERIOD - common - address_ns - edge_uncertainty
        ce_setup = 2 * PERIOD - common - ce - edge_uncertainty
        if t['addr_setup']:
            result.append((memory + ' address setup to write end', 1 - t['addr_setup'] / address_setup))
        if t['ce_setup']:
            result.append((memory + ' CE setup to write end', 1 - t['ce_setup'] / ce_setup))
        available = 2 * PERIOD - common - max(data_ns, address_ns) - edge_uncertainty
        result.append((memory + ' data setup to write end', 1 - t['data_setup'] / available))
        result.append((memory + ' cycle time', 1 - t['cycle'] / (4 * PERIOD)))
        # The explicit m_gap prevents the next selected memory driving D
        # until at least one complete clock after this chip is deselected.
        turnover = PERIOD - 2 * (ALLOW['out_pad'] + max(ce, data_ns))
        result.append((memory + ' bus release', 1 - t['hz'] / turnover))
    return result


def main():
    path = ROOT / 'build/hw/main/main.kicad_pcb'
    sys.path.insert(0, str(ROOT / 'hw/tools'))
    import boardevidence
    import boardcheck
    out = path.parent
    boardevidence.validate('main', out)
    boardcheck.check_report(__import__('json').loads((out / 'drc.json').read_text()), 'drc')
    lengths = routed_lengths(path)
    timing = margins(lengths, io_delays('chipset'))
    bad = 0
    for name, margin in timing:
        ok = math.isfinite(margin) and margin >= MARGIN
        print('%-42s %6.1f%% %s' % (name, margin * 100, 'ok' if ok else 'FAIL'))
        bad += not ok
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

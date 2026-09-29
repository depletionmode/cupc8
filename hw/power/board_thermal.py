#!/usr/bin/env python3
"""Main board and CPU card thermal rows (MB-006, CC-006) beyond THM-001.

    python3 hw/power/thermal.py board main build/hw/main
    python3 hw/power/thermal.py board cpu build/hw/cpu

Each board's 1V2 rail is an RT9013-12 (SOT-23-5, 250 C/W) feeding an
iCE40HX4K-TQ144 and a few resistor branches. The main board also has the
HT7533-2 standby LDO on VBUS_F (3V3_STBY). At 40 C ambient, Tj <= 100 C:

  RT9013   Tj = 40 + [(3V3 max - 1V2 min) x I_1V2 + 3V3 max x IQ] x 250.
           The largest I_1V2 that holds is the ceiling. The iCE40's share of
           I_1V2 needs a maximum operating core current. Lattice publishes
           none: DS1040 gives the static ICC as a 25 C typical only, and
           leaves design-dependent power to its Power Calculator (iCEcube2),
           whose coefficients are not published. The one guaranteed core
           maximum is the power-up peak (ICCPEAK + ICCPLLPEAK). So the
           operating row stays red until a worst-corner Power Calculator
           report or a measurement supplies ICE40_CORE_MAX.
  HT7533   Tj = 40 + [(VIN - VOUT min) x I_load + VIN x I_gnd] x 500, at the
           part's rated 24 V input (covers VBUS_F whatever the source does
           below the rating; the eFuse's OVLO does not limit VBUS_F). Every
           part on 3V3_STBY must be modelled; a new one fails the row.

Sources:
  Lattice DS1040 iCE40 LP/HX Family Data Sheet, Version 3.2, October 2015:
    Static Supply Current - HX Devices (ICC HX4K 1140 uA typ, TJ = 25 C,
    blank pattern, f = 0), Peak Startup Supply Current - HX Devices
    (ICCPEAK HX4K 22.3 mA max, ICCPLLPEAK HX4K 6.4 mA max), Recommended
    Operating Conditions (VCC 1.14-1.26 V, tJIND <= 100 C).
  Holtek HT75xx-2 datasheet Rev. 1.30 (December 14, 2012; hw/parts/C82217
    cites the same revision): Thermal Information theta_JA SOT23-5 500 C/W
    max (no airflow, no heat sink); VIN <= 24 V; ISS 5.0 uA max (no load,
    Ta = 25 C); VOUT tolerance +-1 % at 10 mA (design.py's +-2 % kept).
"""

from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / 'tools'))

import design as d
from spice import Checks

ROOT = HERE.parents[1]

# ---------------------------------------------------------------- iCE40 (DS1040 v3.2)
ICE40_PART = 'ICE40HX4K-TQ144'
ICE40_VCC_PINS = ('27', '40', '92', '111')
ICE40_ICC_STATIC_TYP = 1.140e-3     # typical only (25 C, blank, 0 MHz): not a bound
ICE40_ICCPEAK_MAX = 22.3e-3         # power-up, core
ICE40_ICCPLLPEAK_MAX = 6.4e-3       # power-up, PLL supplies (VCCPLL0/1 are fed from 1V2)
ICE40_CORE_MAX = None               # max operating core current: not published (see above)
FPGA_BUILD = {'main': 'chipset', 'cpu': 'cpucard'}
ICESTORM = Path('/opt/oss-cad-suite/bin')
R_TOL = 0.05                        # widest chip-resistor tolerance on these boards

# per board: the iCE40, its 1V2 net, and the LDO that feeds it (through a 0 ohm link on main)
RAIL_1V2 = {'main': ('U7', '/+1V2', 'U4', '/1V2_LDO'),
            'cpu': ('U1', '/1V2', 'U3', '/1V2')}

# ---------------------------------------------------------------- HT7533-2 (Holtek Rev 1.30)
HT_THETA_JA = 500.0
HT_VIN_MAX = d.STBY_LDO_VIN_MAX     # 24 V
HT_ISS_MAX = 5.0e-6                 # 25 C, no load
HT_IGND_MAX = d.assume('main', 'HT7533-2 ground current <= 20 uA over load and temperature '
                       '(DS: ISS 5 uA max at 25 C, no load; no loaded or hot figure)', 20e-6)
MAX16054_RPU_MIN = d.assume('main', 'MAX16054 IN pull-up >= 31.5 kOhm (DS: 63 kOhm typ only), '
                            'button held', d.ONOFF_PULLUP / 2)
EN_LEAK_MAX = d.assume('main', 'TPS25947 EN/UVLO input current <= 10 uA', 10e-6)
CAP_LEAK_MAX = d.assume('main', 'MLCC leakage <= 1 uA per capacitor on 3V3_STBY', 1e-6)
STBY_NET = '/3V3_STBY'
LINK_MAX = 0.002                    # the 1V2 link: a 0 ohm jumper, or the MB-051 1 mOhm shunt
# SN74LVC07A (TI SCAS595, 6.5 Electrical Characteristics, VCC 2.7-3.6 V): ICC <= 10 uA with
# inputs at a rail, plus dICC <= 500 uA per input 0.6 V below VCC. Its inputs are nPOR (U6,
# from +3V3), which may sit below 3V3_STBY: every input is charged its dICC.
LVC07_ICC_MAX, LVC07_DICC_MAX = 10e-6, 500e-6


def ohms(value):
    text = value.split()[0]                 # "7.5k 0.1%": the tolerance is not part of the value
    if text.endswith('m'):
        return float(text[:-1]) * 1e-3      # milliohms (the main board's 1 mOhm links, R7 and R8)
    text = text.upper().replace('OHM', '').rstrip('R')
    for suffix, factor in (('K', 1e3), ('M', 1e6)):
        if suffix in text:
            return float(text.replace(suffix, '.').rstrip('.')) * factor
    return float(text)


def rt9013_w(i, vin=None):
    vin = d.buck_vout_range()[1] if vin is None else vin
    return (vin - d.RT9013['VSET'] * (1 - d.RT9013_TOL)) * i + vin * d.RT9013['IQ']


def rt9013_ceiling():
    """The largest 1V2 load (A) that keeps the RT9013 at Tj <= 100 C."""
    vin = d.buck_vout_range()[1]
    p = (d.TJ_LIMIT_C - d.AMBIENT_C) / d.RT9013_THETA_JA
    return (p - vin * d.RT9013['IQ']) / (vin - d.RT9013['VSET'] * (1 - d.RT9013_TOL))


def tj(p, theta):
    return d.AMBIENT_C + p * theta


def fpga_resources(asc):
    """icebox_stat counts from the placed and routed bitstream source."""
    tool = ICESTORM / 'icebox_stat'
    if not tool.exists():
        tool = shutil.which('icebox_stat')
        if tool is None:
            raise ValueError('icebox_stat (icestorm) not found')
    text = subprocess.run([str(tool), str(asc)], check=True, capture_output=True, text=True).stdout
    counts = {}
    for line in text.splitlines():
        key, _, value = line.partition(':')
        if value.strip().isdigit():
            counts[key.strip()] = int(value)
    if 'LUTs' not in counts:
        raise ValueError('icebox_stat gave no LUT count for %s' % asc)
    return counts


def fpga_clocks(json_path):
    """Clock nets of every flip-flop and RAM in the synthesized netlist."""
    import json
    top = next(m for m in json.loads(Path(json_path).read_text())['modules'].values()
               if m.get('attributes', {}).get('top'))
    names = {}
    for name, net in top['netnames'].items():
        for bit in net['bits']:
            names.setdefault(bit, name)
    clocks = set()
    for cell in top['cells'].values():
        if cell['type'].startswith(('SB_DFF', 'SB_RAM')):
            for port in ('C', 'RCLK', 'WCLK'):
                if port in cell['connections']:
                    clocks.add(names.get(cell['connections'][port][0]))
    return clocks


def rail_1v2(board, circuit):
    """Check the iCE40 sits on the LDO's rail; return the other 1V2 branch
    currents [(ref, A)] at V1V2_MAX into ground through R x (1 - R_TOL)."""
    fpga, net, ldo, ldo_net = RAIL_1V2[board]
    if circuit.components.get(fpga, ('',))[0] != ICE40_PART:
        raise ValueError('%s: expected %s, netlist has %s' % (fpga, ICE40_PART,
                                                              circuit.components.get(fpga)))
    for pin in ICE40_VCC_PINS:
        if circuit.net(fpga, pin) != net:
            raise ValueError('%s.%s (VCC) on %s, not %s' % (fpga, pin, circuit.net(fpga, pin), net))
    if circuit.net(ldo, '5') != ldo_net:
        raise ValueError('%s.5 (VOUT) on %s, not %s' % (ldo, circuit.net(ldo, '5'), ldo_net))
    if net != ldo_net:
        links = [r for r in circuit.resistors if set(r.ends) == {net, ldo_net}]
        if len(links) != 1 or ohms(links[0].value) > LINK_MAX:
            raise ValueError('%s must reach %s through one <= %g ohm link' % (ldo_net, net, LINK_MAX))
    branches, pll = [], []
    for res in circuit.resistors:
        if net not in res.ends or ldo_net in res.ends and net != ldo_net:
            continue
        far = res.ends[1] if res.ends[0] == net else res.ends[0]
        if far.startswith('/VCCPLL'):
            pll.append(res.ref)       # the iCE40's own PLL supplies: in its peak figure
            continue
        branches.append((res.ref, d.V1V2_MAX / (ohms(res.value) * (1 - R_TOL))))
    others = [r for r, _ in circuit.nets[net]
              if not r.startswith(('C', 'R', 'TP')) and r not in (fpga, ldo)]
    if others:
        raise ValueError('unmodelled parts on %s: %s' % (net, ', '.join(sorted(others))))
    return branches, pll


def stby_loads(circuit):
    """Every current 3V3_STBY can source at 3V3_STBY max, as [(what, A)].
    Raises on any part the model does not know."""
    vmax = d.STBY_LDO_VOUT[1]
    members = sorted(circuit.nets[STBY_NET])
    loads = []
    for ref, pin in members:
        kind = circuit.components[ref]
        if ref == 'U15' and pin == '3':
            continue                                    # the LDO's own output
        if kind[1] == ('Device', 'C'):
            loads.append(('%s leakage' % ref, CAP_LEAK_MAX))
        elif kind[1] == ('Connector', 'TestPoint'):
            continue
        elif kind[0] == 'MAX16054AZT' and pin == '6':
            loads.append(('%s ICC (ASSUME, DS 7 uA typ)' % ref, d.ONOFF_I_MAX))
            btn = circuit.net(ref, '1')
            if {r for r, _ in circuit.nets[btn]} - {ref, 'SW2'}:
                raise ValueError('%s IN net %s has other loads' % (ref, btn))
            loads.append(('%s IN pull-up, button held' % ref, vmax / MAX16054_RPU_MIN))
            out = circuit.net(ref, '5')
            for r, p in sorted(circuit.nets[out]):
                if r == ref or r.startswith('TP'):
                    continue
                res = next((x for x in circuit.resistors if x.ref == r), None)
                if res is not None:
                    far = res.ends[1] if res.ends[0] == out else res.ends[0]
                    if far != '/GND':
                        raise ValueError('%s: %s -> %s not modelled' % (r, out, far))
                    loads.append(('%s OUT into %s' % (ref, r), vmax / (ohms(res.value) * (1 - R_TOL))))
                elif circuit.components[r][0] == d.INSW_PART and p == '1':
                    loads.append(('%s OUT into %s EN (ASSUME)' % (ref, r), EN_LEAK_MAX))
                else:
                    raise ValueError('%s.%s on %s not modelled' % (r, p, out))
        elif kind[0] == 'SN74LVC07A' and pin == '14':
            ins = [p for p in (str(k) for k in (1, 3, 5, 9, 11, 13)) if circuit.net(ref, p) != '/GND']
            loads.append(('%s ICC + dICC x %d inputs (DS max)' % (ref, len(ins)),
                          LVC07_ICC_MAX + LVC07_DICC_MAX * len(ins)))
        else:
            raise ValueError('unmodelled 3V3_STBY load %s.%s (%s)' % (ref, pin, kind[0]))
    return loads


def ht7533_w(i_load, vin=HT_VIN_MAX):
    return (vin - d.STBY_LDO_VOUT[0]) * i_load + vin * max(HT_IGND_MAX, HT_ISS_MAX)


def ht7533_allowed(vin=HT_VIN_MAX):
    """The largest 3V3_STBY load (A) that keeps the HT7533 at Tj <= 100 C."""
    p = (d.TJ_LIMIT_C - d.AMBIENT_C) / HT_THETA_JA
    return (p - vin * max(HT_IGND_MAX, HT_ISS_MAX)) / (vin - d.STBY_LDO_VOUT[0])


def check_board(board, out, validate=True):
    from cosim.netlist import read
    import boardevidence
    import thermal_bind

    out = Path(out)
    if board not in RAIL_1V2:
        raise ValueError('board must be main or cpu')
    if validate:
        boardevidence.validate(board, out)
    refs, pins = thermal_bind.bind(board, out)
    circuit = read(out / f'{board}.net')
    c = Checks('%s thermal: iCE40 1V2 and standby rows at %.0f C ambient (hw/power/board_thermal.py)'
               % (board, d.AMBIENT_C))
    c.info('binding', '%d PCB references and %d model pins match (thermal_bind)' % (refs, pins))

    fpga_dir = ROOT / 'build/fpga' / FPGA_BUILD[board]
    name = FPGA_BUILD[board]
    res = fpga_resources(fpga_dir / f'{name}.asc')
    clocks = fpga_clocks(fpga_dir / f'{name}.json')
    c.info('FPGA design', '%s (build/fpga/%s): %d LUTs, %d DFFs, %d carries, %d BRAMs, %d IOBs, '
           '%d PLLs; clocks %s (12 MHz, doc/hardware/cpu-bus.md)' % (
               name, name, res['LUTs'], res['DFFs'], res['CARRYs'], res['BRAMs'], res['IOBs'],
               res['PLLs'], ', '.join(sorted(clocks))))
    branches, pll = rail_1v2(board, circuit)
    i_branch = sum(i for _, i in branches)
    for ref, i in branches:
        c.info(ref, '1V2 branch <= %.3f mA' % (1e3 * i))
    ceiling = rt9013_ceiling()
    c.info('RT9013 ceiling', '1V2 load <= %.1f mA keeps Tj <= %.0f C (3V3 max %.3f V, 250 C/W); '
           'iCE40 share %.1f mA after %.2f mA of branches' % (
               1e3 * ceiling, d.TJ_LIMIT_C, d.buck_vout_range()[1], 1e3 * (ceiling - i_branch),
               1e3 * i_branch))
    peak = ICE40_ICCPEAK_MAX + (ICE40_ICCPLLPEAK_MAX if pll else 0) + i_branch
    c.check('F1', 'RT9013 at the iCE40 power-up peak (DS1040 ICCPEAK %.1f + ICCPLLPEAK %.1f mA max) '
            '+ branches, %.1f mA' % (1e3 * ICE40_ICCPEAK_MAX, 1e3 * ICE40_ICCPLLPEAK_MAX, 1e3 * peak),
            tj(rt9013_w(peak), d.RT9013_THETA_JA), d.TJ_LIMIT_C, '<=', 'C', fmt='%.1f')
    cells = res['LUTs'] + res['DFFs'] + res['CARRYs']
    c_eff = (ceiling - i_branch) / (cells * 12e6 * d.V1V2_MAX)
    c.info('headroom', 'the ceiling would need %.2f pF switched per used LUT/DFF/carry every 12 MHz '
           'cycle at %.2f V (DS1040 static ICC is only a 25 C typical, %.2f mA)' % (
               1e12 * c_eff, d.V1V2_MAX, 1e3 * ICE40_ICC_STATIC_TYP))
    if ICE40_CORE_MAX is None:
        c.check('F2', 'iCE40 maximum operating core current bounded (DS1040 publishes none; needs '
                'a worst-corner Power Calculator report or a measurement)', 0, 1, '>=', '', fmt='%d')
    else:
        i = ICE40_CORE_MAX + i_branch
        c.check('F2', 'RT9013 at the iCE40 operating maximum %.1f mA + branches' % (1e3 * ICE40_CORE_MAX),
                tj(rt9013_w(i), d.RT9013_THETA_JA), d.TJ_LIMIT_C, '<=', 'C', fmt='%.1f')

    if board == 'main':
        loads = stby_loads(circuit)
        i_load = sum(i for _, i in loads)
        for what, i in loads:
            c.info('3V3_STBY', '%s <= %.1f uA' % (what, 1e6 * i))
        for vin in (d.VBUS_MAX, d.insw_ovlo()[1]):
            c.info('HT7533 at %.2f V' % vin, '%.3f mW, Tj %.2f C' % (
                1e3 * ht7533_w(i_load, vin), tj(ht7533_w(i_load, vin), HT_THETA_JA)))
        c.check('H1', 'HT7533-2 3V3_STBY load %.0f uA vs the most that holds Tj <= %.0f C at %.0f V in'
                % (1e6 * i_load, d.TJ_LIMIT_C, HT_VIN_MAX),
                1e3 * i_load, 1e3 * ht7533_allowed(), '<=', 'mA', fmt='%.3f')
        p = ht7533_w(i_load)
        c.check('H2', 'HT7533-2 standby LDO at its rated %.0f V input: %.1f mW x %.0f C/W (Holtek Rev 1.30)'
                % (HT_VIN_MAX, 1e3 * p, HT_THETA_JA), tj(p, HT_THETA_JA), d.TJ_LIMIT_C, '<=', 'C',
                fmt='%.1f')
    return c.done()


def main(argv):
    if len(argv) != 2:
        print('usage: thermal.py board main|cpu BUILD_DIR', file=sys.stderr)
        return 2
    try:
        return check_board(*argv)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('FAIL %s thermal: %s' % (argv[0], error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

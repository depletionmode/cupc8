#!/usr/bin/env python3
"""MB-005: bind the main board's power models to its receipt.

The power checks (POW-001..008, THM-001) model the parts and values in
hw/power/design.py and hw/boards/main.py's POWER table. This checks that the
built board is that circuit: every modelled part's LCSC number in the BOM,
the values the models use, and the pins of the input path, the regulators
and the PWR_HI comparator on the nets the models assume.

    python3 hw/power/main_bind.py build/hw/main
"""

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
sys.path.insert(0, str(ROOT / 'hw/boards'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cosim.netlist import read  # noqa: E402
import boardevidence  # noqa: E402
import design as d  # noqa: E402
from spice import Checks  # noqa: E402

# ref: POWER key (hw/boards/main.py), the model's parts
PARTS = {'F1': 'FUSE_IN', 'D1': 'TVS', 'C1': 'VBUS_C_AHEAD', 'U2': 'EFUSE', 'U16': 'ONOFF', 'U15': 'STBY_LDO',
         'C17': 'STBY_LDO_COUT', 'R3': 'EFUSE_RILM', 'R58': 'EFUSE_OVLO_R1', 'R59': 'EFUSE_OVLO_R2',
         'C15': 'EFUSE_DVDT', 'C3': '5V_SYS_BULK', 'U3': 'BUCK', 'L1': 'BUCK_L', 'C5': 'BUCK_CIN',
         'C7': 'BUCK_COUT', 'R5': 'BUCK_R1', 'R6': 'BUCK_R2', 'R1': 'CC_RD', 'R2': 'CC_RD',
         'R13': 'CC_AVG_R', 'R14': 'CC_AVG_R', 'R15': 'CC_REF_R1', 'R16': 'CC_REF_R2', 'R7': 'LINK', 'R8': 'LINK',
         **{'F%d00' % n: 'SLOT_PTC' for n in range(2, 8)}, **{'R%d01' % n: 'SLOT_LINK' for n in range(2, 8)}}
OTHER = {'U4': 'C58464', 'U5': 'C702117'}           # RT9013-12GB (POW-002), TLV7011 (POW-005)
# (ref, pin): net the models assume
PINS = {('J1', 'A4B9'): '/VBUS', ('J1', 'B4A9'): '/VBUS', ('F1', '1'): '/VBUS', ('F1', '2'): '/VBUS_F',
        ('D1', '1'): '/VBUS_F', ('C1', '1'): '/VBUS_F', ('U2', '5'): '/VBUS_F', ('U2', '6'): '/5V_SYS',
        ('U2', '9'): '/EFUSE_ILM', ('U2', '2'): '/EFUSE_OVLO', ('U2', '7'): '/EFUSE_DVDT', ('U2', '1'): '/PWR_EN',
        ('U15', '2'): '/VBUS_F', ('U15', '3'): '/3V3_STBY', ('U16', '6'): '/3V3_STBY', ('U16', '5'): '/PWR_EN',
        ('C3', '1'): '/5V_SYS', ('U3', '1'): '/5V_SYS', ('U3', '4'): '/5V_SYS', ('U3', '6'): '/BUCK_FB',
        ('L1', '2'): '/3V3_BUCK', ('C7', '1'): '/3V3_BUCK', ('U4', '1'): '/+3V3', ('U4', '5'): '/1V2_LDO',
        ('C10', '1'): '/1V2_LDO', ('R4', '1'): '/5V_SYS', ('R4', '2'): '/+5V'}
RES = {'R3': ({'/EFUSE_ILM', '/GND'}, d.INSW_RILM), 'R58': ({'/VBUS_F', '/EFUSE_OVLO'}, d.INSW_OVLO_R[0]),
       'R59': ({'/EFUSE_OVLO', '/GND'}, d.INSW_OVLO_R[1]), 'R5': ({'/3V3_BUCK', '/BUCK_FB'}, d.BUCK_R1),
       'R6': ({'/BUCK_FB', '/GND'}, d.BUCK_R2), 'R1': ({'/CC1', '/GND'}, 5.1e3), 'R2': ({'/CC2', '/GND'}, 5.1e3),
       'R13': ({'/CC1', '/CC_AVG'}, d.CC_AVG_R), 'R14': ({'/CC2', '/CC_AVG'}, d.CC_AVG_R),
       'R15': ({'/+3V3', '/CC_REF'}, d.CC_REF_R[0]), 'R16': ({'/CC_REF', '/GND'}, d.CC_REF_R[1]),
       'R7': ({'/3V3_BUCK', '/+3V3'}, 0.001), 'R8': ({'/1V2_LDO', '/+1V2'}, 0.001)}


def ohms(value):
    text = value.split()[0]
    if text.endswith('m'):
        return float(text[:-1]) * 1e-3
    scale = {'k': 1e3, 'K': 1e3, 'M': 1e6}.get(text[-1], 1.0)
    return float(text[:-1] if scale != 1.0 else text) * scale


def check(out):
    import main
    bom = {}
    with (out / 'fab/bom.csv').open() as f:
        for row in csv.DictReader(f):
            for ref in row['Designator'].split(','):
                bom[ref.strip()] = row['LCSC Part #']
    circuit = read(out / 'main.net')
    bad = []
    for ref, key in PARTS.items():
        if bom.get(ref) != main.POWER[key][1]:
            bad.append('%s: BOM %s, POWER[%s] %s' % (ref, bom.get(ref), key, main.POWER[key][1]))
    for ref, lcsc in OTHER.items():
        if bom.get(ref) != lcsc:
            bad.append('%s: BOM %s, modelled %s' % (ref, bom.get(ref), lcsc))
    for pin, net in PINS.items():
        if circuit.net(*pin) != net:
            bad.append('%s.%s on %s, modelled on %s' % (pin[0], pin[1], circuit.net(*pin), net))
    for ref, (ends, value) in RES.items():
        r = next((x for x in circuit.resistors if x.ref == ref), None)
        if r is None or set(r.ends) != ends or abs(ohms(r.value) - value) > 1e-6 * value:
            bad.append('%s: %s, modelled %s %g ohm' % (ref, r and (r.ends, r.value), sorted(ends), value))
    c15 = circuit.components.get('C15', ('',))[0]
    if c15 != '680p' or abs(d.INSW_CDVDT - 680e-12) > 1e-15:
        bad.append('C15 (dVdt): %s, modelled %g F' % (c15, d.INSW_CDVDT))
    return bad


def main(argv):
    out = Path(argv[1] if len(argv) > 1 else ROOT / 'build/hw/main').resolve()
    c = Checks('MB-005 main-board power models bound to the receipt (hw/power/main_bind.py)')
    try:
        boardevidence.validate('main', out)
        bad = check(out)
    except (OSError, ValueError, KeyError) as error:
        bad = ['receipt: %s' % error]
    for line in bad:
        c.info('differs', line)
    c.check('B1', 'modelled power parts, values and pins that differ from the receipt', len(bad), 0, '<=', '',
            fmt='%d')
    return c.done()


if __name__ == '__main__':
    sys.exit(main(sys.argv))

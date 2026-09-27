#!/usr/bin/env python3
"""Bind thermal-model heat sources to a KiCad netlist and matching PCB.

This checks identity and topology, not board thermal resistance. The CLI is
deliberately red after a successful binding: no measured/calibrated package,
pad, enclosure and neighbour coupling bounds have been supplied.
"""

from pathlib import Path
import sys
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cosim.netlist import read
import design as d

RP_FOOTPRINT = 'Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm'
RP_VALUE = ('RP2040', ('MCU_RaspberryPi', 'RP2040'))
RP_3V3_PINS = ('1', '10', '22', '33', '42', '43', '44', '48', '49')
RP_1V1_PINS = ('23', '45', '50')

# Values are KiCad (value, library source) pairs. Heat-source footprints are
# checked exactly: JEDEC theta_JA is package-dependent. Each listed component's
# *entire* pad-to-net map is compared between netlist and routed PCB.
SPECS = {
    'main': {
        'parts': {
            'U2': ('TPS259470ARPWR', ('jlc', 'TPS259470ARPWR')),
            'U3': ('TLV62569PDDCR', ('jlc', 'TLV62569PDDCR')),
            'U4': ('RT9013-12GB', ('jlc', 'RT9013-12GB')),
            'U15': ('HT7533-2', ('jlc', 'HT7533-2_C82217')),
            'L1': ('2.2uH', ('Device', 'L')),
            'R3': ('1.13k', ('Device', 'R')),
            'R5': ('453k', ('Device', 'R')),
            'R6': ('100k', ('Device', 'R')),
            'C3': ('22u', ('Device', 'C')),
            'C5': ('10u', ('Device', 'C')),
            'C7': ('22u', ('Device', 'C')),
            'C9': ('1u', ('Device', 'C')),
            'C10': ('1u', ('Device', 'C')),
            'C15': ('680p', ('Device', 'C')),
        },
        'footprints': {
            'U2': 'jlc:VQFN-10_L2.0-W2.0-P0.45-TL',
            'U3': 'jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL',
            'U4': 'jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR',
            'U15': 'jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR',
        },
        'pins': {
            ('U2', '5'): '/VBUS_F', ('U2', '6'): '/5V_SYS',
            ('U2', '8'): '/GND', ('U2', '9'): '/EFUSE_ILM',
            ('U2', '7'): '/EFUSE_DVDT',
            ('U3', '1'): '/5V_SYS', ('U3', '4'): '/5V_SYS',
            ('U3', '2'): '/GND', ('U3', '3'): '/BUCK_SW',
            ('U3', '6'): '/BUCK_FB',
            ('L1', '1'): '/BUCK_SW', ('L1', '2'): '/3V3_BUCK',
            ('R5', '1'): '/3V3_BUCK', ('R5', '2'): '/BUCK_FB',
            ('R6', '1'): '/BUCK_FB', ('R6', '2'): '/GND',
            ('U4', '1'): '/+3V3', ('U4', '3'): '/+3V3',
            ('U4', '2'): '/GND', ('U4', '5'): '/1V2_LDO',
            ('U15', '2'): '/VBUS_F', ('U15', '1'): '/GND',
            ('U15', '3'): '/3V3_STBY',
            ('C3', '1'): '/5V_SYS', ('C5', '1'): '/5V_SYS',
            ('C7', '1'): '/3V3_BUCK', ('C9', '1'): '/+3V3',
            ('C10', '1'): '/1V2_LDO',
        },
        'closed': {
            '/BUCK_SW': {('U3', '3'), ('L1', '1')},
            '/BUCK_FB': {('U3', '6'), ('R5', '2'), ('R6', '1')},
            '/EFUSE_ILM': {('U2', '9'), ('R3', '1')},
            '/EFUSE_DVDT': {('U2', '7'), ('C15', '1')},
        },
    },
    'cpu': {
        'parts': {'U3': ('RT9013-12GB', ('jlc', 'RT9013-12GB')),
                  'C21': ('1u', ('Device', 'C')),
                  'C22': ('4.7u', ('Device', 'C')),
                  **{f'C{n}': ('100n', ('Device', 'C')) for n in range(1, 5)}},
        'footprints': {'U3': 'jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR'},
        'pins': {('U3', '1'): '/3V3', ('U3', '3'): '/3V3',
                 ('U3', '2'): '/GND', ('U3', '5'): '/1V2',
                 ('C21', '1'): '/3V3', ('C22', '1'): '/1V2',
                 **{(f'C{n}', '1'): '/1V2' for n in range(1, 5)},
                 **{('U1', str(n)): '/1V2' for n in (27, 40, 92, 111)}},
        'closed': {},
    },
    'gpu': {
        'parts': {'U7': ('TPS63802DLAR', ('jlc', 'TPS63802DLAR')),
                  'L1': ('470n', ('Device', 'L')),
                  'R26': ('300k', ('Device', 'R')),
                  'R27': ('33k', ('Device', 'R')),
                  'C21': ('10u', ('Device', 'C')),
                  'C22': ('22u', ('Device', 'C')),
                  'C23': ('22u', ('Device', 'C'))},
        'footprints': {'U7': 'jlc:VSON-10_L3.0-W2.0-P0.50-TL'},
        'pins': {('U7', '1'): '/HDMI_5V_F', ('U7', '10'): '/HDMI_5V_F',
                 ('U7', '6'): '/HDMI_5V', ('U7', '2'): '/GND',
                 ('U7', '3'): '/GND', ('U7', '8'): '/GND',
                 ('U7', '9'): '/BB_L1', ('U7', '7'): '/BB_L2',
                 ('U7', '4'): '/BB_FB',
                 ('L1', '1'): '/BB_L1', ('L1', '2'): '/BB_L2',
                 ('R26', '1'): '/HDMI_5V', ('R26', '2'): '/BB_FB',
                 ('R27', '1'): '/BB_FB', ('R27', '2'): '/GND',
                 ('C21', '1'): '/HDMI_5V_F',
                 ('C22', '1'): '/HDMI_5V', ('C23', '1'): '/HDMI_5V'},
        'closed': {'/BB_L1': {('U7', '9'), ('L1', '1')},
                   '/BB_L2': {('U7', '7'), ('L1', '2')},
                   '/BB_FB': {('U7', '4'), ('R26', '2'), ('R27', '1')}},
    },
    'io': {
        'parts': {'U7': ('TPS61023DRLR', ('jlc', 'TPS61023DRLR')),
                  'U5': ('SY6280AAC', ('jlc', 'SY6280AAC')),
                  'L1': ('1u', ('Device', 'L')),
                  'R16': ('750k', ('Device', 'R')),
                  'R17': ('100k', ('Device', 'R')),
                  'C20': ('10u', ('Device', 'C')),
                  'C23': ('22u', ('Device', 'C')),
                  'C24': ('22u', ('Device', 'C'))},
        'footprints': {'U7': 'jlc:SOT-563_L1.6-W1.2-P0.50-LS1.6-BR',
                       'U5': 'jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BL'},
        'pins': {('U7', '2'): '/+5V', ('U7', '3'): '/+5V',
                 ('U7', '4'): '/GND', ('U7', '5'): '/BOOST_SW',
                 ('U7', '6'): '/VBOOST', ('U7', '1'): '/BOOST_FB',
                 ('U5', '5'): '/VBOOST', ('U5', '1'): '/VBUS',
                 ('U5', '2'): '/GND',
                 ('L1', '1'): '/+5V', ('L1', '2'): '/BOOST_SW',
                 ('R16', '1'): '/VBOOST', ('R16', '2'): '/BOOST_FB',
                 ('R17', '1'): '/BOOST_FB', ('R17', '2'): '/GND',
                 ('C20', '1'): '/+5V',
                 ('C23', '1'): '/VBOOST', ('C24', '1'): '/VBOOST'},
        'closed': {'/BOOST_SW': {('U7', '5'), ('L1', '2')},
                   '/BOOST_FB': {('U7', '1'), ('R16', '2'), ('R17', '1')}},
    },
}

for _board in ('storage', 'eink', 'system'):
    SPECS[_board] = {'parts': {}, 'footprints': {}, 'pins': {}, 'closed': {}}

for _board in ('gpu', 'io', 'storage', 'eink', 'system'):
    _spec = SPECS[_board]
    _rail = '/+3V3' if _board == 'system' else '/3V3'
    _spec['parts']['U1'] = RP_VALUE
    _spec['footprints']['U1'] = RP_FOOTPRINT
    _spec['pins'].update({('U1', pin): _rail for pin in RP_3V3_PINS})
    _spec['pins'].update({('U1', pin): '/1V1' for pin in RP_1V1_PINS})
    _spec['pins'][('U1', '57')] = '/GND'
    _spec['pins'][('U1', '19')] = '/GND'  # TESTEN tied low
    _caps = {'C9': '100n', 'C10': '100n', 'C13': '1u'} if _board == 'system' else \
            {'C12': '100n', 'C13': '100n', 'C14': '1u'}
    for _ref, _value in _caps.items():
        _spec['parts'][_ref] = (_value, ('Device', 'C'))
        _spec['pins'][(_ref, '1')] = '/1V1'
        _spec['pins'][(_ref, '2')] = '/GND'
    _spec['closed']['/1V1'] = ({('U1', pin) for pin in RP_1V1_PINS} |
                              {(_ref, '1') for _ref in _caps} |
                              ({('TP7', '1')} if _board == 'system' else set()))


def check_model_constants(board_name):
    """Reject a design.py parameter drift hidden by unchanged board values."""
    def scalar(label, actual, expected):
        if not math.isclose(actual, expected, rel_tol=1e-12):
            raise ValueError(f'{label}: model {actual} differs from fitted {expected}')

    if board_name == 'main':
        if (d.INSW_PART, d.BUCK_PACKAGE) != ('TPS259470ARPWR', 'DDC'):
            raise ValueError('main eFuse or buck model identity/package differs from fitted parts')
        for label, actual, expected in (
                ('buck L1', d.BUCK_L, 2.2e-6), ('buck R5', d.BUCK_R1, 453e3),
                ('buck R6', d.BUCK_R2, 100e3), ('buck C5', d.BUCK_CIN, 10e-6),
                ('buck C7', d.BUCK_COUT, 22e-6)):
            scalar(label, actual, expected)
    elif board_name == 'gpu':
        if d.GPUB_PART != 'TPS63802DLAR':
            raise ValueError('GPU buck-boost model identity differs from fitted part')
        for label, actual, expected in (
                ('GPU L1', d.GPUB_L, 470e-9), ('GPU R26', d.GPUB_R1, 300e3),
                ('GPU R27', d.GPUB_R2, 33e3), ('GPU C21', d.GPUB_CIN, 10e-6),
                ('GPU C22/C23', d.GPUB_COUT, 44e-6)):
            scalar(label, actual, expected)
    elif board_name == 'io':
        if d.IOB_PART != 'TPS61023DRLR':
            raise ValueError('IO boost model identity differs from fitted part')
        for label, actual, expected in (
                ('IO L1', d.IOB_L, 1e-6), ('IO R16', d.IOB_R1, 750e3),
                ('IO R17', d.IOB_R2, 100e3), ('IO C20', d.IOB_CIN, 10e-6),
                ('IO C23/C24', d.IOB_COUT, 44e-6)):
            scalar(label, actual, expected)


def bind(board_name, out):
    """Raise on any modeled part, package, pin, or feedback topology drift."""
    import pcbnew

    if board_name not in SPECS:
        raise ValueError(f'unsupported thermal board {board_name}')
    out = Path(out)
    circuit = read(out / f'{board_name}.net')
    board = pcbnew.LoadBoard(str(out / f'{board_name}.kicad_pcb'))
    spec = SPECS[board_name]
    check_model_constants(board_name)
    footprints = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in footprints:
            raise ValueError(f'duplicate PCB reference {ref}')
        footprints[ref] = fp
    for ref, expected in spec['parts'].items():
        got = circuit.components.get(ref)
        if got != expected:
            raise ValueError(f'{ref}: modeled value/library {expected}, netlist has {got}')
    for (ref, pin), net in spec['pins'].items():
        if circuit.net(ref, pin) != net:
            raise ValueError(f'{ref}.{pin}: modeled {net}, netlist has {circuit.net(ref, pin)}')
    for net, expected in spec['closed'].items():
        got = set(circuit.nets.get(net, ()))
        if got != expected:
            raise ValueError(f'{net}: modeled pins {sorted(expected)}, netlist has {sorted(got)}')
    refs = set(spec['parts']) | {ref for ref, _ in spec['pins']}
    for ref in sorted(refs):
        fp = footprints.get(ref)
        if fp is None:
            raise ValueError(f'{ref}: missing PCB footprint')
        if ref in spec['parts'] and fp.GetValue() != spec['parts'][ref][0]:
            raise ValueError(f'{ref}: PCB value {fp.GetValue()} differs from model')
        if ref in spec['footprints']:
            lib_id = fp.GetFPID()
            actual = f'{lib_id.GetLibNickname()}:{lib_id.GetLibItemName()}'
            if actual != spec['footprints'][ref]:
                raise ValueError(f'{ref}: PCB package {actual} differs from {spec["footprints"][ref]}')
        pcb_pins = {}
        for pad in fp.Pads():
            pin = pad.GetNumber()
            if not pin:
                if pad.GetNetname():
                    raise ValueError(f'{ref}: unnumbered pad has net {pad.GetNetname()}')
                continue  # repeated unnumbered, netless mechanical copper
            if pin in pcb_pins:
                raise ValueError(f'{ref}: duplicate PCB pad {pin}')
            pcb_pins[pin] = pad.GetNetname()
        modeled_pins = {pin: net for (component, pin), net in circuit.pins.items()
                        if component == ref}
        if pcb_pins != modeled_pins:
            raise ValueError(f'{ref}: PCB pads differ from exported netlist: '
                             f'{pcb_pins} vs {modeled_pins}')
    return len(refs), len(spec['pins'])


GAPS = {
    'main': 'package-to-board/enclosure theta, eFuse fault pulse, copper/pad/contact loss and neighbouring heat unbounded',
    'cpu': 'RT9013 heat path, input/feed and 1V2 pad/spoke/contact losses unbounded; FPGA core maximum load unverified',
    'gpu': 'RP2040 VREG maximum 1V1 load/loss and local board/enclosure thermal path unbounded',
    'io': 'RP2040 VREG maximum 1V1 load/loss and boost/SY6280 shared board/enclosure path unbounded',
    'storage': 'RP2040 VREG maximum 1V1 load/loss and board/enclosure path unbounded',
    'eink': 'RP2040 VREG maximum 1V1 load/loss and board/enclosure path unbounded',
    'system': 'RP2040 VREG maximum 1V1 load/loss and board/enclosure path unbounded',
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != '--binding-only'):
        print('usage: thermal_bind.py BOARD BUILD_DIR [--binding-only]', file=sys.stderr)
        return 2
    board_name, out = argv[:2]
    try:
        refs, pins = bind(board_name, out)
    except (OSError, ValueError) as error:
        print(f'FAIL {board_name} thermal binding: {error}', file=sys.stderr)
        return 1
    print(f'BIND PASS {board_name}: {refs} PCB references, {pins} model pins and feedback nets match')
    if len(argv) == 3:
        return 0
    print(f'FAIL {board_name} thermal closure: {GAPS[board_name]}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())

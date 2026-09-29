"""Conservative E2E net coverage accounting for all eight KiCad netlists.

Two waiver kinds exist: a pin-exact, electrically unused reserved contact,
and a non-digital (supply, return, regulator-internal) net whose attached
pins are all passive, power/analog or static straps, naming the analog
catalogue checks that cover it. Classification is a work queue, not
evidence that a circuit was simulated.
"""
import re


def family(board, name):
    """Assign every coverage gap to its next required model family."""
    if name == 'GND' or name.startswith(('+', 'GND')) or re.match(
            r'^(?:\dV\d|5V_SYS|VCC|VBOOST|VBUS|EPD_VCC|SLOT\d+_5V)', name):
        return 'power_and_return'
    if re.search(r'QSPI|^FL[01]_|BOOT|SWD|PROG|CDONE|CRESET|STRAP', name):
        return 'boot_and_programming'
    if re.search(r'CLK|XIN|XOUT|XTAL|OSC|(?:^|_)RST|nRST|nPOR|nMR|^RUN$|^EN$', name):
        return 'clock_and_reset'
    if re.search(r'^CPU_|^FPGA_|^MEM_', name):
        return 'cpu_and_memory'
    if re.search(r'LED|^GPO|^ISET$', name):
        return 'indicators'
    if re.search(r'USB|^CC[12]$|HDMI|^HD_|^DDC|^EPD|^SD_|HPD|UART|U0RXD|U0TXD', name):
        return 'external_io'
    if re.search(r'SPI|^BR_|MISO|MOSI|SCK|CS_n|IRQ|PRSNT|MUX|I2C', name):
        return 'slot_and_control_bus'
    if re.search(r'PWR|BUCK|BOOST|EFUSE|SENSE|FB|GATE|OVLO|ILM|^BB_L|^Q[12]_B$|^SW$', name):
        return 'power_policy'
    return 'other_functional'


def _passive_reserved(circuit, net, connector, pin):
    """Require one reserved connector contact and one passive test point."""
    nodes = circuit.nets.get(net)
    return nodes is not None and len(nodes) == 2 and (connector, pin) in nodes and any(
        ref.startswith('TP') and pad == '1' and
        circuit.components[ref][1] == ('Connector', 'TestPoint')
        for ref, pad in nodes if (ref, pad) != (connector, pin))


def _mating_nc(circuit, connector, pin):
    net = circuit.net(connector, pin)
    return net is not None and net.startswith('unconnected-') and circuit.nets[net] == ((connector, pin),)


def reviewed_reserved_waivers(circuits):
    """Pin-bound waivers for unused reserved contacts, never active signals.

    Main-to-card contact maps are fixed by the connector drawing. A newly
    attached IC, resistor, power net, or non-NC mating contact fails the
    waiver even when the original net name remains unchanged.
    """
    main = circuits['main']
    waivers = {}

    def add(board, net, connector, pin, mate, mate_ref, mate_pin):
        if not _passive_reserved(circuits[board], f'/{net}', connector, pin):
            return
        if not _mating_nc(circuits[mate], mate_ref, mate_pin):
            return
        waivers[f'{board}:{net}'] = {
            'family': 'reserved_contact',
            'reason': 'Only a passive test point is attached; the mating contact is KiCad NC.',
            'pins': [f'{ref}.{pad}' for ref, pad in circuits[board].nets[f'/{net}']],
            'mating_nc': f'{mate}.{mate_ref}.{mate_pin}',
        }

    for net, nodes in main.nets.items():
        name = net.lstrip('/')
        if name.startswith('CPU_RSVD_'):
            connector = next((pin for ref, pin in nodes if ref == 'J2'), None)
            if connector:
                add('main', name, 'J2', connector, 'cpu', 'J1', connector)
        elif name.startswith('SYS_RSVD_'):
            connector = next((pin for ref, pin in nodes if ref == 'J3'), None)
            if connector:
                side, index = name.rsplit('_', 1)[-1][0], name.rsplit('_', 1)[-1][1:]
                # Only A1/A2/A3 are NC on the system card; B1/B2
                # terminate at another passive test point, handled below.
                if side == 'A':
                    card_pin = {'A1': 'A29', 'A2': 'A30', 'A3': 'A32'}.get(side + index)
                    if card_pin:
                        add('main', name, 'J3', connector, 'system', 'J2', card_pin)
        elif re.fullmatch(r'SLOT[1-6]_RSVD_A[1-5]', name):
            slot = int(name[4])
            connector = next((pin for ref, pin in nodes if ref == f'J{10+slot}'), None)
            if connector and all(_mating_nc(circuits[card], 'J1', connector)
                                 for card in ('gpu', 'io', 'storage', 'wifi', 'eink')):
                add('main', name, f'J{10+slot}', connector, 'gpu', 'J1', connector)
                if f'main:{name}' in waivers:
                    waivers[f'main:{name}']['mating_nc'] = 'all five slot-card J1 contacts'

    system = circuits['system']
    for name, main_pin, card_pin in (('RSVD_B1', '61', 'B29'), ('RSVD_B2', '62', 'B30')):
        if _passive_reserved(system, f'/{name}', 'J2', card_pin) and \
                _passive_reserved(main, f'/SYS_{name}', 'J3', main_pin):
            waivers[f'system:{name}'] = {
                'family': 'reserved_contact',
                'reason': 'Only passive test points on both sides of this reserved contact.',
                'pins': [f'{ref}.{pin}' for ref, pin in system.nets[f'/{name}']],
                'mating_nc': f'main.J3.{main_pin}: passive reserved contact',
            }
            waivers[f'main:SYS_{name}'] = {
                'family': 'reserved_contact',
                'reason': 'Only passive test points on both sides of this reserved contact.',
                'pins': [f'{ref}.{pin}' for ref, pin in main.nets[f'/SYS_{name}']],
                'mating_nc': f'system.J2.{card_pin}: passive reserved contact',
            }
    return waivers


# Non-digital nets: supply rails, returns and regulator-internal nodes. The
# digital co-simulation assumes these rails are present; their behaviour is
# the job of the named analog checks (catalogue rows with a command). A net
# is waived only while every attached pin is a passive part, a connector
# contact, a power/analog pin of a listed IC, or a listed static strap pin.
# Any other package pin (a GPIO, a logic input or output) on the net removes
# the waiver and the net becomes a coverage gap again.
POWER_PINS = {
    'ICE40HX4K-TQ144': {'VCC', 'VCCIO_0', 'VCCIO_1', 'VCCIO_2', 'VCCIO_3', 'VCC_SPI',
                        'VPP_2V5', 'VCCPLL0', 'VCCPLL1', 'GNDPLL0', 'GNDPLL1', 'GND'},
    'RP2040': {'IOVDD', 'DVDD', 'VREG_VIN', 'VREG_VOUT', 'USB_VDD', 'ADC_AVDD', 'GND'},
    'W25Q32JVSSIQ': {'VCC', 'GND'},
    'W25Q16JVSSIQ': {'VCC', 'GND'},
    '74LVC1G125GW': {'VCC', 'GND'},
    'TPD4E05U06DQAR': {'GND'},
    'USBLC6-2SC6': {'VBUS', 'GND'},
    'IS62WV5128EBLL-45HLI': {'VDD', 'GND'},
    'SST39VF040': {'VDD', 'VSS'},
    'CD74HC4051PWR': {'VCC', 'GND'},
    'TCA9555PWR': {'VCC', 'GND'},
    'MAX811TEUS': {'VCC', 'GND'},
    'TLV7011DBVR': {'VCC', 'VEE'},
    'MAX16054AZT': {'VCC', 'GND', 'IN', 'OUT'},   # IN/OUT: the POWER switch and the eFuse enable (MB-053)
    'ESP32-C3-MINI-1U-N4': {'3V3', 'GND'},
    '12MHz': {'VDD', 'GND', 'G'},
    'MMBT3904': {'E'},
    '2N7002': {'S'},
    # regulators, switches and the eFuse: their power and analog-control pins
    'HT7533-2': {'VIN', 'VOUT', 'GND'},
    'RT9013-12GB': {'VIN', 'VOUT', 'EN', 'GND'},
    'TLV62569PDDCR': {'VIN', 'EN', 'SW', 'FB', 'GND'},
    'TLV62569DBVR': {'VIN', 'EN', 'SW', 'FB', 'GND'},
    'TPS259470ARPWR': {'IN', 'OUT', 'DVDT', 'ILM', 'OVLO/OVCSEL', 'EN/UVLO', 'GND'},
    'TPS63802DLAR': {'VIN', 'EN', 'VOUT', 'FB', 'L1', 'L2', 'GND', 'AGND'},
    'TPS61023DRLR': {'VIN', 'EN', 'VOUT', 'FB', 'SW', 'GND'},
    'SY6280AAC': {'IN', 'OUT', 'ISET', 'GND'},
}
# Static logic straps tied to a rail. They are constants of the design,
# checked by pin consistency and the board's pinout rows, never toggled.
STRAP_PINS = {
    'TCA9555PWR': {'A0', 'A1', 'A2'},
    'CD74HC4051PWR': {'VEE', '~{E}'},
    '12MHz': {'~{OE}'},
    'W25Q32JVSSIQ': {'HOLD#orRESET#(IO3)', 'WP#(IO2)'},
    'RP2040': {'TESTEN'},
    'MAX16054AZT': {'CLEAR'},
    'ESP32-C3-MINI-1U-N4': {'IO2', 'IO8'},        # boot-mode straps sampled at reset (WC-006)
    'TPS63802DLAR': {'MODE'},
    '2N7002': {'G'},
}
_PASSIVE = re.compile(r'^(?:R|RN|C|L|F|FB|D|TP|SW)\d+$')

# board -> net -> named analog checks (catalogue ids). Every board's rails
# also carry that board's power and thermal rows.
_BOARD_ROWS = {'main': ('MB-005', 'MB-006'), 'cpu': ('CC-005', 'CC-006'),
               'gpu': ('GC-005', 'GC-006'), 'io': ('IC-005', 'IC-006'),
               'storage': ('SC-005', 'SC-006'), 'eink': ('EC-005', 'EC-006'),
               'system': ('YC-005', 'YC-006'), 'wifi': ('WC-005', 'WC-010')}
_PINOUT_ROWS = {'main': 'MB-004', 'cpu': 'CC-004', 'gpu': 'GC-004', 'io': 'IC-004',
                'storage': 'SC-004', 'eink': 'EC-004', 'system': 'YC-004', 'wifi': 'WC-004'}
ANALOG_NETS = {
    'main': {'GND': (), '+5V': ('POW-006',), '+3V3': ('POW-001',), '+1V2': ('POW-002',),
             '5V_SYS': ('POW-004', 'POW-006'), '3V3_BUCK': ('POW-001',),
             '1V2_LDO': ('POW-002',), '3V3_STBY': (), 'VBUS': ('POW-004',),
             'VBUS_F': ('POW-004', 'POW-006'), 'VCCPLL0': ('POW-002',),
             'VCCPLL1': ('POW-002',), 'BUCK_FB': ('POW-001',), 'BUCK_SW': ('POW-001',),
             'EFUSE_DVDT': ('POW-004',), 'EFUSE_ILM': ('POW-004', 'POW-006'),
             'EFUSE_OVLO': ('POW-004', 'POW-006'),
             # the POWER switch and the eFuse enable it drives: the machine is
             # modelled powered; the on/off circuit is MB-053's netlist check
             'PWR_BTN': ('MB-053',), 'PWR_EN': ('MB-053', 'POW-004'),
             **{f'SLOT{s}_5V{x}': ('POW-006',) for s in range(1, 7) for x in ('', '_F', '_L')}},
    'cpu': {'GND': (), '3V3': (), '1V2': (), 'VCCPLL0': (), 'VCCPLL1': (),
            'GNDPLL0': (), 'GNDPLL1': ()},
    'gpu': {'GND': (), '+5V': (), '3V3': (), '1V1': (), 'HDMI_5V': ('POW-008',),
            'HDMI_5V_F': ('POW-008',), 'BB_FB': ('POW-008',), 'BB_L1': ('POW-008',),
            'BB_L2': ('POW-008',)},
    'io': {'GND': (), '+5V': ('POW-006',), '3V3': (), '1V1': (), 'VBOOST': ('POW-007',),
           'VBUS': ('POW-007', 'POW-006'), 'BOOST_FB': ('POW-007',),
           'BOOST_SW': ('POW-007',), 'ISET': ('POW-006',)},
    'storage': {'GND': (), '+5V': (), '3V3': (), '1V1': ()},
    'eink': {'GND': (), '+5V': (), '3V3': (), '1V1': ()},
    'system': {'GND': (), '+3V3': (), '1V1': ()},
    'wifi': {'GND': (), '+5V': ('POW-003',), '3V3': ('POW-003',), 'FB': ('POW-003',),
             'SW': ('POW-003',),
             # static boot-mode straps (resistors to a rail), WC-006 checks their levels
             'STRAP2': ('WC-006',), 'STRAP8': ('WC-006',)},
}


def reviewed_analog_waivers(circuits, implemented=None):
    """Pin-bound waivers for supply, return and regulator-internal nets.

    `implemented` is the set of catalogue ids that have a command; a waiver
    whose named checks are not all implemented is withheld (the net stays a
    gap). The waiver records the pins it was granted for.
    """
    waivers = {}
    for board, nets in ANALOG_NETS.items():
        circuit = circuits.get(board)
        if circuit is None:
            continue
        for name, extra in nets.items():
            pins = circuit.nets.get(f'/{name}')
            if not pins:
                continue
            ok, straps = True, []
            for ref, pin in pins:
                if _PASSIVE.match(ref) or ref.startswith('J'):
                    continue
                value = circuit.components[ref][0]
                label = (circuit.pin_names or {}).get((ref, pin))
                if label in POWER_PINS.get(value, ()):
                    continue
                if label in STRAP_PINS.get(value, ()):
                    straps.append(f'{ref}.{pin} {label}')
                    continue
                ok = False
                break
            checks = sorted(set(_BOARD_ROWS[board]) | set(extra) |
                            ({_PINOUT_ROWS[board], 'E2E-005'} if straps or 'PLL' in name else set()))
            if not ok or (implemented is not None and not set(checks) <= implemented):
                continue
            waivers[f'{board}:{name}'] = {
                'family': 'non_digital',
                'reason': 'supply, return or regulator-internal node: every attached pin is '
                          'passive, a connector contact, a power/analog pin or a static strap',
                'checks': checks,
                'pins': [f'{ref}.{pin}' for ref, pin in pins],
                'static_straps': straps,
            }
    return waivers


def audit(circuits, executed, structural, implemented=None):
    waivers = reviewed_reserved_waivers(circuits)
    analog = reviewed_analog_waivers(circuits, implemented)
    gaps, structural_only, families = [], [], {}
    for board, circuit in circuits.items():
        for net in circuit.nets:
            if net.startswith('unconnected-') or (board, net) in executed:
                continue
            key = f'{board}:{net.lstrip("/")}'
            if (board, net) in structural:
                structural_only.append(key)
            if key not in waivers and key not in analog:
                gaps.append(key)
                group = family(board, net.lstrip('/'))
                families.setdefault(group, []).append(key)
    return {
        'reviewed_waivers': dict(sorted(waivers.items())),
        'analog_waivers': dict(sorted(analog.items())),
        'unmodeled_nets': sorted(gaps),
        'structural_only_nets': sorted(structural_only),
        'coverage_families': {k: sorted(v) for k, v in sorted(families.items())},
        'coverage_complete': not gaps,
    }

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
    if re.search(r'LED|^GPO|^ILIM$', name):
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
    'TPS2553DBVR-1': {'IN', 'OUT', 'ILIM', 'GND'},
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
           'BOOST_SW': ('POW-007',),
           # the TPS2553-1 current-limit resistor (R10, 45.3k to GND): IC-005's limit and inrush checks
           'ILIM': ('POW-006', 'IC-005')},
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


# Nets at the edge of the machine, or whose far side the emulator does not
# model. They are NOT static or analog: each is a waiver David decided on
# (2026-09-29; BOUNDARY_DECISIONS below, per group), every net listed by name.
# Pin-exact like the others: any change to the pins on the net (a part
# swapped, a pin added) drops the waiver and the net is a gap again.
#   test_access   a bring-up pad for a tool outside the machine (a debug probe,
#                 a serial adapter, a jumper): nothing in the machine drives or reads it.
#   card_control  sysctl's card reset / boot-select lines. sysctl's side runs (the TCA9555
#                 model holds the outputs; power.c drives them); the card's reaction does
#                 not: the emulator starts an RP2040 card from its ELF and has no whole-chip
#                 reset (RP2040::reset() resets the cores only), and the ESP32-C3 in QEMU
#                 has no EN/boot-strap input.
#   esp_pins      ESP32-C3 pins the QEMU machine does not export (LED GPIOs and the ROM
#                 bootloader's UART0 on the slot's SWD contacts).
#   unused_by_fw  pins no firmware drives or reads and no model attaches.
#   passive_loop  a presence loop only a pull-up and a test point read.
#   external_header  a header for a device that is not part of the machine (AUX SPI, J4): the
#                 chipset drives select 6 (SPI_nCS[6], output bit 8) but nothing is plugged in
#                 and no firmware selects device 6.
def _boundary_specs():
    specs = {}

    def add(board, net, kind, pins, why):
        specs[f'{board}:{net}'] = (kind, pins.split(), why)

    rp_cards = ('gpu', 'io', 'storage', 'eink')
    for board in rp_cards:
        add(board, 'BOOTSEL', 'test_access', 'R1.2 TP1.1',
            'BOOTSEL pad (1k to QSPI_SS): shorted to GND by hand at power-up for the USB boot ROM')
        add(board, 'RUN', 'card_control', 'J1.B9 R3.2 TP4.1 U1.26',
            'CARD_RST_n from sysctl into the RP2040 RUN pin: no whole-chip reset in the emulator')
        uart = 'TP5.1 U1.2' if board == 'gpu' else 'TP5.1 U1.27'
        if board in ('io', 'storage'):
            add(board, 'UART_TX', 'test_access', uart,
                "the firmware's stdio UART (captured at the chip by the emulator); "
                'read by a serial adapter on the pad, which is outside the machine')
        else:
            add(board, 'UART_TX', 'unused_by_fw', uart, 'the firmware does not use the UART')
    add('system', 'BOOTSEL', 'test_access', 'R6.2 TP4.1', 'BOOTSEL pad, as on the slot cards')
    add('system', 'RUN', 'test_access', 'TP3.1 U1.26',
        'RUN pad on the system card (nothing else drives it): a reset jumper or probe')
    add('system', 'SWCLK', 'test_access', 'TP1.1 U1.24', 'SWD pad for a debug probe')
    add('system', 'SWDIO', 'test_access', 'TP2.1 U1.25', 'SWD pad for a debug probe')
    add('system', 'PRSNT', 'passive_loop', 'J2.A1 J2.B32',
        'PRSNT1_n (GND on the main board) to PRSNT2_n: the presence loop')
    add('main', 'SYS_PRSNT2_n', 'passive_loop', 'J3.64 R104.2 TP41.1',
        'pull-up and test point only: no IC reads the system card presence')
    add('main', 'SPI_nCS6_SRC', 'external_header', 'R43.1 U7.74',
        'chipset SPI select 6 (33 ohm R43) to the AUX SPI header J4: no device, no firmware use')
    add('main', 'AUX_CS_n', 'external_header', 'J4.8 R43.2', 'the AUX SPI header J4 pin 8, nothing plugged in')
    for slot in range(1, 7):
        base, pin_rst, pin_prog = (slot + 1) * 100, 3 + slot, 12 + slot
        connector = f'J{10 + slot}'
        add('main', f'SLOT{slot}_RST_n', 'card_control',
            f'{connector}.B9 R{base + 4}.2 U13.{pin_rst}',
            'sysctl CARD_RST_n (TCA9555 U13 output, hold/release in power.c): the card '
            'side is card_control above')
        add('main', f'SLOT{slot}_PROG_n', 'card_control',
            f'{connector}.A18 R{base + 5}.2 U13.{pin_prog}',
            'sysctl PROG_n (U13): only the Wi-Fi card wires A18 (ESP32 IO9); it is NC on the '
            'RP2040 cards')
    add('wifi', 'EN', 'card_control', 'C5.1 J1.B9 R1.2 U1.8',
        'CARD_RST_n into the ESP32-C3 EN: QEMU has no EN input')
    add('wifi', 'BOOT', 'card_control', 'J1.A18 R2.2 U1.23',
        'PROG_n into the ESP32-C3 IO9 (download-mode strap): not exported by QEMU')
    for net, pins in (('LED_LINK', 'R6.1 U1.18'), ('LED_TX', 'R7.1 U1.12'), ('LED_RX', 'R8.1 U1.13'),
                      ('LED_LINK_A', 'D2.2 R6.2'), ('LED_TX_A', 'D3.2 R7.2'), ('LED_RX_A', 'D4.2 R8.2')):
        add('wifi', net, 'esp_pins', pins, 'ESP32-C3 GPIO indicator LED: QEMU does not export GPIO levels')
    add('wifi', 'USB_DN', 'unused_by_fw', 'TP1.1 U1.26', 'native USB pad: test point only, unused by the firmware')
    add('wifi', 'USB_DP', 'unused_by_fw', 'TP2.1 U1.27', 'native USB pad: test point only, unused by the firmware')
    add('wifi', 'U0RXD', 'esp_pins', 'J1.B6 U1.30',
        "ROM-bootloader UART0 on the slot's SWCLK contact (cupc8.py card flash --esp): "
        'the prog port reaches no ESP UART in the emulator')
    add('wifi', 'U0TXD', 'esp_pins', 'J1.B7 U1.31', 'as U0RXD, on the SWDIO contact')
    for net, pins, why in (
            ('DDC_SCL', 'J2.15 Q1.3 R23.2', "HDMI DDC clock (EDID): no monitor's I2C is modelled"),
            ('DDC_SDA', 'J2.16 Q2.3 R25.2', 'HDMI DDC data (EDID)'),
            ('HDMI_SCL', 'Q1.2 R22.2 U1.30', 'GPIO19 behind the DDC level shifter'),
            ('HDMI_SDA', 'Q2.2 R24.2 U1.31', 'GPIO20 behind the DDC level shifter'),
            ('HDMI_HPD', 'R20.2 R21.1 U1.29', 'GPIO18 behind the hot-plug divider'),
            ('HPD_5V', 'J2.19 R20.1', 'hot-plug pin from the sink')):
        add('gpu', net, 'unused_by_fw', pins, why + '; the GPU firmware never touches GPIO18-20')
    return specs


BOUNDARY = _boundary_specs()

# David's decision per group (2026-09-29): all four waived, no new emulator or
# QEMU modelling. `verified_by` names the first-article / bring-up rows that
# close what the emulator cannot.
BOUNDARY_DECISIONS = {
    'test_access': {
        'decision': 'accepted by David 2026-09-29: waived as test access',
        'reason': 'bring-up pads for a tool outside the machine (a probe, a serial adapter, '
                  'a jumper): nothing in the machine drives or reads them',
        'verified_by': []},
    'passive_loop': {
        'decision': 'accepted by David 2026-09-29: waived as test access',
        'reason': 'a presence loop that only a pull-up and a test point read',
        'verified_by': []},
    'card_control': {
        'decision': 'accepted by David 2026-09-29: waived; verified at first article',
        'reason': "sysctl's reset and boot-select lines run up to the expander; the card's reaction "
                  '(RP2040 RUN, ESP32 EN and IO9) needs a whole-chip reset in the emulator and an '
                  'EN hook in QEMU, which were declined',
        'verified_by': ['MB-106', 'WC-101']},
    'unused_by_fw': {
        'decision': 'accepted by David 2026-09-29: waived; GPU DDC/HPD verified at first article',
        'reason': 'no firmware drives or reads these pins and no emulator model attaches; the GPU '
                  "card's DDC/EDID and hot-plug path is measured on a real monitor",
        'verified_by': ['GC-105']},
    'external_header': {
        'decision': 'accepted by David 2026-09-29: waived; the planned model is dropped',
        'reason': 'the AUX SPI header J4 has no device in the machine and no firmware selects '
                  'device 6',
        'verified_by': []},
    'esp_pins': {
        'decision': 'accepted by David 2026-09-29: waived; verified at first article',
        'reason': 'QEMU exports no ESP32-C3 GPIO levels and the prog port reaches no ESP UART',
        'verified_by': ['WC-101']},
}


def reviewed_boundary_waivers(circuits, implemented=None):
    """Pin-exact waivers for the nets in BOUNDARY (see the note above it)."""
    waivers = {}
    for key, (kind, pins, why) in BOUNDARY.items():
        board, name = key.split(':', 1)
        circuit = circuits.get(board)
        nodes = circuit.nets.get(f'/{name}') if circuit is not None else None
        if not nodes or sorted(f'{r}.{p}' for r, p in nodes) != sorted(pins):
            continue
        decision = BOUNDARY_DECISIONS[kind]
        checks = [_PINOUT_ROWS[board]]
        if implemented is not None and not set(checks) <= implemented:
            continue
        waivers[key] = {
            'family': 'boundary_' + kind,
            'reason': why,
            'checks': checks,
            'pins': [f'{r}.{p}' for r, p in nodes],
            'status': decision['decision'],
            'group_reason': decision['reason'],
            'verified_by': list(decision['verified_by']),
        }
    return waivers


def audit(circuits, executed, structural, implemented=None):
    waivers = reviewed_reserved_waivers(circuits)
    analog = reviewed_analog_waivers(circuits, implemented)
    boundary = reviewed_boundary_waivers(circuits, implemented)
    gaps, structural_only, families = [], [], {}
    for board, circuit in circuits.items():
        for net in circuit.nets:
            if net.startswith('unconnected-') or (board, net) in executed:
                continue
            key = f'{board}:{net.lstrip("/")}'
            if (board, net) in structural:
                structural_only.append(key)
            if key not in waivers and key not in analog and key not in boundary:
                gaps.append(key)
                group = family(board, net.lstrip('/'))
                families.setdefault(group, []).append(key)
    return {
        'reviewed_waivers': dict(sorted(waivers.items())),
        'analog_waivers': dict(sorted(analog.items())),
        'boundary_waivers': dict(sorted(boundary.items())),
        'unmodeled_nets': sorted(gaps),
        'structural_only_nets': sorted(structural_only),
        'coverage_families': {k: sorted(v) for k, v in sorted(families.items())},
        'coverage_complete': not gaps,
    }

"""Conservative E2E net coverage accounting for all eight KiCad netlists.

Only a pin-exact, electrically unused reserved contact may be waived here.
Classification is a work queue, not evidence that a circuit was simulated.
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


def audit(circuits, executed, structural):
    waivers = reviewed_reserved_waivers(circuits)
    gaps, structural_only, families = [], [], {}
    for board, circuit in circuits.items():
        for net in circuit.nets:
            if net.startswith('unconnected-') or (board, net) in executed:
                continue
            key = f'{board}:{net.lstrip("/")}'
            if (board, net) in structural:
                structural_only.append(key)
            if key not in waivers:
                gaps.append(key)
                group = family(board, net.lstrip('/'))
                families.setdefault(group, []).append(key)
    return {
        'reviewed_waivers': dict(sorted(waivers.items())),
        'unmodeled_nets': sorted(gaps),
        'structural_only_nets': sorted(structural_only),
        'coverage_families': {k: sorted(v) for k, v in sorted(families.items())},
        'coverage_complete': not gaps,
    }

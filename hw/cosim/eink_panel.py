"""Routed digital-continuity prerequisite for the e-ink panel header.

The native panel attachment is gated by actual source-to-header copper,
including the 3V3 -> F1 -> EPD_VCC feed. No voltage, PTC trip, return,
signal-quality or panel-power model is inferred from continuity.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'hw/si')]
from gen_top import path  # noqa: E402
from ibis_bus import routed_distances  # noqa: E402


# KiCad package pads for GPIO9..15 and the nine-pin e-paper header.
SIGNALS = {
    'EPD_DIN': ('14', '3', 'R10', ('U5', '2')),
    'EPD_CLK': ('13', '4', 'R11', ('U5', '4')),
    'EPD_nCS': ('12', '5', 'R12', ('U5', '5')),
    'EPD_DC': ('15', '6', 'R13', ('U6', '1')),
    'EPD_nRST': ('16', '7', 'R14', ('U6', '2')),
    'EPD_BUSY': ('17', '8', 'R15', ('U6', '4')),
    'EPD_PWR': ('18', '9', 'R16', ('U6', '5')),
}
VCC_NODES = {('F1', '2'), ('J2', '1'), ('U5', '1'),
             ('C20', '1'), ('C21', '1')}


def routes(circuit, board):
    """Return (functional panel continuity, measured copper legs, gaps)."""
    if circuit.components.get('J2') != ('EPD', ('jlc', 'PZ254R-11-09P')) or \
            circuit.components.get('F1') != ('100mA', ('Device', 'Polyfuse')):
        raise ValueError('e-ink panel: wrong fitted header or supply PTC')
    if set(circuit.nets.get('/EPD_VCC', ())) != VCC_NODES or \
            circuit.net('F1', '1') != '/3V3' or circuit.net('J2', '2') != '/GND' or \
            circuit.net('J1', 'A4') != '/3V3' or circuit.net('J1', 'B4') != '/3V3':
        raise ValueError('e-ink panel: 3V3 → F1 → EPD_VCC/header source changed')
    for ref in ('U5', 'U6'):
        if circuit.components.get(ref) != ('TPD4E05U06DQAR',
                                           ('Power_Protection', 'TPD4E05U06DQA')) or \
                circuit.net(ref, '3') != '/GND' or circuit.net(ref, '8') != '/GND':
            raise ValueError(f'e-ink panel: {ref} TVS or GND source changed')

    pcb = Path(board) if board is not None else None
    rows, gaps = [], []
    essential = []

    def leg(net, first, target, kind):
        path(circuit, first, target)
        length = None
        if pcb is not None and pcb.is_file():
            length = routed_distances(pcb, net, first, [target])[
                f'{target[0]}.{target[1]}']
        rows.append({'net': net.lstrip('/'), 'from': f'{first[0]}.{first[1]}',
                     'to': f'{target[0]}.{target[1]}', 'function': kind,
                     'route_mm': length})
        if length is None:
            gaps.append(f'{net.lstrip("/")}:{first[0]}.{first[1]}→{target[0]}.{target[1]}')
        return length is not None

    supply_paths = [leg('/3V3', ('J1', contact), ('F1', '1'), 'supply')
                    for contact in ('A4', 'B4')]
    essential.append(any(supply_paths))
    essential.append(leg('/EPD_VCC', ('F1', '2'), ('J2', '1'), 'panel-power'))
    for target in (('U5', '1'), ('C20', '1'), ('C21', '1')):
        leg('/EPD_VCC', ('F1', '2'), target, 'power-branch')

    for signal, (gpio, contact, resistor, esd) in SIGNALS.items():
        a, b = '/' + signal, '/' + signal + '_J'
        source, series_in = ('U1', gpio), (resistor, '1')
        series_out, header = (resistor, '2'), ('J2', contact)
        if circuit.components.get(resistor) != ('33R', ('Device', 'R')) or \
                set(circuit.nets.get(a, ())) != {source, series_in} or \
                set(circuit.nets.get(b, ())) != {series_out, header, esd} or \
                path(circuit, source, header, '33R') != resistor:
            raise ValueError(f'e-ink panel {signal}: MCU, 33R or header source changed')
        essential.append(leg(a, source, series_in, 'source'))
        essential.append(leg(b, series_out, header, 'header'))
        leg(b, series_out, esd, 'tvs-branch')
    return all(essential), rows, gaps

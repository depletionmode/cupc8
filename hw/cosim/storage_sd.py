"""Bind the storage card's microSD digital socket to its routed copper.

The returned flag is suitable for the native machine's storage_sd_socket
input. It covers seven direct signal paths and their fitted pull/ESD branches;
rail integrity, signal quality and the rest of the card remain separate gates.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
sys.path.insert(0, str(ROOT / 'hw/si'))
from gen_top import path  # noqa: E402
from ibis_bus import routed_distances  # noqa: E402


# RP2040 GPIOs and TF-01A contacts are fixed by hw/boards/storage.py.
SIGNALS = {
    'SD_DAT2': ('30', '1', ('RN1', '4'), ('U6', '2')),
    'SD_nCS': ('16', '2', ('R20', '2'), ('U5', '5')),
    'SD_MOSI': ('18', '3', ('RN1', '1'), ('U5', '2')),
    'SD_SCK': ('17', '5', None, ('U5', '1')),
    'SD_MISO': ('15', '7', ('RN1', '2'), ('U5', '4')),
    'SD_DAT1': ('29', '8', ('RN1', '3'), ('U6', '1')),
    'SD_nDETECT': ('28', '9', ('R21', '2'), ('U6', '4')),
}
PACK_RETURN = {'1': '8', '2': '7', '3': '6', '4': '5'}


def routes(circuit, board):
    """Return (functional socket connected, measured legs, missing legs).

    Missing pull or ESD copper makes the complete board route fail without
    pretending that it disconnects an otherwise intact SD data path.
    """
    rows, missing = [], []
    socket_connected = True
    pcb = Path(board) if board is not None else None
    for signal, (gpio, contact, pull, esd) in SIGNALS.items():
        net = '/' + signal
        source, socket = ('U1', gpio), ('J2', contact)
        if circuit.net(*source) != net or circuit.net(*socket) != net:
            raise ValueError(f'storage {signal}: RP2040 or TF-01A pad swapped')
        if circuit.components.get('J2') != ('microSD', ('jlc', 'TF-01A')):
            raise ValueError('storage SD: wrong socket source')
        if circuit.components.get(esd[0]) != ('TPD4E05U06DQAR',
                                              ('Power_Protection', 'TPD4E05U06DQA')):
            raise ValueError(f'storage {signal}: wrong ESD source')
        if circuit.net(esd[0], '3') != '/GND' or circuit.net(esd[0], '8') != '/GND':
            raise ValueError(f'storage {signal}: ESD ground source missing')
        targets = [socket, esd]
        if pull:
            supply_pin = PACK_RETURN[pull[1]] if pull[0] == 'RN1' else '1'
            if circuit.net(*pull) != net or circuit.net(pull[0], supply_pin) != '/3V3':
                raise ValueError(f'storage {signal}: pull-up not tied to 3V3')
            expected = '10k'
            if circuit.components.get(pull[0], (None,))[0] != expected:
                raise ValueError(f'storage {signal}: wrong pull-up value')
            targets.append(pull)
        expected = {source, *targets}
        if set(circuit.nets.get(net, ())) != expected:
            raise ValueError(f'storage {signal}: unexpected source net attachment')
        for target in targets:
            path(circuit, source, target)
        lengths = ({key: None for key in (f'{ref}.{pin}' for ref, pin in targets)}
                   if pcb is None or not pcb.is_file() else
                   routed_distances(pcb, net, source, targets))
        for target in targets:
            ref, pin = target
            length = lengths[f'{ref}.{pin}']
            rows.append({'net': signal, 'from': f'U1.{gpio}', 'to': f'{ref}.{pin}',
                         'route_mm': length, 'function': ('socket' if target == socket else
                                                        'esd' if target == esd else 'pull')})
            if length is None:
                missing.append(f'{signal}:{ref}.{pin}')
                if target == socket:
                    socket_connected = False
    return socket_connected, rows, missing

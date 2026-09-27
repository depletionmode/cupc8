#!/usr/bin/env python3
"""Fetch and verify Lattice's iCE40 LP/HX IBIS model for local PCB analysis.

The vendor grants use for PCB design but prohibits duplication. Keep the IBS
under ignored build/, never in the repository. This supplies a source model;
it does not itself simulate a bus or satisfy verification row 4.6.
"""
import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

URL = 'https://www.latticesemi.com/view_document?document_id=48057'
SHA256 = '8acc5bf6bc90d6956b80d5e688b7bc47a48386b127533702c8d5f328a57390c9'


def verify(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise ValueError(f'Lattice IBIS changed: SHA-256 {digest}, expected {SHA256}')
    text = data.decode('ascii')
    required = ('[File Rev]       2.5', 'iCE40HK4K', '| TQ144',
                'L_pkg 10.53nH', 'C_pkg 1.207pF', '[Model]          lvc330io',
                '[Model]          lvc330_b3io', '[Rising Waveform]', '[Falling Waveform]')
    if any(item not in text for item in required):
        raise ValueError('Lattice IBIS lacks the expected iCE40HX4K models and waveforms')
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('build/hw/si/FPGA-MD-02034-2-5-iCE40-IO.ibs'))
    args = parser.parse_args()
    output = args.out
    if output.is_file():
        data = output.read_bytes()
        try:
            digest = verify(data)
        except ValueError:
            output.unlink()  # a stale/corrupt cache must never be treated as the vendor model
        else:
            print(f'Lattice iCE40 IBIS cached and verified: {output} ({digest})')
            return
    with urlopen(URL, timeout=30) as response:
        data = response.read()
    digest = verify(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f'Lattice iCE40 IBIS downloaded and verified: {output} ({digest})')


if __name__ == '__main__':
    main()

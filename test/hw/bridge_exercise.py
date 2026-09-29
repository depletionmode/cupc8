#!/usr/bin/env python3
"""BRG-001/002 through the co-simulated machine's system card (MB-052).

Run by test/hw/bridge_probe.mjs against the native machine's sysctl TCP
port. The same checks as the GHDL bridge rows, on the netlist-generated
board: SRAM writes and reads of every length 1-256 at random addresses
(with the CPU running, with the CPU held, and with the CPU card's FPGA
unconfigured, i.e. no CPU on the bus); the ROM's JEDEC ID; a full-chip
erase read back as $FF over all 512 KB; programs, with DQ6/DQ7 polling in
the firmware, that land on every ROM address line and every data bit, and
read back; and the kernel image restored for the boot check that follows.
The full 512 KB program of BRG-002 is not repeated here (about 50 s of
machine time at the bridge's 1 MHz); the per-line programs reach every
routed ROM address and data line instead.
"""
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import cupc8  # noqa: E402


def ram_pass(sc, rng, label, lo, hi):
    for n in range(1, 257):
        addr = rng.randrange(lo, hi - n)
        data = bytes(rng.randrange(256) for _ in range(n))
        sc.ram_write(addr, data)
        back = sc.ram_read(addr, n)
        if back != data:
            raise SystemExit(f'FAIL: {label}: RAM ${addr:05x} length {n} read back differs')
    print(f'{label}: RAM write/read of every length 1-256 at random addresses in '
          f'${lo:05x}-${hi - 1:05x}', flush=True)


def main():
    port, rom_image = sys.argv[1], Path(sys.argv[2])
    rng = random.Random(52)
    sc = cupc8.Sysctl(port)
    try:
        sc.resync()
        # the CPU running: banks the booted kernel leaves alone
        ram_pass(sc, rng, 'BRG-001 CPU running', 0x40000, 0x80000)
        sc.cpu_ctl(0x40)                       # hold the CPU
        ram_pass(sc, rng, 'BRG-001 CPU held', 0, 0x80000)
        sc.cpu_ctl(0x00)
        sc.fpga_hold(1)                        # the CPU card's FPGA unconfigured: no CPU on the bus
        ram_pass(sc, rng, 'BRG-001 no CPU (CPU card FPGA held)', 0, 0x80000)
        sc.fpga_boot(1)

        mfr, dev = sc.rom_id()
        if (mfr, dev) != (0xBF, 0xD7):
            raise SystemExit(f'FAIL: BRG-002 ROM ID {mfr:02x} {dev:02x}, want BF D7 (SST39VF040)')
        sc.rom_erase(0, 0)
        erased = sc.rom_read(0, 0x80000)
        if erased != b'\xff' * 0x80000:
            first = next(i for i, b in enumerate(erased) if b != 0xFF)
            raise SystemExit(f'FAIL: BRG-002 chip erase left ${first:05x} = {erased[first]:02x}')
        print('BRG-002: JEDEC ID BF D7; chip erase reads $FF over all 512 KB', flush=True)
        # one byte at 0 and at each single-address-line address (every ROM
        # address line high alone), then every data bit both ways at the top
        spots = [0] + [1 << bit for bit in range(19)]
        values = {addr: (0x5A + 37 * i) & 0xFF or 0x01 for i, addr in enumerate(spots)}
        pattern = bytes([0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80,
                         0xFE, 0xFD, 0xFB, 0xF7, 0xEF, 0xDF, 0xBF, 0x7F])
        for addr, value in values.items():
            sc.rom_program(addr, bytes([value]))
        sc.rom_program(0x7FF00, pattern)
        for addr, value in values.items():
            back = sc.rom_read(addr, 1)[0]
            if back != value:
                raise SystemExit(f'FAIL: BRG-002 ROM ${addr:05x} read back {back:02x}, want {value:02x}')
        if sc.rom_read(0x7FF00, 16) != pattern:
            raise SystemExit('FAIL: BRG-002 data-bit pattern at $7FF00 did not read back')
        print(f'BRG-002: programs at {len(spots)} addresses (0 and each ROM address line alone) '
              'and a walking data-bit pattern read back', flush=True)
        image = rom_image.read_bytes()
        end = len(image.rstrip(b'\xff'))
        sc.rom_erase(0, 0)
        sc.rom_program(0, image[:end])
        if sc.rom_read(0, end) != image[:end]:
            raise SystemExit('FAIL: kernel image restore did not verify')
        sc.machine_reset()
        print(f'kernel image ({end} bytes) restored and the machine reset', flush=True)
    except cupc8.SysctlError as error:
        raise SystemExit(f'FAIL: {error}')
    finally:
        sc.close()
    print('BRIDGE OK')


if __name__ == '__main__':
    os.environ.setdefault('CUPC8_TIMEOUT_SCALE', '300')
    main()

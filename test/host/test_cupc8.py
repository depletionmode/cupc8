#!/usr/bin/env python3
"""HOST-002: every cupc8.py command, run as a user runs it, against sysctl_sim
(the real sysctl core on the model machine, on a pseudo-terminal). What
landed where is checked in the models' own memory (sysctl_sim --dump), not
only through cupc8.py's read-back.

    python3 test/host/test_cupc8.py        (make -C fw sysctl_sim first)
"""

import os
import random
import signal
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SIM = os.path.join(ROOT, "build", "fw", "sysctl_sim")
CUPC8 = [sys.executable, os.path.join(ROOT, "tools", "cupc8.py")]
sys.path.insert(0, os.path.join(ROOT, "tools"))
import cupc8  # noqa: E402

bad = checks = 0


def expect(cond, what):
    global bad, checks
    checks += 1
    if not cond:
        bad += 1
        print("FAIL", what)


class Sim:
    def __init__(self, *args):
        self.dir = tempfile.mkdtemp(prefix="sysctl_sim-")
        self.p = subprocess.Popen([SIM, "--dump", self.dir, *args], stdout=subprocess.PIPE, text=True)
        self.port = self.p.stdout.readline().strip()

    def run(self, *args, ok=True):
        r = subprocess.run(CUPC8 + ["--port", self.port, *args], capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
        if ok and r.returncode:
            expect(False, "cupc8.py %s exited %d: %s" % (" ".join(args), r.returncode, out.strip()))
        return r.returncode, out

    def stop(self):
        """Stop the sim and return what its models hold."""
        self.p.send_signal(signal.SIGTERM)
        self.p.wait(10)
        return {n: open(os.path.join(self.dir, n), "rb").read() for n in ("rom.bin", "fl0.bin", "fl1.bin", "card3.bin")}


def main():
    rnd = random.Random(8)
    tmp = tempfile.mkdtemp(prefix="cupc8-")

    def file_of(name, data):
        path = os.path.join(tmp, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    # ------------------------------------------------------------ a machine that runs
    sim = Sim("--flashed", "--cc", "900")
    _, out = sim.run("ping")
    expect(out.startswith("CUPC8 sysctl"), "ping: %r" % out)
    _, out = sim.run("status")
    expect("chipset running" in out and "CPU card present" in out and "Type-C 1.5 A" in out, "status: %r" % out)
    _, out = sim.run("power")
    expect(out.startswith("Type-C 1.5 A (CC 900 mV)"), "power: %r" % out)

    # the ROM through the chipset's bridge
    _, out = sim.run("rom", "id")
    expect("manufacturer $bf, device $d7" in out, "rom id (SST39VF040): %r" % out)
    rom = bytes(rnd.randrange(256) for _ in range(20000))
    _, out = sim.run("rom", "write", file_of("rom.bin", rom), "--addr", "0x1000")
    expect("wrote and verified 20000 bytes at $01000" in out, "rom write: %r" % out)
    sim.run("rom", "read", "0x1000", "20000", "-o", os.path.join(tmp, "rom-back.bin"))
    expect(open(os.path.join(tmp, "rom-back.bin"), "rb").read() == rom, "rom read gives back what was written")

    # RAM through the bridge
    ram = bytes(rnd.randrange(256) for _ in range(5000))
    sim.run("ram", "write", "0x4000", file_of("ram.bin", ram))
    sim.run("ram", "read", "0x4000", "5000", "-o", os.path.join(tmp, "ram-back.bin"))
    expect(open(os.path.join(tmp, "ram-back.bin"), "rb").read() == ram, "ram write then read")
    _, out = sim.run("ram", "read", "0xfff8", "16")
    expect(out.count("\n") == 1, "ram read wrapping past $ffff: %r" % out)

    # the CPU through the bridge
    for op in ("stop", "step", "cycle", "run", "hold", "release"):
        rc, out = sim.run("cpu", op)
        expect(rc == 0 and out.startswith("bridge status $"), "cpu %s: %r" % (op, out))
    rc, _ = sim.run("trace")
    expect(rc == 0, "trace")

    # FPGA flash: refused until held; a real flash cycle; an image that won't configure
    rc, out = sim.run("flash", "id", "cpu", ok=False)
    expect(rc == 1 and "not held" in out, "flash id refused while the FPGA owns its flash: %r" % out)
    bit = b"\xff\x00\x00\xff\x7e\xaa\x99\x7e" + bytes(rnd.randrange(256) for _ in range(135100 - 8))
    rc, out = sim.run("fpga", "flash", "cpu", file_of("cpu.bin", bit))
    expect(rc == 0 and "configured" in out, "fpga flash cpu: %r" % out)
    rc, out = sim.run("fpga", "flash", "cpu", file_of("junk.bin", b"\x00" * 4096), ok=False)
    expect(rc == 1 and "timeout" in out, "an image that doesn't configure is reported: %r" % out)
    sim.run("fpga", "flash", "cpu", os.path.join(tmp, "cpu.bin"))
    sim.run("fpga", "hold", "chipset")
    _, out = sim.run("flash", "id", "chipset")
    expect(out.strip() == "ef4016", "flash id chipset (W25Q32): %r" % out)
    _, out = sim.run("status")
    expect("held: chipset" in out and "chipset down" in out, "status while the chipset is held: %r" % out)
    rc, out = sim.run("rom", "id", ok=False)
    expect(rc == 1 and "chipset is not running" in out, "the bridge is refused with the chipset down: %r" % out)
    sim.run("fpga", "boot", "chipset")

    # cards
    sim.run("card", "reset", "2", "--hold")
    _, out = sim.run("status")
    expect("cards held in reset: 2;" in out, "card reset --hold: %r" % out)
    sim.run("card", "reset", "2", "--release")
    _, out = sim.run("status")
    expect("cards held in reset: none" in out, "card reset --release: %r" % out)
    elf = open(os.path.join(ROOT, "build", "rp2040", "gpu.elf"), "rb").read()
    rc, out = sim.run("card", "flash", "3", os.path.join(ROOT, "build", "rp2040", "gpu.elf"))
    expect(rc == 0 and "RP2040 flashed and verified" in out, "card flash 3 gpu.elf over SWD: %r" % out)
    rc, out = sim.run("card", "flash", "4", file_of("x.bin", b"\x00" * 256), ok=False)
    expect(rc == 1 and "no SWD target" in out, "an empty slot: no SWD target, then the ESP path fails: %r" % out)
    rc, out = sim.run("card", "reset", "7", ok=False)
    expect(rc == 2, "slot numbers are 1-6")

    rc, _ = sim.run("reset")
    expect(rc == 0, "reset (SYS_nRST)")
    got = sim.stop()
    expect(got["rom.bin"][0x1000:0x1000 + len(rom)] == rom, "the ROM chip holds the image")
    expect(got["fl1.bin"][:len(bit)] == bit, "the CPU card's flash holds the bitstream")
    img = cupc8.elf_to_flash(elf)
    expect(got["card3.bin"][:len(img)] == img, "slot 3's RP2040 flash holds gpu.elf's image (%d bytes)" % len(img))

    print("HOST-002: cupc8.py against sysctl_sim, %d checks, %d failures" % (checks, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

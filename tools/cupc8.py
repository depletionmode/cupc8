#!/usr/bin/env python3
"""cupc8.py: the host side of the CUPC/8 system card (doc/hardware/sysctl.md).

    cupc8.py [--port DEV] COMMAND ...

    ping | status | power | reset
    ram read ADDR LEN [-o FILE] | ram write ADDR FILE
    rom id | rom read ADDR LEN -o FILE | rom erase [ADDR LEN] | rom write FILE [--addr A]
    cpu stop | cpu run | cpu step | cpu cycle | cpu hold | cpu release | trace
    fpga flash chipset|cpu FILE | fpga hold chipset|cpu | fpga boot chipset|cpu
    flash id chipset|cpu | flash read chipset|cpu ADDR LEN -o FILE
    card reset SLOT [--hold|--release] | card flash SLOT FILE [--esp] [--addr A]

The port is --port, or $CUPC8_PORT, or the first system card found on USB
(VID:PID 1209:C8C8). tcp:HOST:PORT reaches the system card in the
whole-machine emulator (test/emu/machine.mjs). tools/../build/fw/sysctl_sim serves a pseudo-terminal
that stands in for the card (HOST-002, SYS-004). Slots are numbered 1-6 on
the command line, as on the board; the protocol numbers them 0-5.
"""

import argparse
import glob
import os
import select
import socket
import struct
import subprocess
import sys
import termios
import threading
import time
import tty

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAGIC = 0xC8
STATUS = {0: "OK", 1: "bad CRC", 2: "unknown command", 3: "bad length or argument", 4: "timeout",
          5: "verify failed", 6: "that FPGA is not held (fpga hold first)", 7: "the chipset is not running"}
TARGET = {"chipset": 0, "cpu": 1}
CLASSES = {0: "unknown (no CC)", 1: "default USB (500/900 mA)", 2: "Type-C 1.5 A", 3: "Type-C 3.0 A"}


class SysctlError(Exception):
    def __init__(self, status, data=b""):
        self.status, self.data = status, data
        extra = " at $%06x" % (data[0] | data[1] << 8 | data[2] << 16) if status == 5 and len(data) >= 3 else ""
        super().__init__("sysctl: %s%s" % (STATUS.get(status, "status %d" % status), extra))


def crc8(data):
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def find_port():
    if os.environ.get("CUPC8_PORT"):
        return os.environ["CUPC8_PORT"]
    for dev in sorted(glob.glob("/sys/class/tty/ttyACM*")):
        usb = os.path.realpath(os.path.join(dev, "device", ".."))
        try:
            vid = open(os.path.join(usb, "idVendor")).read().strip()
            pid = open(os.path.join(usb, "idProduct")).read().strip()
        except OSError:
            continue
        if (vid, pid) == ("1209", "c8c8"):
            return "/dev/" + os.path.basename(dev)
    sys.exit("cupc8.py: no system card found (plug it in, or use --port)")


class Sysctl:
    """The USB protocol: one request, one reply."""

    def __init__(self, port, timeout=10.0):
        if port.startswith("tcp:"):
            # the whole-machine emulator's system card (test/emu/machine.mjs)
            host, _, p = port[4:].rpartition(":")
            self.sock = socket.create_connection((host or "127.0.0.1", int(p)))
            self.fd = self.sock.fileno()
        else:
            self.sock = None
            self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
        if os.isatty(self.fd):
            tty.setraw(self.fd)
            attrs = termios.tcgetattr(self.fd)
            attrs[2] |= termios.CLOCAL
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        self.timeout = timeout
        self.buf = b""

    def close(self):
        if self.sock:
            self.sock.close()
        else:
            os.close(self.fd)

    def _read(self, n, deadline):
        while len(self.buf) < n:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.fd], [], [], left)[0]:
                raise TimeoutError("cupc8.py: no reply from the system card")
            self.buf += os.read(self.fd, 65536)
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def request(self, cmd, payload=b"", timeout=None):
        payload = bytes(payload)
        body = bytes([cmd]) + struct.pack("<H", len(payload)) + payload
        os.write(self.fd, bytes([MAGIC]) + body + bytes([crc8(body)]))
        # CUPC8_TIMEOUT_SCALE: the whole-machine emulator runs slower than real time
        scale = float(os.environ.get("CUPC8_TIMEOUT_SCALE", "1"))
        deadline = time.monotonic() + (timeout or self.timeout) * scale
        while self._read(1, deadline)[0] != MAGIC:
            pass
        head = self._read(3, deadline)
        n = head[1] | head[2] << 8
        rest = self._read(n + 1, deadline)
        if crc8(head + rest[:n]) != rest[n]:
            raise SysctlError(1)
        if head[0]:
            raise SysctlError(head[0], rest[:n])
        return rest[:n]

    # ---------------------------------------------------------------- commands
    def ping(self):
        return self.request(0x00).decode()

    def status(self):
        d = self.request(0x01)
        return {"bridge": d[0], "gpo": d[1], "cdone": d[2], "held": d[3], "power_class": d[4],
                "cc_mv": d[5] | d[6] << 8, "v1v2_mv": d[7] | d[8] << 8, "reset_slots": d[9],
                "cpu_card": bool(d[10])}

    def ram_read(self, addr, n):
        out = b""
        while n:
            k = min(n, 4096)
            out += self.request(0x10, struct.pack("<HH", addr, k))
            addr, n = (addr + k) & 0xFFFF, n - k
        return out

    def ram_write(self, addr, data):
        for i in range(0, len(data), 4000):
            self.request(0x11, struct.pack("<H", (addr + i) & 0xFFFF) + data[i:i + 4000])

    def rom_read(self, addr, n):
        out = b""
        while n:
            k = min(n, 4096)
            out += self.request(0x20, struct.pack("<I", addr)[:3] + struct.pack("<H", k))
            addr, n = addr + k, n - k
        return out

    def rom_erase(self, addr=0, n=0):
        self.request(0x21, struct.pack("<I", addr)[:3] + struct.pack("<I", n)[:3], timeout=60)

    def rom_program(self, addr, data):
        for i in range(0, len(data), 2048):
            self.request(0x22, struct.pack("<I", addr + i)[:3] + data[i:i + 2048], timeout=60)

    def rom_id(self):
        return tuple(self.request(0x23))

    def cpu_ctl(self, ctl):
        return self.request(0x30, [ctl])[0]

    def trace(self):
        d = self.request(0x31)
        count, lost = (d[0] | d[1] << 8) & 0x7FFF, bool(d[1] & 0x80)
        entries = [struct.unpack_from("<HBB", d, 2 + 4 * i) for i in range(count)]
        return entries, lost

    def machine_reset(self):
        self.request(0x32)

    def flash_read(self, t, addr, n):
        out = b""
        while n:
            k = min(n, 4096)
            out += self.request(0x40, bytes([t]) + struct.pack("<I", addr)[:3] + struct.pack("<H", k))
            addr, n = addr + k, n - k
        return out

    def flash_erase(self, t, addr, n):
        self.request(0x41, bytes([t]) + struct.pack("<I", addr)[:3] + struct.pack("<I", n)[:3], timeout=120)

    def flash_program(self, t, addr, data):
        for i in range(0, len(data), 4000 - 4000 % 256):
            chunk = data[i:i + 4000 - 4000 % 256]
            self.request(0x42, bytes([t]) + struct.pack("<I", addr + i)[:3] + chunk, timeout=30)

    def flash_id(self, t):
        return bytes(self.request(0x43, [t]))

    def fpga_hold(self, t):
        self.request(0x44, [t])

    def fpga_boot(self, t):
        self.request(0x45, [t], timeout=5)

    def power(self):
        d = self.request(0x50)
        return d[0], d[1] | d[2] << 8

    def card_reset(self, slot, hold):
        self.request(0x52, [slot, 1 if hold else 0])

    def card_prog(self, slot, low):
        self.request(0x58, [slot, 1 if low else 0])

    def prog_select(self, slot):
        self.request(0x53, [0xFF if slot is None else slot])

    def swd_seq(self, bits, nbits):
        self.request(0x54, struct.pack("<H", nbits) + bytes(bits))

    def swd_xfer(self, ops):
        """ops: [(request, data or None)]; returns [(ack, data)] up to the first failure."""
        payload = b""
        for req, data in ops:
            payload += bytes([req]) + (b"" if req & 0x04 else struct.pack("<I", data & 0xFFFFFFFF))
        d = self.request(0x55, payload)
        out, i = [], 0
        for req, _ in ops:
            if i >= len(d):
                break
            ack = d[i]
            i += 1
            v = None
            if req & 0x04 and ack == 1:
                v = struct.unpack_from("<I", d, i)[0]
                i += 4
            out.append((ack, v))
            if ack != 1:
                break
        return out

    def uart_open(self, baud):
        self.request(0x56, struct.pack("<I", baud))

    def uart_xfer(self, data=b""):
        return self.request(0x57, data)


# -------------------------------------------------------------------- SWD

class SwdError(Exception):
    pass


def swd_request(ap, read, a):
    p = ap ^ read ^ (a >> 2 & 1) ^ (a >> 3 & 1)
    return 1 | ap << 1 | read << 2 | (a >> 2 & 1) << 3 | (a >> 3 & 1) << 4 | p << 5 | 1 << 7


LINE_RESET = [0xFF] * 7 + [0x00]                                        # 56 ones, 8 idle
SWD_TO_DORMANT = [0xFF] * 7 + [0xBC, 0xE3]                              # line reset, then $E3BC
DORMANT_TO_SWD = [0xFF, 0x92, 0xF3, 0x09, 0x62, 0x95, 0x2D, 0x85, 0x86,  # 8 ones, the ADIv5.2 alert,
                  0xE9, 0xAF, 0xDD, 0xE3, 0xA2, 0x0E, 0xBC, 0x19, 0xA0, 0x01]   # 4 low, activation $1A
TARGETSEL_CORE0 = 0x01002927


class Rp2040:
    """An RP2040 card through SWD: what a debugger does to program its flash."""

    DHCSR, DCRSR, DCRDR, DEMCR, AIRCR = 0xE000EDF0, 0xE000EDF4, 0xE000EDF8, 0xE000EDFC, 0xE000ED0C
    RAM, STAGE, STACK = 0x20000000, 0x20001000, 0x20040000

    def __init__(self, sc, slot):
        self.sc, self.slot = sc, slot
        self.tar = None

    def _check(self, results, n):
        if len(results) < n or any(a != 1 for a, _ in results):
            acks = [a for a, _ in results]
            raise SwdError("SWD transfer failed (acks %s)" % acks)
        return results

    def dp_read(self, a):
        return self._check(self.sc.swd_xfer([(swd_request(0, 1, a), None)]), 1)[0][1]

    def dp_write(self, a, v):
        self._check(self.sc.swd_xfer([(swd_request(0, 0, a), v)]), 1)

    def connect(self):
        self.sc.prog_select(self.slot)
        self.sc.swd_seq(SWD_TO_DORMANT, 72)
        self.sc.swd_seq(DORMANT_TO_SWD, 148)
        self.sc.swd_seq(LINE_RESET, 64)
        self.sc.swd_xfer([(0x99, TARGETSEL_CORE0)])
        r = self.sc.swd_xfer([(swd_request(0, 1, 0), None)])
        idr = r[0][1] if r and r[0][0] == 1 else None
        if idr != 0x0BC12477:
            raise SwdError("no RP2040 answered in slot %d (DPIDR %s)" % (self.slot + 1, idr and hex(idr)))
        self.dp_write(0, 0x1E)                                  # ABORT: clear sticky errors
        self.dp_write(4, 0x50000000)                            # CDBGPWRUPREQ | CSYSPWRUPREQ
        for _ in range(100):
            if self.dp_read(4) & 0xA0000000 == 0xA0000000:
                break
        else:
            raise SwdError("the debug port did not power up")
        self.dp_write(8, 0)                                     # SELECT: AP 0, bank 0
        self._check(self.sc.swd_xfer([(swd_request(1, 0, 0), 0xA2000012)]), 1)   # CSW: word, increment
        self.tar = None
        return idr

    def _set_tar(self, addr):
        self._check(self.sc.swd_xfer([(swd_request(1, 0, 4), addr)]), 1)
        self.tar = addr

    def read32(self, addr):
        self._set_tar(addr)
        r = self._check(self.sc.swd_xfer([(swd_request(1, 1, 0xC), None), (swd_request(0, 1, 0xC), None)]), 2)
        return r[1][1]                                          # posted: RDBUFF has it

    def write32(self, addr, v):
        self._set_tar(addr)
        self._check(self.sc.swd_xfer([(swd_request(1, 0, 0xC), v)]), 1)

    def write_block(self, addr, data):
        """Words to RAM; TAR's increment wraps at 1 KB, so it is set per 1 KB."""
        data = data + b"\0" * (-len(data) % 4)
        i = 0
        while i < len(data):
            n = min(len(data) - i, 0x400 - ((addr + i) & 0x3FF))
            ops = [(swd_request(1, 0, 4), addr + i)]
            ops += [(swd_request(1, 0, 0xC), struct.unpack_from("<I", data, i + k)[0]) for k in range(0, n, 4)]
            self._check(self.sc.swd_xfer(ops), len(ops))
            i += n

    def read_block(self, addr, n):
        out = b""
        i = 0
        while i < n:
            k = min(n - i, 0x400 - ((addr + i) & 0x3FF), 512)
            ops = [(swd_request(1, 0, 4), addr + i)] + [(swd_request(1, 1, 0xC), None)] * (k // 4)
            ops.append((swd_request(0, 1, 0xC), None))
            r = self._check(self.sc.swd_xfer(ops), len(ops))
            vals = [v for _, v in r[2:]]                         # posted: each read returns the one before
            out += b"".join(struct.pack("<I", v) for v in vals)
            i += k
        return out[:n]

    def halt(self):
        self.write32(self.DHCSR, 0xA05F0003)
        if not self.read32(self.DHCSR) & 1 << 17:
            raise SwdError("the core did not halt")

    def set_reg(self, reg, v):
        self.write32(self.DCRDR, v)
        self.write32(self.DCRSR, 0x10000 | reg)

    def rom_functions(self):
        if self.read32(0x10) & 0xFFFFFF != 0x01754D:
            raise SwdError("no RP2040 boot ROM at 0 (magic %08x)" % self.read32(0x10))
        table = self.read32(0x14) & 0xFFFF
        funcs = {}
        while True:
            w = self.read32(table)
            code, addr = w & 0xFFFF, w >> 16
            if not code:
                return funcs
            funcs[chr(code & 0xFF) + chr(code >> 8)] = addr
            table += 4

    def call(self, fn, *args, timeout=10.0):
        """Run a boot ROM function; it returns to a BKPT, which halts the core."""
        for i, a in enumerate(args):
            self.set_reg(i, a)
        self.set_reg(13, self.STACK)
        self.set_reg(14, self.RAM | 1)                          # LR: the BKPT at the start of RAM
        self.set_reg(15, fn & ~1)
        self.set_reg(16, 0x01000000)                            # xPSR: Thumb
        self.write32(self.DHCSR, 0xA05F0001)                    # run
        end = time.monotonic() + timeout
        while not self.read32(self.DHCSR) & 1 << 17:
            if time.monotonic() > end:
                raise SwdError("boot ROM function at %#x did not return" % fn)

    def flash(self, image, offset=0, log=print):
        self.connect()
        self.halt()
        f = self.rom_functions()
        for need in ("IF", "EX", "RE", "RP", "FC", "CX"):
            if need not in f:
                raise SwdError("boot ROM has no %s routine" % need)
        self.write_block(self.RAM, struct.pack("<HH", 0xBE00, 0xBE00))   # BKPT #0
        size = len(image) + (-len(image) % 4096)
        log("erasing %d KB at +%#x" % (size // 1024, offset))
        self.call(f["IF"])
        self.call(f["EX"])
        self.call(f["RE"], offset, size, 1 << 16, 0xD8)
        image = image + b"\xff" * (-len(image) % 256)
        for i in range(0, len(image), 4096):
            chunk = image[i:i + 4096]
            self.write_block(self.STAGE, chunk)
            self.call(f["RP"], offset + i, self.STAGE, len(chunk))
        self.call(f["FC"])
        self.call(f["CX"])
        log("verifying")
        back = self.read_block(0x10000000 + offset, len(image))
        if back != image:
            bad = next(i for i in range(len(image)) if back[i] != image[i])
            raise SwdError("verify failed at flash +%#x" % (offset + bad))
        self.write32(self.DHCSR, 0xA05F0000)                    # debug off: run after the reset
        self.write32(self.AIRCR, 0x05FA0004)                    # SYSRESETREQ
        self.sc.prog_select(None)


def elf_to_flash(data):
    """The flash image of an RP2040 ELF: its loadable segments at 0x10000000+."""
    if data[:4] != b"\x7fELF":
        return data
    phoff, = struct.unpack_from("<I", data, 28)
    phentsize, phnum = struct.unpack_from("<HH", data, 42)
    segs = []
    for i in range(phnum):
        typ, off, _, paddr, filesz = struct.unpack_from("<IIIII", data, phoff + i * phentsize)
        if typ == 1 and filesz and 0x10000000 <= paddr < 0x11000000:
            segs.append((paddr - 0x10000000, data[off:off + filesz]))
    end = max(a + len(d) for a, d in segs)
    img = bytearray(b"\xff" * end)
    for a, d in segs:
        img[a:a + len(d)] = d
    return bytes(img)


# -------------------------------------------------------------------- ESP32

def esptool_command():
    if os.environ.get("CUPC8_ESPTOOL"):
        return os.environ["CUPC8_ESPTOOL"].split()
    sdk = os.environ.get("CUPC8_SDK", os.path.expanduser("~/.local/share/cupc8-sdk"))
    for py in sorted(glob.glob(os.path.join(sdk, "espressif/python_env/*/bin/python"))):
        return [py, "-m", "esptool"]
    return ["esptool.py"]


def uart_bridge(sc, stop):
    """A local TCP port that forwards to the card's UART through UART_XFER."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    log = open(os.environ["CUPC8_UART_LOG"], "w") if os.environ.get("CUPC8_UART_LOG") else None

    def run():
        conn, _ = srv.accept()
        conn.setblocking(False)
        while not stop.is_set():
            try:
                out = conn.recv(4000)
                if out == b"":
                    break
            except BlockingIOError:
                out = b""
            back = sc.uart_xfer(out)
            if log:
                if out:
                    log.write("> %d %s\n" % (len(out), out[:24].hex()))
                if back:
                    log.write("< %d %s\n" % (len(back), back[:24].hex()))
            if back:
                conn.sendall(back)
            if not out and not back:
                time.sleep(0.001)
        conn.close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return srv.getsockname()[1], t


def esp_flash(sc, slot, image, addr, log=print, stub=True):
    log("ESP32 in slot %d: into its ROM bootloader" % (slot + 1))
    sc.prog_select(slot)
    sc.card_prog(slot, True)
    sc.card_reset(slot, True)
    time.sleep(0.05)
    sc.card_reset(slot, False)
    time.sleep(0.1)
    sc.uart_open(115200)
    stop = threading.Event()
    port, t = uart_bridge(sc, stop)
    path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "cupc8-esp-%d.bin" % os.getpid())
    with open(path, "wb") as f:
        f.write(image)
    try:
        r = subprocess.run(esptool_command() + ["--chip", "esp32c3", "--port", "socket://127.0.0.1:%d" % port,
                                                "--baud", "115200", "--before", "no_reset", "--after", "no_reset"]
                           + ([] if stub else ["--no-stub"]) + ["write_flash", hex(addr), path])
    finally:
        stop.set()
        t.join(5)
        os.unlink(path)
        sc.uart_open(0)
        sc.card_prog(slot, False)
        sc.card_reset(slot, True)
        time.sleep(0.05)
        sc.card_reset(slot, False)
        sc.prog_select(None)
    if r.returncode:
        raise SystemExit("cupc8.py: esptool failed (%d)" % r.returncode)


# -------------------------------------------------------------------- CLI

def num(s):
    return int(s, 0)


def slot_of(s):
    n = int(s)
    if not 1 <= n <= 6:
        raise argparse.ArgumentTypeError("slots are 1-6")
    return n - 1


def write_out(data, path):
    if path:
        with open(path, "wb") as f:
            f.write(data)
    else:
        for i in range(0, len(data), 16):
            print("%06x  %s" % (i, data[i:i + 16].hex(" ")))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cupc8.py", description="the CUPC/8 system card, from the host")
    ap.add_argument("--port")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    sub.add_parser("status")
    sub.add_parser("power")
    sub.add_parser("reset")
    sub.add_parser("trace")
    ram = sub.add_parser("ram").add_subparsers(dest="op", required=True)
    p = ram.add_parser("read"); p.add_argument("addr", type=num); p.add_argument("len", type=num); p.add_argument("-o")
    p = ram.add_parser("write"); p.add_argument("addr", type=num); p.add_argument("file")
    rom = sub.add_parser("rom").add_subparsers(dest="op", required=True)
    rom.add_parser("id")
    p = rom.add_parser("read"); p.add_argument("addr", type=num); p.add_argument("len", type=num); p.add_argument("-o")
    p = rom.add_parser("erase"); p.add_argument("addr", type=num, nargs="?", default=0); p.add_argument("len", type=num, nargs="?", default=0)
    p = rom.add_parser("write"); p.add_argument("file"); p.add_argument("--addr", type=num, default=0)
    cpu = sub.add_parser("cpu"); cpu.add_argument("op", choices=["stop", "run", "step", "cycle", "hold", "release"])
    fpga = sub.add_parser("fpga").add_subparsers(dest="op", required=True)
    p = fpga.add_parser("flash"); p.add_argument("target", choices=TARGET); p.add_argument("file")
    for op in ("hold", "boot"):
        p = fpga.add_parser(op); p.add_argument("target", choices=TARGET)
    fl = sub.add_parser("flash").add_subparsers(dest="op", required=True)
    p = fl.add_parser("id"); p.add_argument("target", choices=TARGET)
    p = fl.add_parser("read"); p.add_argument("target", choices=TARGET); p.add_argument("addr", type=num); p.add_argument("len", type=num); p.add_argument("-o")
    card = sub.add_parser("card").add_subparsers(dest="op", required=True)
    p = card.add_parser("reset"); p.add_argument("slot", type=slot_of)
    g = p.add_mutually_exclusive_group(); g.add_argument("--hold", action="store_true"); g.add_argument("--release", action="store_true")
    p = card.add_parser("flash"); p.add_argument("slot", type=slot_of); p.add_argument("file")
    p.add_argument("--esp", action="store_true", help="an ESP32 card (else: tries SWD, then the ESP bootloader)")
    p.add_argument("--addr", type=num, default=0)
    p.add_argument("--no-stub", action="store_true", help="ESP32: the ROM loader alone (esptool's stub crashes in QEMU)")
    a = ap.parse_args(argv)

    sc = Sysctl(a.port or find_port())
    try:
        return run(sc, a)
    except (SysctlError, SwdError, TimeoutError) as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        sc.close()


def run(sc, a):
    c = a.cmd
    if c == "ping":
        print(sc.ping())
    elif c == "status":
        s = sc.status()
        print("chipset %s, CPU card FPGA %s; held: %s" % (
            "running" if s["cdone"] & 1 and not s["held"] & 1 else "down",
            "configured" if s["cdone"] & 2 else "not configured",
            ", ".join(n for n, t in TARGET.items() if s["held"] >> t & 1) or "none"))
        print("bridge status $%02x, GPO $%02x" % (s["bridge"], s["gpo"]))
        print("power: %s (CC %d mV), 1V2 %d mV" % (CLASSES.get(s["power_class"], "?"), s["cc_mv"], s["v1v2_mv"]))
        print("cards held in reset: %s; CPU card %s" % (
            ", ".join(str(i + 1) for i in range(6) if s["reset_slots"] >> i & 1) or "none",
            "present" if s["cpu_card"] else "missing"))
    elif c == "power":
        cls, mv = sc.power()
        print("%s (CC %d mV)" % (CLASSES.get(cls, "?"), mv))
    elif c == "reset":
        sc.machine_reset()
    elif c == "trace":
        entries, lost = sc.trace()
        for addr, data, flags in entries:
            print("%04x %s %02x%s" % (addr, "R" if flags & 1 else "W", data, " sync" if flags & 2 else ""))
        if lost:
            print("(entries were lost before these)")
    elif c == "ram":
        if a.op == "read":
            write_out(sc.ram_read(a.addr, a.len), a.o)
        else:
            sc.ram_write(a.addr, open(a.file, "rb").read())
    elif c == "rom":
        if a.op == "id":
            print("manufacturer $%02x, device $%02x" % sc.rom_id())
        elif a.op == "read":
            write_out(sc.rom_read(a.addr, a.len), a.o)
        elif a.op == "erase":
            sc.rom_erase(a.addr, a.len)
        else:
            data = open(a.file, "rb").read()
            sc.rom_erase(a.addr, len(data))
            sc.rom_program(a.addr, data)
            print("wrote and verified %d bytes at $%05x" % (len(data), a.addr))
    elif c == "cpu":
        ctl = {"stop": 0x01, "run": 0x00, "step": 0x03, "cycle": 0x05, "hold": 0x40, "release": 0x00}[a.op]
        print("bridge status $%02x" % sc.cpu_ctl(ctl))
    elif c == "fpga":
        t = TARGET[a.target]
        if a.op == "hold":
            sc.fpga_hold(t)
        elif a.op == "boot":
            sc.fpga_boot(t)
        else:
            data = open(a.file, "rb").read()
            sc.fpga_hold(t)
            sc.flash_erase(t, 0, len(data))
            sc.flash_program(t, 0, data)
            sc.fpga_boot(t)
            print("%s: %d bytes written, verified, and it configured" % (a.target, len(data)))
    elif c == "flash":
        t = TARGET[a.target]
        if a.op == "id":
            print(sc.flash_id(t).hex())
        else:
            write_out(sc.flash_read(t, a.addr, a.len), a.o)
    elif c == "card":
        if a.op == "reset":
            if a.hold:
                sc.card_reset(a.slot, True)
            elif a.release:
                sc.card_reset(a.slot, False)
            else:
                sc.card_reset(a.slot, True)
                time.sleep(0.01)
                sc.card_reset(a.slot, False)
        else:
            data = open(a.file, "rb").read()
            if not a.esp:
                try:
                    Rp2040(sc, a.slot).flash(elf_to_flash(data), a.addr)
                    print("slot %d: RP2040 flashed and verified, running" % (a.slot + 1))
                    return 0
                except SwdError as e:
                    if "no RP2040 answered" not in str(e):
                        raise
                    print("slot %d: no SWD target; trying the ESP bootloader" % (a.slot + 1))
            esp_flash(sc, a.slot, data, a.addr, stub=not a.no_stub)
            print("slot %d: ESP32 flashed" % (a.slot + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

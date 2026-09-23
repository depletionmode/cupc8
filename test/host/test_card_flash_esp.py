#!/usr/bin/env python3
"""SYS-004 (ESP32 cards): cupc8.py card flash --esp, end to end. esptool runs
through sysctl's UART tunnel (sysctl_sim: the real sysctl core) into the
ESP32-C3 ROM bootloader in Espressif's QEMU, booted in UART download mode
on a blank flash. Then QEMU boots that flash normally, and the Wi-Fi card
image that was written must answer IDENT.

    python3 test/host/test_card_flash_esp.py   (tools/fw_esp32c3.sh qemu, make -C fw sysctl_sim)
"""

import glob
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "test", "emu"))
from test_wifi_qemu import Card, free_port  # noqa: E402

SDK = os.environ.get("CUPC8_SDK", os.path.expanduser("~/.local/share/cupc8-sdk"))
QEMU = glob.glob(os.path.join(SDK, "espressif/tools/qemu-riscv32/*/qemu/bin/qemu-system-riscv32"))[0]
IMAGE = os.path.join(ROOT, "build", "esp32c3-qemu", "flash.bin")


def qemu(flash, strap, uart0, uart1=None):
    args = [QEMU, "-nographic", "-machine", "esp32c3", "-monitor", "none",
            "-global", "driver=esp32c3.gpio,property=strap_mode,value=%s" % strap,
            "-drive", "file=%s,if=mtd,format=raw" % flash, "-nic", "user,model=open_eth",
            "-serial", uart0]
    if uart1:
        args += ["-serial", uart1]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def main():
    bad = []
    tmp = tempfile.mkdtemp(prefix="espflash-")
    image = os.path.join(tmp, "image.bin")          # a snapshot: the build may change meanwhile
    with open(IMAGE, "rb") as src, open(image, "wb") as dst:
        dst.write(src.read())
    flash = os.path.join(tmp, "flash.bin")
    with open(flash, "wb") as f:
        f.write(b"\xff" * (4 << 20))                     # a blank module from JLC

    # the card in its ROM bootloader, UART0 on a TCP port
    port = free_port()
    q = qemu(flash, "0x02", "tcp:127.0.0.1:%d,server,nowait" % port)
    sim = subprocess.Popen([os.path.join(ROOT, "build", "fw", "sysctl_sim"), "--esp", "4=127.0.0.1:%d" % port],
                           stdout=subprocess.PIPE, text=True)
    pty = sim.stdout.readline().strip()
    time.sleep(1)
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "cupc8.py"), "--port", pty,
                            "card", "flash", "5", image, "--esp", "--addr", "0", "--no-stub"],
                           capture_output=True, text=True, timeout=1800)
        out = r.stdout + r.stderr
        if r.returncode or "ESP32 flashed" not in out:
            bad.append("card flash 5 --esp failed:\n" + out[-2000:])
        elif "Hash of data verified" not in out and "verified" not in out.lower():
            bad.append("esptool did not verify the write:\n" + out[-1000:])
    finally:
        sim.terminate()
        sim.wait(10)
        q.kill()
        q.wait()

    if not bad:
        written = open(flash, "rb").read()
        img = open(image, "rb").read()
        if written[:len(img)] != img:
            bad.append("the flash file doesn't hold the image")
        # boot what was written, as the card would after its reset
        frames = free_port()
        q = qemu(flash, "0x08", "file:" + os.path.join(tmp, "uart0.log"), "tcp:127.0.0.1:%d,server,nowait" % frames)
        try:
            card = Card(frames)
            ident = None
            for _ in range(100):
                ident = card.cmd([0xF0], tries=20)
                if ident:
                    break
                time.sleep(0.1)
            if not (ident and ident[0] == 0x03 and ident[3] == 0xC8):
                bad.append("the flashed card does not answer IDENT: %r" % ident)
        finally:
            q.kill()
            q.wait()

    for b in bad:
        print("FAIL", b)
    print("SYS-004 (ESP32): cupc8.py -> sysctl UART tunnel -> esptool -> QEMU ROM bootloader, %d failures" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

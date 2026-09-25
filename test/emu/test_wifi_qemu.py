#!/usr/bin/env python3
"""WIFI-003: the WIFI-002 scenarios on the real ESP-IDF image in Espressif's QEMU.

    python3 test/emu/test_wifi_qemu.py            (tools/fw_esp32c3.sh qemu first)
    CUPC8_ONLINE=1 python3 test/emu/test_wifi_qemu.py   also: TLS to a real site

The image is the card's own code (core, lwIP, esp-tls, DNS task, frame
engine) built with CONFIG_CUPC8_QEMU: QEMU has no radio and no SPI slave, so
"joining" brings up its OpenCores Ethernet (user-mode NAT: the host is
10.0.2.2) and the card frames travel over UART1 with the SPI slave's exact
preload semantics. Every server the card talks to is real and on this host.

The card's flash is a copy, so what NET_CONFIG saves in NVS stays out of the
build and survives the second boot (the power cycle) only.
"""

import glob
import os
import shutil
import socket
import struct
import ssl
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SDK = os.environ.get("CUPC8_SDK", os.path.expanduser("~/.local/share/cupc8-sdk"))
IMAGE = os.path.join(ROOT, "build", "esp32c3-qemu", "flash.bin")
HOST = [10, 0, 2, 2]

bad = checks = 0


def expect(cond, what):
    global bad, checks
    checks += 1
    if not cond:
        bad += 1
        print("FAIL", what, flush=True)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Card:
    """The CPU's side of the slot, over the QEMU build's UART transport."""

    def __init__(self, port):
        for _ in range(100):
            try:
                self.s = socket.create_connection(("127.0.0.1", port))
                break
            except OSError:
                time.sleep(0.1)
        self.s.settimeout(10)

    def frame(self, mosi):
        mosi = bytes(mosi)
        self.s.sendall(bytes([0xA5, len(mosi) & 255, len(mosi) >> 8]) + mosi)
        want, got = 3 + len(mosi), b""
        while len(got) < want:
            chunk = self.s.recv(4096)
            if not chunk:
                raise EOFError("QEMU closed the frame port")
            got += chunk
        assert got[0] == 0x5A, got[:3].hex()
        return got[3:]

    def status(self):
        return self.frame([0x00])[0]            # a NOP-sized frame: the status byte

    def cmd(self, mosi, tries=200):
        """A command, then READ frames until the response is there (slot.md)."""
        self.frame(mosi)
        for _ in range(tries):
            miso = self.frame([0xFE] + [0] * 258)
            n = miso[1]
            if n:
                return miso[2:2 + n]
            time.sleep(0.002)
        return None

    def events(self):
        r = self.cmd([0x1F])
        return [(r[1 + 2 * i], r[2 + 2 * i]) for i in range(r[0])] if r else []

    def wait_event(self, code, timeout=20):
        end = time.time() + timeout
        seen = []
        while time.time() < end:
            for ev in self.events():
                seen.append(ev)
                if ev[0] == code:
                    return ev[1], seen
            time.sleep(0.02)
        return None, seen


def string(s):
    b = s.encode()
    return [len(b)] + list(b)


def boot(qemu, flash, forwards, boot_no):
    """QEMU on `flash`, with hostfwd `forwards` [(proto, host port, card port)]: (process, Card)."""
    frames_port = free_port()
    log_path = os.path.join(ROOT, "build", "esp32c3-qemu", "uart0-%d.log" % boot_no)
    log = open(os.path.join(ROOT, "build", "esp32c3-qemu", "qemu-%d.log" % boot_no), "w")
    fwd = "".join(",hostfwd=%s:127.0.0.1:%d-:%d" % f for f in forwards)
    q = subprocess.Popen([qemu, "-nographic", "-machine", "esp32c3", "-monitor", "none",
                          "-drive", "file=%s,if=mtd,format=raw" % flash,
                          "-nic", "user,model=open_eth" + fwd,
                          "-serial", "file:" + log_path, "-serial", "tcp:127.0.0.1:%d,server,nowait" % frames_port],
                         stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    return q, Card(frames_port)


def main():
    qemu = glob.glob(os.path.join(SDK, "espressif/tools/qemu-riscv32/*/qemu/bin/qemu-system-riscv32"))
    if not qemu or not os.path.exists(IMAGE):
        sys.exit("needs tools/fetch_sdks.sh and tools/fw_esp32c3.sh qemu")
    listen_port, udp_port = free_port(), free_port()
    forwards = [("tcp", listen_port, 7000), ("udp", udp_port, UDP_CARD_PORT)]
    with tempfile.TemporaryDirectory() as d:
        flash = os.path.join(d, "flash.bin")
        shutil.copyfile(IMAGE, flash)
        q, card = boot(qemu[0], flash, forwards, 1)
        try:
            run(card, listen_port)
            run_net(card, udp_port)
        finally:
            q.kill()
            q.wait()
        # the power cycle: the same flash, so NVS kept what NET_CONFIG saved
        q, card = boot(qemu[0], flash, forwards, 2)
        try:
            run_power_cycle(card)
        finally:
            q.kill()
            q.wait()
    print("WIFI-003: real ESP-IDF image in QEMU, %d checks, %d failures" % (checks, bad))
    return 1 if bad else 0


def run(card, listen_port):
    # ------------------------------------------------------------- the card
    ident = None
    for _ in range(100):
        ident = card.cmd([0xF0], tries=20)
        if ident:
            break
        time.sleep(0.1)
    expect(ident and ident[0] == 0x03 and ident[3] == 0xC8, "IDENT says Wi-Fi card: %r" % ident)
    st = card.cmd([0x01])
    expect(st and st[0] == 0, "idle before JOIN: %r" % st)

    # ------------------------------------------------------------- the link
    card.frame([0x02])
    ev, seen = card.wait_event(0x01)
    expect(ev is not None, "SCAN raises SCAN_DONE (%r)" % seen)
    r0, r1 = card.cmd([0x03, 0]), card.cmd([0x03, 1])
    expect(r0 and bytes(r0[3:3 + r0[2]]) == b"qemu-eth", "SCAN_RESULT 0: %r" % r0)
    expect(r1 == bytes([0xFF]), "SCAN_RESULT past the end is $FF: %r" % r1)

    card.frame([0x04] + string("qemu-eth") + string("") + [0])
    ev, seen = card.wait_event(0x02, timeout=30)
    expect(ev is not None, "JOIN raises JOINED (%r)" % seen)
    st = card.cmd([0x01])
    expect(st and st[0] == 2 and list(st[2:6]) == [10, 0, 2, 15] and list(st[6:10]) == HOST
           and list(st[10:14]) == [10, 0, 2, 3], "NET_STATUS up, DHCP from QEMU: %r" % (st and list(st)))
    expect(card.status() & 0x40, "status byte LINK set")

    card.frame([0x06] + string("nonexistent.invalid"))
    ev, seen = card.wait_event(0x05)
    rr = card.cmd([0x07])
    expect(ev is not None and rr and rr[0] == 0, "RESOLVE of an invalid name fails: %r %r" % (seen, rr))

    # ------------------------------------------------------------- TCP client
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    sock = card.cmd([0x10, 0])[0]
    expect(sock == 0, "OPEN TCP gives socket 0 (%d)" % sock)
    card.frame([0x11, sock] + HOST + [port & 255, port >> 8])
    srv.settimeout(20)
    conn, _ = srv.accept()
    ev, seen = card.wait_event(0x10)
    expect(ev == sock, "CONNECT raises CONNECTED (%r)" % seen)
    card.frame([0x14, sock, 5] + list(b"hello"))
    conn.settimeout(10)
    expect(conn.recv(64) == b"hello", "SEND reaches the server")
    conn.sendall(b"PONG")
    ready = False
    for _ in range(200):
        if card.status() & (1 << sock):
            ready = True
            break
        time.sleep(0.01)
    expect(ready, "the status byte's RXREADY bit shows the reply waiting")
    ss = card.cmd([0x16, sock])
    expect(ss and ss[0] == 2 and (ss[1] | ss[2] << 8) >= 4, "SOCK_STATUS open with 4 bytes waiting: %r" % (ss and list(ss)))
    rv = card.cmd([0x15, sock, 64])
    expect(rv and bytes(rv[1:1 + rv[0]]) == b"PONG", "RECV returns the server's reply: %r" % rv)
    conn.close()
    ev, seen = card.wait_event(0x13)
    expect(ev == sock, "the server closing raises PEER_CLOSED (%r)" % seen)
    card.frame([0x17, sock])
    srv.close()

    # ------------------------------------------------------------- TCP server
    ls = card.cmd([0x10, 0])[0]
    card.frame([0x13, ls, 7000 & 255, 7000 >> 8])
    time.sleep(0.5)
    c = socket.create_connection(("127.0.0.1", listen_port), timeout=10)
    ev, seen = card.wait_event(0x12)
    expect(ev == ls, "LISTEN: a client raises ACCEPTED (%r)" % seen)
    c.sendall(b"hi card")
    got = b""
    for _ in range(200):
        rv = card.cmd([0x15, ls, 64])
        got += bytes(rv[1:1 + rv[0]]) if rv else b""
        if got == b"hi card":
            break
        time.sleep(0.01)
    expect(got == b"hi card", "the accepted connection receives: %r" % got)
    card.frame([0x14, ls, 3] + list(b"yes"))
    c.settimeout(10)
    expect(c.recv(16) == b"yes", "and sends back")
    c.close()
    card.frame([0x17, ls])

    # ------------------------------------------------------------- UDP
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(("127.0.0.1", 0))
    u.settimeout(10)
    uport = u.getsockname()[1]
    us = card.cmd([0x10, 1])[0]
    card.frame([0x18, us] + HOST + [uport & 255, uport >> 8, 5] + list(b"dgram"))
    try:
        data, _ = u.recvfrom(64)
    except socket.timeout:
        data = None
    expect(data == b"dgram", "UDP_SENDTO reaches the host: %r" % data)
    card.frame([0x17, us])

    # ------------------------------------------------------------- failures
    fs = card.cmd([0x10, 0])[0]
    card.frame([0x12, fs, 80, 0] + string("nonexistent.invalid"))
    ev, seen = card.wait_event(0x11, timeout=30)
    expect(ev == fs, "CONNECT_HOST to a name that doesn't resolve: CONN_FAILED (%r)" % seen)
    card.frame([0x17, fs])

    # TLS: a server with a certificate no CA signed must be refused, after a
    # real handshake attempt (so it is the verification that fails)
    with tempfile.TemporaryDirectory() as d:
        key, crt = os.path.join(d, "k.pem"), os.path.join(d, "c.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
                        "-out", crt, "-days", "1", "-subj", "/CN=10.0.2.2"], check=True, capture_output=True)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(crt, key)
        ts = socket.socket()
        ts.bind(("127.0.0.1", 0))
        ts.listen(1)
        tport = ts.getsockname()[1]
        hello = []

        def serve():
            try:
                ts.settimeout(30)
                conn, _ = ts.accept()
                conn.settimeout(20)
                first = conn.recv(5, socket.MSG_PEEK)
                hello.append(first)
                try:
                    ctx.wrap_socket(conn, server_side=True)
                except (ssl.SSLError, OSError):
                    pass
            except OSError:
                pass

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        tls = card.cmd([0x10, 2])[0]
        card.frame([0x11, tls] + HOST + [tport & 255, tport >> 8])
        ev, seen = card.wait_event(0x11, timeout=40)
        t.join(5)
        expect(hello and hello[0][:1] == b"\x16", "the card started a TLS handshake: %r" % hello)
        expect(ev == tls, "a self-signed server certificate is refused: CONN_FAILED (%r)" % seen)
        card.frame([0x17, tls])
        ts.close()

    # ------------------------------------------------------------- online
    if os.environ.get("CUPC8_ONLINE") == "1":
        s = card.cmd([0x10, 2])[0]
        card.frame([0x12, s, 443 & 255, 443 >> 8] + string("example.com"))
        ev, seen = card.wait_event(0x10, timeout=60)
        expect(ev == s, "online: TLS to example.com verified and CONNECTED (%r)" % seen)
        req = b"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n"
        card.frame([0x14, s, len(req)] + list(req))
        got, evs = b"", []
        end = time.time() + 30
        while time.time() < end and b"\r\n" not in got:
            evs += card.events()
            rv = card.cmd([0x15, s, 200])
            got += bytes(rv[1:1 + rv[0]]) if rv else b""
            time.sleep(0.05)
        if not got:
            print("  online: events after SEND %r, SOCK_STATUS %r" % (evs, list(card.cmd([0x16, s]) or [])))
        expect(got.startswith(b"HTTP/1.1 200"), "online: HTTPS GET answered: %r" % got[:40])
        card.frame([0x17, s])


UDP_CARD_PORT = 5300
STATIC = [10, 0, 2, 20]                     # in QEMU's 10.0.2.0/24, not DHCP's .15
MASK = [255, 255, 255, 0]


def ip_str(b):
    return ".".join(str(x) for x in b)


def net_config(card, mode, ip, mask, gw, dns, dns_port, save):
    card.frame([0x08, mode] + ip + mask + gw + dns + [dns_port & 255, dns_port >> 8, save])


def inet_checksum(b):
    if len(b) & 1:
        b += b"\0"
    total = sum(struct.unpack("!%dH" % (len(b) // 2), b))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def recvfrom(card, sock, max_len=200, timeout=10):
    """RECVFROM until a datagram comes: (ip, port, data), or None."""
    end = time.time() + timeout
    while time.time() < end:
        r = card.cmd([0x1A, sock, max_len])
        if r is None or len(r) < 7 or len(r) != 7 + r[6]:
            expect(False, "RECVFROM's RESP_LEN is 7 + n: %r" % r)
            return None
        if r[6]:
            return list(r[0:4]), r[4] | r[5] << 8, bytes(r[7:])
        time.sleep(0.02)
    return None


def tcp_round_trip(card, what):
    """A TCP client connection from the card to this host, both ways."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    srv.settimeout(20)
    port = srv.getsockname()[1]
    sock = card.cmd([0x10, 0])[0]
    card.frame([0x11, sock] + HOST + [port & 255, port >> 8])
    try:
        conn, _ = srv.accept()
        ev, seen = card.wait_event(0x10)
        card.frame([0x14, sock, 2] + list(b"hi"))
        conn.settimeout(10)
        got = conn.recv(16)
        conn.close()
    except OSError as e:
        ev, seen, got = None, [], repr(e)
    expect(ev == sock and got == b"hi", "%s: TCP to the host (%r, %r)" % (what, seen, got))
    card.frame([0x17, sock])
    srv.close()


def run_net(card, udp_port):
    # ------------------------------------------------------------- NET_CONFIG
    cfg = card.cmd([0x09])
    expect(cfg and list(cfg) == [0] + [0] * 16 + [53, 0, 0],
           "NET_CONFIG_GET at power-up: DHCP, DNS port 53, not saved: %r" % (cfg and list(cfg)))

    # ------------------------------------------------------------- UDP server
    us = card.cmd([0x10, 1])[0]
    card.frame([0x19, us, UDP_CARD_PORT & 255, UDP_CARD_PORT >> 8])
    r = card.cmd([0x1A, us, 64])
    expect(r and list(r) == [0] * 7, "RECVFROM with nothing waiting: n 0: %r" % (r and list(r)))
    a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    a.settimeout(10)
    b.settimeout(10)
    a.sendto(b"hello card", ("127.0.0.1", udp_port))
    got = recvfrom(card, us)
    expect(got and got[2] == b"hello card" and got[0] == HOST,
           "UDP_BIND + RECVFROM: a datagram through the port forward, from 10.0.2.2: %r" % (got,))
    if got:
        ip, port, _ = got
        card.frame([0x18, us] + ip + [port & 255, port >> 8, 4] + list(b"pong"))
        try:
            data, src = a.recvfrom(64)
        except socket.timeout:
            data, src = None, None
        expect(data == b"pong" and src == ("127.0.0.1", udp_port),
               "UDP_SENDTO answers the sender through the forward: %r %r" % (data, src))
    b.sendto(b"second", ("127.0.0.1", udp_port))
    got = recvfrom(card, us)
    expect(got and got[2] == b"second", "after replying to one client, the bound socket hears another: %r" % (got,))
    a.close()
    b.close()
    card.frame([0x17, us])

    # ------------------------------------------------------------- ICMP
    ic = card.cmd([0x10, 3])[0]
    expect(ic < 4, "OPEN type 3 (ICMP) gives a socket: %r" % ic)
    msg = bytearray(struct.pack("!BBHHH", 8, 0, 0, 0xC8C8, 7) + b"cupc8 ping")
    struct.pack_into("!H", msg, 2, inet_checksum(bytes(msg)))
    card.frame([0x18, ic] + HOST + [0, 0, len(msg)] + list(msg))
    got = recvfrom(card, ic)
    ok = got and got[0] == HOST and got[1] == 0 and len(got[2]) == len(msg)
    if ok:
        typ, code, _, ident, seq = struct.unpack("!BBHHH", got[2][:8])
        ok = typ == 0 and code == 0 and ident == 0xC8C8 and seq == 7 and got[2][8:] == b"cupc8 ping" \
            and inet_checksum(got[2]) == 0
    expect(ok, "ICMP echo to 10.0.2.2: the reply, id and sequence kept, IP header stripped: %r" % (got,))
    card.frame([0x17, ic])

    # ------------------------------------------------------------- DNS server
    net_config(card, 0, [0] * 4, [0] * 4, [0] * 4, HOST, 5353, 0)
    cfg = card.cmd([0x09])
    expect(cfg and list(cfg) == [0] + [0] * 12 + HOST + [5353 & 255, 5353 >> 8, 0],
           "NET_CONFIG_GET: DHCP, DNS 10.0.2.2:5353, not saved: %r" % (cfg and list(cfg)))
    st = card.cmd([0x01])
    expect(st and st[0] == 2 and list(st[2:6]) == [10, 0, 2, 15] and list(st[10:14]) == HOST,
           "NET_STATUS: DHCP's address, the configured DNS server: %r" % (st and list(st)))

    # ------------------------------------------------------------- static
    net_config(card, 1, STATIC, MASK, HOST, [10, 0, 2, 3], 53, 1)
    st = None
    for _ in range(100):
        st = card.cmd([0x01])
        if st and st[0] == 2 and list(st[2:6]) == STATIC:
            break
        time.sleep(0.05)
    expect(st and st[0] == 2 and list(st[2:6]) == STATIC and list(st[6:10]) == HOST
           and list(st[10:14]) == [10, 0, 2, 3], "static address in use at once: %r" % (st and list(st)))
    cfg = card.cmd([0x09])
    expect(cfg and list(cfg) == [1] + STATIC + MASK + HOST + [10, 0, 2, 3, 53, 0, 1],
           "NET_CONFIG_GET: static, saved: %r" % (cfg and list(cfg)))
    tcp_round_trip(card, "static address")


def run_power_cycle(card):
    ident = None
    for _ in range(100):
        ident = card.cmd([0xF0], tries=20)
        if ident:
            break
        time.sleep(0.1)
    expect(ident and ident[0] == 0x03, "IDENT after the power cycle: %r" % ident)
    cfg = card.cmd([0x09])
    expect(cfg and list(cfg) == [1] + STATIC + MASK + HOST + [10, 0, 2, 3, 53, 0, 1],
           "the saved static settings came back from NVS: %r" % (cfg and list(cfg)))
    card.frame([0x04] + string("qemu-eth") + string("") + [0])
    ev, seen = card.wait_event(0x02, timeout=30)
    st = card.cmd([0x01])
    expect(ev is not None and st and st[0] == 2 and list(st[2:6]) == STATIC,
           "JOIN after power-up comes up on the saved static address (%r): %r" % (seen, st and list(st)))
    tcp_round_trip(card, "static address after power-up")

    # back to DHCP, saved: a lease replaces the static address
    net_config(card, 0, [0] * 4, [0] * 4, [0] * 4, [0] * 4, 53, 1)
    st = None
    for _ in range(200):
        st = card.cmd([0x01])
        if st and st[0] == 2 and list(st[2:6]) == [10, 0, 2, 15]:
            break
        time.sleep(0.05)
    expect(st and st[0] == 2 and list(st[2:6]) == [10, 0, 2, 15] and list(st[10:14]) == [10, 0, 2, 3],
           "static to DHCP: a lease again (10.0.2.15, DNS 10.0.2.3): %r" % (st and list(st)))
    cfg = card.cmd([0x09])
    expect(cfg and list(cfg) == [0] + [0] * 16 + [53, 0, 1], "DHCP saved: %r" % (cfg and list(cfg)))
    tcp_round_trip(card, "DHCP again")


if __name__ == "__main__":
    sys.exit(main())

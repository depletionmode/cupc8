# Wi-Fi card (card type $03)

This card gives CUPC/8 the internet connection the original project was
aiming for. The whole network stack runs **on the card**: Wi-Fi, DHCP, DNS,
TCP/UDP, and optionally TLS. The CPU sees a handful of numbered **sockets**
over the common SPI framing in `slot.md`, and never touches a packet.

## Hardware

- **Module:** **ESP32-C3-MINI-1U-N4** (LCSC C2911374). It is pre-certified,
  with an **MHF III (IPEX gen 3) receptacle for an external antenna** and 4 MB of flash. The
  external antenna means our layout can't detune the radio, which can't be
  simulated (see `verification.md` §5). There is no separate MCU: the ESP32-C3
  is both the SPI slave and the network stack.
- **Power:** a **TLV62569DBVR buck** (C141836, the main board's 3V3 part)
  from the slot's **+5V**, with 2.2 µH (FNR3015S2R2MT, C167747) and a
  453k/100k divider (3.32 V). The card does not use the slot's +3V3, because
  Wi-Fi TX peaks at ~350 mA and the slot's +3V3 is limited to 300 mA. The
  buck is followed by the bulk capacitance Espressif recommends (22 µF +
  0.1 µF at the module). An AMS1117 LDO was used first. It failed the power
  checks: 2.71 V at the module in a TX burst at the worst-case corner, and
  Tj ≈ 120 °C (`power.md`, POW-003, THM-001).
- **SPI slave:** ESP32-C3 GPSPI2 routed to SCK/MOSI/MISO/CS_n through the GPIO
  matrix. MISO reaches the slot through a **74LVC1G125** tri-state buffer
  whose /OE is CS_n, so this card releases the shared MISO line whenever it
  isn't selected. That is guaranteed by the buffer, not by how GPSPI2 drives
  its output enable, which nothing before hardware can check (QEMU has no
  SPI slave).
- **IRQ_n:** open-drain GPIO.
- **Programming** (in-system, via the slot programming port, see `slot.md`):

  | Slot pin | Module pin | Notes |
  |---|---|---|
  | SWCLK | U0RXD (GPIO20) | sysctl → card UART |
  | SWDIO | U0TXD (GPIO21) | card → sysctl UART |
  | CARD_RST_n | EN | RC 10 kΩ / 1 µF, per Espressif |
  | PROG_n | GPIO9 | boot strap. Card pull-up 10 kΩ, so it boots normally when PROG_n is released. |

  GPIO8 and GPIO2 are strapped high (10 kΩ), per the datasheet, and carry
  nothing else: a strapping pin is sampled at reset, and a signal from the
  slot (the shared MISO line, say) could be low at that moment. So the SPI
  slave's MISO is on GPIO5, not GPIO2.
- **Antenna:** a 150 mm MHF III-to-SMA lead (KH-IPEX3-SMA-RG081-150mm, LCSC
  C709347) and a 2.4 GHz SMA rubber-duck antenna (HJ-2.4GHz-SMA, C1509156),
  both ordered loose from JLC and plugged in by hand (JLC doesn't assemble
  cable parts). The module's receptacle is MHF III, not U.FL: MECH-007 found
  the U.FL antenna first listed would not mate. Plug the lead in before the
  card goes into its slot (about 16 mm to the next card); the SMA end mounts
  on the case.
- **Debug:** LEDs for power and link (GPIO4, lit while LINK is up). Test pads for the ESP32-C3
  native USB-Serial/JTAG (GPIO18/19), for debugging only.

## Status byte

The DMA SPI slave preloads the status byte, so it reflects the card's state
as of the end of the previous frame. That's fine for polling. For ordering,
use EVENTS.

```
bit 7    0
bit 6    LINK      associated and has an IP address
bit 5    BUSY      an asynchronous operation (scan/join/resolve/connect) is running
bit 4    EVENT     one or more unread events (see EVENTS); IRQ_n is asserted while set
bit 3:0  RXREADY   socket n (0–3) has received data waiting
```

## Commands

**→** marks response bytes, which are collected with a READ frame. Strings are
length-prefixed (`len8` followed by bytes). IPv4 addresses are 4 bytes,
most significant first. Ports are 16-bit little-endian.

### Network

| Op | Name | Args → response | Description |
|---|---|---|---|
| $01 | NET_STATUS | → state, rssi, ip[4], gw[4], dns[4] | state: 0 idle, 1 joining, 2 up, 3 failed |
| $02 | SCAN | — | Asynchronous. Raises the `SCAN_DONE` event. |
| $03 | SCAN_RESULT | idx → rssi, auth, ssid(len8 + bytes) | Up to 16 results. RESP_LEN = 1 with `$FF` means past the end. |
| $04 | JOIN | ssid(len8+…), psk(len8+…), save8 | Asynchronous. With `save = 1` the credentials are stored in NVS, and the card auto-joins at power-up. Raises `JOINED` or `JOIN_FAILED`. |
| $05 | LEAVE | forget8 | Disconnect. `forget = 1` also erases the stored credentials. |
| $06 | RESOLVE | name(len8+…) | Asynchronous DNS lookup. Raises `RESOLVED`. |
| $07 | RESOLVE_RESULT | → ok8, ip[4] | Result of the last `RESOLVE` |
| $08 | NET_CONFIG | mode, ip[4], mask[4], gw[4], dns[4], dns_port16, save8 | mode 0 DHCP, 1 static (ip, mask, gw). `dns` 0.0.0.0 = the one DHCP gives. `save = 1` keeps the settings in NVS, and they apply at power-up. Takes effect at once, and again at every join. |
| $09 | NET_CONFIG_GET | → mode, ip[4], mask[4], gw[4], dns[4], dns_port16, saved8 | The settings (not the lease: NET_STATUS has that). `saved = 1`: these are the ones in NVS. |

**Network settings.** At power-up the card uses what NET_CONFIG last saved,
or DHCP with the DHCP server's DNS (`dns_port` 53). A soft reset keeps the
settings, as it keeps the link. A static address needs a join all the same
(the card has to be on a network), and the link comes up with that address
without asking DHCP. A DNS server given here replaces DHCP's for the card's
own `RESOLVE`, which always asks it on port 53; `dns_port` is for the CPU's
DNS client (`net resolve` in the kernel), which reads it with NET_CONFIG_GET.
Going from static back to DHCP drops the address until a lease comes (NET_STATUS
reports `joining`, then `JOINED`). With `dns` set back to 0.0.0.0, DHCP's
server returns at the next lease. NET_CONFIG with fewer than 21 bytes, a mode
above 1, or static with address 0.0.0.0 is malformed. `save = 0` leaves NVS
as it was, so the saved settings come back at the next power-up.

### Sockets (4 sockets, numbered 0–3)

| Op | Name | Args → response | Description |
|---|---|---|---|
| $10 | OPEN | type8 → sock | type: 0 TCP, 1 UDP, 2 TLS over TCP, 3 ICMP (a raw ICMP socket). `$FF` = none free, or an unknown type. |
| $11 | CONNECT | sock, ip[4], port16 | Asynchronous. Raises `CONNECTED(sock)` or `CONN_FAILED(sock)`. |
| $12 | CONNECT_HOST | sock, port16, host(len8+…) | DNS + connect in one step. TLS uses `host` for SNI and checks it against the certificate. |
| $13 | LISTEN | sock, port16 | TCP server. An incoming client raises `ACCEPTED(sock)`, and the connection takes over this socket. |
| $14 | SEND | sock, len8, data × len | Queue up to 255 bytes. The host checks tx_free first (SOCK_STATUS). Excess bytes are dropped and an `ERROR(sock)` event is raised. |
| $15 | RECV | sock, max8 → n, data × n | Up to `max` bytes (1–250). `n` may be 0 when nothing is waiting. RESP_LEN = 1 + n. |
| $16 | SOCK_STATUS | sock → state, rx_avail16, tx_free16 | state: 0 closed, 1 connecting, 2 open, 3 listening, 4 peer closed |
| $17 | CLOSE | sock | |
| $18 | UDP_SENDTO | sock, ip[4], port16, len8, data × len | One datagram. It does not connect the socket, so a bound socket still hears everyone. On an ICMP socket: the ICMP message the host built, checksum included (at least 8 bytes); the port is ignored. A failed send raises `ERROR(sock)`. |
| $19 | UDP_BIND | sock, port16 | Bind a UDP socket to a local port (a UDP server). A port in use, or a socket that isn't UDP: `ERROR(sock)`. |
| $1A | RECVFROM | sock, max8 → ip[4], port16, n, data × n | One datagram (UDP) or ICMP message (ICMP socket, port 0, without the IP header), with its sender. `n = 0`: nothing waiting. `max` is capped at 248, so RESP_LEN = 7 + n fits; a longer datagram is cut to `max` and the rest dropped. On a TCP socket: n = 0. |

For UDP and ICMP sockets, RXREADY and SOCK_STATUS's `rx_avail` say a datagram
is waiting; the count is the stack's (all queued bytes, with lwIP's IP
headers for ICMP), not the next datagram's length.

### Events

| Op | Name | Args → response | Description |
|---|---|---|---|
| $1F | EVENTS | → count, (code, sock) × count | Drain up to 16 queued events. Clears EVENT and releases IRQ_n. |

Event codes: `$01 SCAN_DONE`, `$02 JOINED`, `$03 JOIN_FAILED`, `$04 LINK_LOST`,
`$05 RESOLVED`, `$10 CONNECTED`, `$11 CONN_FAILED`, `$12 ACCEPTED`,
`$13 PEER_CLOSED`, `$14 ERROR`.

### TLS

- **What it does:** type-2 sockets use mbedTLS with ESP-IDF's built-in CA
  bundle. The server certificate is verified, and a failed verification is
  reported as `CONN_FAILED`.
- **Why it matters:** an 8-bit machine can talk to HTTPS services, because
  every byte of cryptography runs on the card.

## Firmware structure

- **Toolchain:** ESP-IDF (C).
- **Code split:**
  - `fw/wifi/core/`, hardware-independent: the command interpreter, the
    socket table, and the event queue.
  - `fw/wifi/port/esp32c3/`: the SPI slave (DMA, queued so the next READ
    response is always preloaded), Wi-Fi and lwIP glue.
- **Testing:** the core also builds for the host against **the host's own
  sockets** (`fw/wifi/host/netposix.c`). So the co-simulation, the host
  tests and the simulator (`tools/sim --cards:...,wifi`: any SSID joins,
  the address is 127.0.0.1, localhost is the host's) make real TCP and UDP
  connections, driven entirely by CUPC/8 code.
  NVS is a variable there that outlives a simulated power cycle. ICMP uses
  Linux's unprivileged ping socket (the user's group must be in
  `net.ipv4.ping_group_range`): it sends echo requests only, and the id is
  the one in the first request (the socket is bound to it). The real image
  runs in Espressif's QEMU (WIFI-003) with lwIP, esp-tls, NVS, a raw ICMP
  socket and static addresses on the emulated Ethernet. Only the radio
  itself is left untested before hardware.

# Kernel API, user programs, and networking in CUPC/8 assembly

Status: **decided 2026-09-25 by David**, being implemented. This records the
decisions so a lost session loses nothing; the specs they change
(`memory-map.md`, `wifi-card.md`, `eink-card.md`, `sysctl.md`) are updated
as each part lands.

## Goals

- Programs written in CUPC/8 assembly, loaded **from the PC** (through the
  system card, when it is fitted) **or from the storage card**, and run.
- A **stable kernel API**: a jump table at a fixed address, grouped by
  feature, with **blank entries after each group** for later functions.
  It covers everything: system, console, graphics, e-ink, storage, net,
  timers.
- **Networking done in CUPC/8 assembly** where it can be: TCP and UDP
  servers and clients, a **DNS client** (`net lookup`, and `net get NAME`
  uses it), **`net ping`** over a raw ICMP socket, and **`net config`**.
  No BASIC commands for any of this (e-ink: decided; the rest follows).

## Memory layout (changes `memory-map.md`)

The kernel today uses ~11.5 KB: code $1000–$3504 (9.3 KB of a 12 KB
area), data $4000–$42e6, bss $6000–$65f8. The API, DNS, ping and the
loader do not fit the 2.8 KB left, so:

| Range | Use |
|---|---|
| $0000–$0fff | vectors, boot ROM variables, stack (as now) |
| $1000–$4fff | kernel code (16 KB); the jump table first |
| $5000–$5fff | kernel data |
| $6000–$6eff | kernel bss |
| $6f00–$6fff | **API block**: fixed addresses shared with programs (below) |
| $7000–$dfff | **user program** (28 KB): loaded at $7000, entered at $7000 |

`kernel/assemble.sh` passes `0x1000,0x5000,0x6000`; a test fails the build
if code, data or bss outgrow their areas.

## The jump table

- `kernel/api.s` (sorts first, so it follows the assembler's `b main` at
  $1000) holds the table from **$1003**: **8 groups × 16 entries × 3 bytes**
  (`b routine`), $1003–$1182. Group g, entry n is at `$1003 + 48g + 3n`.
- Unused entries are `b api_none`, which returns `r0 = $ff` (and sets
  `API_ERR` to $ff, "not implemented").
- `kernel/api.inc` gives every entry a name (`%define API_NET_OPEN $10f3`)
  for programs. A test checks the table's addresses against `api.inc` and
  that no used entry moved (entries are only ever **added**).

| Group | Base | Contents (first entries) |
|---|---|---|
| 0 system | $1003 | version, exit (back to the terminal), api_block address, slot table |
| 1 console | $1033 | putc, puts, getkey (wait), pollkey, cls, cursor set/get, attr |
| 2 graphics | $1063 | mode, pixel, rect, line, palette, text-plane helpers (what `gfx.s`/the GPU protocol offer) |
| 3 e-ink | $1093 | eink_auto, eink_get, eink_status, eink_refresh (`eink-card.md`) |
| 4 storage | $10c3 | info, open, read, write, close, seek, dir first/next, delete, rename |
| 5 net | $10f3 | status, join, open, connect, connect_host, listen, send, recv, sock_status, close, udp_bind, sendto, recvfrom, events, resolve (the kernel's DNS client), config get/set |
| 6 timers | $1123 | ticks (ms since boot), wait ms |
| 7 reserved | $1153 | |

**Calling convention.** A program calls an entry like any kernel routine:
`push pch` / `push pcl` / `b API_X`; the routine returns with
`pop pcl` / `pop pch`. Small arguments go in r0/r1; the rest, and pointers
(lo, hi), in the **API block** at $6f00. Results: r0 = 0 ok or an error
code, data in the API block or the caller's buffer. Each routine's
comment in `api.s` is its contract.

**API block ($6f00–$6fff):** `API_ARGS` $6f00 (32 bytes of arguments and
results), `API_ERR` $6f20, `API_RUN` $6f21 (the PC loader's mailbox), the
rest reserved.

## Loading and running programs

- **Format:** a flat binary assembled for $7000 (`tools/mkprg.py prog.s -o
  prog.prg` puts `kernel/api.inc` in front, assembles it with its data right
  after the code and its bss after that, and adds the header). Up to 28 KB.
- **Program file header** (decided by David): 4 bytes, `'C'`, `'8'`, `'P'`,
  then the version, 1. The body follows and is loaded at $7000.
  `tools/mkprg.py prog.bin -o prog.prg` wraps a binary assembled some other
  way.
- **From the storage card:** the terminal command `exec "NAME"` reads the
  file. With the header (version 1) the body goes to $7000, 128-byte chunk
  by chunk, and is called. `"C8P"` with another version, or cut short, gives
  `bad program header`; a body past $dfff gives `program too big`; neither
  runs anything. Any other file is a BASIC program as SAVE writes it: `exec`
  does LOAD's work (NEW, then the lines as if typed), then RUN. `ret`
  (`pop pcl`/`pop pch`) or the `exit` API entry returns to the terminal,
  which resets its stack.
- **From the PC:** `cupc8.py run prog.prg` (or the bare binary) writes the
  body at $7000 with `RAM_WRITE`, then sets `API_RUN` to 1. The terminal
  looks at `API_RUN` every time its key wait wakes: the kernel's clock
  (timer 0) wakes the `WAI` about every 60 µs, more often than the ~20 Hz
  planned, and the look is three instructions. It then calls $7000 as `exec`
  does. `API_RUN` is 2 while a program runs and 0 again at the prompt, and
  `cupc8.py run` refuses unless it is 0. Needs the system card. The bridge's
  RAM writes are safe while the CPU runs, byte by byte (`sysctl.md`), which
  is why `API_RUN` goes last.
- **In the simulator** (no system card): `runProgram` in `tools/sim.nim` does
  what `cupc8.py run` does.

### As implemented (2026-09-25)

- `kernel/api.s` holds the table, `kernel/sys.s` the routines (each one's
  comment is its contract) and the loader, `kernel/api.inc` the names.
  Pointers in `API_ARGS` are low byte first; routines that return a pointer
  in registers give r0 = low, r1 = high.
- **Resetting the stack:** nothing reads SP, so the terminal finds it once at
  start-up (a pushed byte lands at SP: the address that takes two different
  pushed markers is SP), and a program's end pops until the same probe says
  SP is back there. A program that pops more than it pushed cannot be
  recovered.
- **The clock:** timer 0 counts instructions (and WAI idle turns, one per 3
  clocks), so the kernel's ms since boot is weighted: 1/16 ms per expiry
  while waiting in WAI, 4/16 while running. About right (±25%), not exact.
  The tick costs a program about 17 instructions in 250.
- **CPU fix found on the way:** an IRQ taken right after `POP pcl` lost the
  return (its frame went over the popped byte, its handler's `POP pcl`
  replaced pcl). `cpu.vhd` and `sim.nim` now take no IRQ at that boundary
  (CPU-005).
- Graphics has no BLIT8/BLIT1/DEFCHAR entries yet (a frame over 64 bytes
  needs the card's FREE check); they can be added in group 2's spare
  entries.

## Networking

### Wi-Fi card additions (changes `wifi-card.md`)

| Op | Name | Args → response | Description |
|---|---|---|---|
| $08 | NET_CONFIG | mode, ip[4], mask[4], gw[4], dns[4], dns_port16, save8 | mode 0 DHCP, 1 static (ip, mask, gw). `dns` 0.0.0.0 = the one DHCP gives. `save = 1` keeps it in NVS, applied at power-up. |
| $09 | NET_CONFIG_GET | → mode, ip[4], mask[4], gw[4], dns[4], dns_port16, saved8 | The settings (not the lease: NET_STATUS has that). |
| $10 | OPEN | type8 → sock | adds type **3 ICMP** (a raw ICMP socket: SENDTO sends an ICMP message the host built, checksum included; RECVFROM returns ICMP messages that arrive) |
| $19 | UDP_BIND | sock, port16 | Bind a UDP socket to a local port (a UDP server). |
| $1A | RECVFROM | sock, max8 → ip[4], port16, n, data × n | UDP (and ICMP, port 0): one datagram, with its sender. n = 0: nothing waiting. |

`UDP_SENDTO` ($18) also sends on an ICMP socket (port ignored). The card
keeps everything else it does today (the card's RESOLVE stays for other
software; the kernel's `net` no longer uses it).

### Kernel (`kernel/net.s`, terminal `net`)

- **`net config`** prints the settings. `net config dns IP [PORT]`,
  `net config ip IP MASK GW` (static), `net config dhcp`,
  `net config save`. Uses NET_CONFIG / NET_CONFIG_GET.
- **DNS client in assembly:** builds the query (RD set, one A question),
  sends it over UDP to the configured server (or DHCP's), waits for the
  answer (timeout, one retry), checks the id, parses the answer section
  (following name compression) for the first A record. API entry
  `net resolve`.
- **`net lookup NAME`** prints the address. **`net get NAME [PORT]`**
  resolves with the kernel's client (a dotted address is used as is), then
  CONNECT.
- **`net ping HOST [COUNT]`:** resolves, opens an ICMP socket, sends echo
  requests (id, sequence, a payload, the Internet checksum computed in
  assembly), matches replies by id and sequence, prints the round-trip
  time from the timer, and a summary.
- The net API group gives programs the same sockets (TCP client/server,
  UDP bind/sendto/recvfrom, ICMP, events), so a server is: open, listen or
  bind, then `WAI` for the card's IRQ and drain EVENTS.

### Emulator

QEMU's user networking lets the card connect out; a server on the machine
needs **port forwards**: `Machine.create({ forward: ['tcp:8080:80',
'udp:5353:53'] })`, the viewer's `--forward`, passed to QEMU as
`hostfwd`. 10.0.2.2 is the PC, 10.0.2.3 QEMU's DNS; QEMU answers pings
to 10.0.2.2 itself.

## E-ink settings

The e-ink group of the table is where `eink_auto`/`eink_get`/`eink_status`
live (`eink-card.md`: AUTO_EXT $0C, AUTO_GET $0D on the card).

## Testing

- **Card:** the Wi-Fi core's host tests (lwIP's Unix port) for NET_CONFIG
  (and NVS persistence), UDP_BIND, RECVFROM, ICMP sockets; the e-ink core's
  for AUTO_EXT/AUTO_GET; the HDMI core treats $0C/$0D as NOPs.
- **Kernel (`tools/simtest.nim`):** the table's addresses against
  `api.inc`; a test program at $7000 calling entries of every group;
  `exec` from the storage model; DNS answers from a scripted server
  (compression, no answer, NXDOMAIN, wrong id, timeout); ping's checksum
  and reply matching.
- **Whole machine (native emulator, E2E):** `cupc8.py run` of an assembly
  **TCP echo server** and **UDP echo server**, reached from the PC through
  port forwards; `net lookup` and `net get NAME` against a DNS server the
  test runs on the PC (`net config dns 10.0.2.2 PORT`); `net ping 10.0.2.2`;
  `exec` from the SD card model.
- Every bug found gets a test and a counterexample, as always.

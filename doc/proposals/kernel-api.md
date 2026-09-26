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
| $1000–$67ff | kernel code (22 KB); the jump table first |
| $6800–$6eff | kernel data (1.75 KB) |
| $6f00–$6fff | **API block**: fixed addresses shared with programs (below) |
| $7000–$dfff | **user program** (28 KB): loaded at $7000, entered at $7000 |
| $e000–$efff | kernel bss (4 KB): RAM once the kernel turns the ROM off, its first instruction |

`kernel/assemble.sh` passes `0x1000,0x6800,0xe000`; a test (KRN-010) fails
the build if code, data or bss outgrow their areas. (Decided first as code
$1000–$4fff, data $5000, bss $6000; with the API, networking and the bank
routines the code reached $5623, so on 2026-09-25 the code area grew to
$5fff, data moved to $6000 and bss to $e000; on 2026-09-26, with 16-bit BASIC,
the memory API and line editing, the code area grew to $67ff and data moved
to $6800, which it fills to about 80 %.)

## The jump table

- `kernel/api.s` (sorts first, so it follows the assembler's `b main` at
  $1000) holds the table from **$1003**: **8 groups × 32 entries × 3 bytes**
  (`b routine`), $1003–$1302. Group g, entry n is at `$1003 + 96g + 3n`
  (David, 2026-09-25: 32 a group, not 16, so a group has room to grow).
- Unused entries are `b api_none`, which returns `r0 = $ff` (and sets
  `API_ERR` to $ff, "not implemented").
- `kernel/api.inc` gives every entry a name (`%define API_NET_OPEN $11e9`)
  for programs. A test checks the table's addresses against `api.inc` and
  that no used entry moved (entries are only ever **added**).

| Group | Base | Contents (first entries) |
|---|---|---|
| 0 system | $1003 | version, exit (back to the terminal), api_block address, slot table, bank_set, bank_get, bank_count, bank_far_copy (`kernel/bank.s`, as they are: they leave `API_ERR` alone), mem_cmp, mem_cpy, term_hook |
| 1 console | $1063 | putc, puts, getkey (wait), pollkey, cls, cursor set/get, attr, ..., readline |
| 2 graphics | $10c3 | mode, pixel, rect, line, palette, text-plane helpers (what `gfx.s`/the GPU protocol offer); from $10e4 the e-ink card's native mode 2 (`basic-graphics.md`) |
| 3 e-ink | $1123 | eink_auto, eink_get, eink_status, eink_refresh (`eink-card.md`) |
| 4 storage | $1183 | info, open, read, write, close, seek, dir first/next, delete, rename, perror |
| 5 net | $11e3 | 16 routines (`kernel/net.s`): status, join, open, connect, connect_host, listen, send, recv, sock_status, close, udp_bind, sendto, recvfrom, events, resolve (the kernel's DNS client), config (r0 0 get, 1 set); then 16 blank |
| 6 timers | $1243 | ticks (ms since boot), wait ms |
| 7 reserved | $12a3 | |

**Calling convention.** A program calls an entry like any kernel routine:
`push pch` / `push pcl` / `b API_X`; the routine returns with
`pop pcl` / `pop pch`. Small arguments go in r0/r1; the rest, and pointers
(lo, hi), in the **API block** at $6f00. Results: r0 = 0 ok or an error
code, data in the API block or the caller's buffer. Each routine's
comment in `api.s` is its contract.

**API block ($6f00–$6fff):** `API_ARGS` $6f00 (32 bytes of arguments and
results), `API_ERR` $6f20, `API_RUN` $6f21 (the PC loader's mailbox), the
USB console's rings and indices $6f22–$6f26 and $6f40–$6fff
(`usb-console.md`, `memory-map.md`), the
rest reserved.

**The USB console.** The console group reaches a PC's terminal through the
system card with no change to it: everything `API_PUTC`/`API_PUTS` print
(and the terminal's own output) is also put in `CON_OUT`, and
`API_GETKEY`/`API_POLLKEY` take keys from `CON_IN` before the IO card's.
The key wait's 20 Hz tick bounds how long a key from the PC waits when the
kernel is idle. While a PC has the console open (`CON_FLAGS` bit 0, HOST,
`%define CON_FLAGS` in `api.inc`) a program that prints faster than the PC
reads waits for it; otherwise nothing waits and what does not fit in the
ring is dropped.

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
  `bad program header`; a body past $dfff gives `program too big` (found
  before anything is loaded); neither runs anything. Any other file is a
  BASIC program as SAVE writes it: `exec` hands its name to the terminal's
  hook (`API_TERM_HOOK`, r0 = 1), and BASIC does LOAD's work (NEW, then the
  lines as if typed), then RUN. `ret`
  (`pop pcl`/`pop pch`) or the `exit` API entry returns to the terminal,
  which resets its stack.
- **From the PC:** `cupc8.py run prog.prg` (or the bare binary) writes the
  body at $7000 with `RAM_WRITE`, then sets `API_RUN` to 1. The terminal
  looks at `API_RUN` every time its key wait wakes: the chipset's tick
  (IRQ_PEND bit 4, `memory-map.md`) wakes the `WAI` every 50 ms, and the look
  is three instructions. It then calls $7000 as `exec` does. `API_RUN` is 2 while a program runs and 0 again at the prompt, and
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
- **The clock** is the chipset's millisecond counter (MS_COUNT, $f206–$f209,
  `memory-map.md`; David, 2026-09-25): 12000 clocks of the chipset's 12 MHz
  a millisecond, exact, with a latch so MS_COUNT0-then-1-2-3 is one value.
  `API_TICKS` reads it; `API_WAIT_MS` N watches it to its next step and N
  more (more than N ms, at most N + 1; the CPU busy meanwhile); DNS and ping
  time out after 1000 ms of it and ping's round trip is exact ms. The
  chipset's 20 Hz tick only wakes the terminal's key wait. The CPU's timers
  (`TMR0`, `TMR1`) are the programs' again: the kernel masks their IRQs and
  never starts them. (First built on a timer-0 tick counting instructions,
  ±25%, and a TMR1 clock for the network; both are gone.)
- **CPU fix found on the way:** an IRQ taken right after `POP pcl` lost the
  return (its frame went over the popped byte, its handler's `POP pcl`
  replaced pcl). `cpu.vhd` and `sim.nim` now take no IRQ at that boundary
  (CPU-005).
- Graphics has no BLIT8/BLIT1/DEFCHAR entries for GFX mode yet; they can
  be added in group 2's spare entries (the mode-2 BLITs below show how: a
  frame over 64 bytes waits for the card's FREE first).

### mem_cmp and mem_cpy (2026-09-26)

Two group-0 entries give programs the kernel's memory routines, with
16-bit lengths (`kernel/printf.s`'s `mem_cmp` and `mem_cpy`, which took
8-bit ones on the stack, went on 2026-09-26: nothing called them). `API_ARGS` = dst
(lo, hi), src (lo, hi), len16 (lo, hi), len 0-65535:

| Entry | Address | Result |
|---|---|---|
| `API_MEM_CMP` | $101b | memcmp, bytes unsigned: r0 = 0 all equal; else at the first pair that differs 1 (dst's byte the greater) or $ff (the less), r1 = dst's byte - src's, `API_ARGS[0..3]` point at that pair and `API_ARGS[4..5]` = the bytes after it |
| `API_MEM_CPY` | $101e | **memmove**: overlapping areas copy right (backwards when dst is above src). r0 = 0 |

r0 is also left in `API_ERR`; `API_ARGS` is used up as they work (the
pointers step, len counts down). About 50 instructions a byte. KRN-024.

### Mode 2 (2026-09-26, `basic-graphics.md`)

`API_GFX_MODE` takes 2, the e-ink card's native mode (`eink-card.md`: the
panel's 648 x 480 or 800 x 480, 2 bits a pixel, grey 0 black ... 3 white),
and returns r0 = 0, or $ff on HDMI (INFO says it is not e-paper; nothing is
sent). The mode-2 commands ($40-$49) have entries after `API_GFX_VSYNC`,
with the card's arguments in `API_ARGS` (16-bit coordinates, low byte
first, positions signed); each returns r0 = 0, or $ff on HDMI, where nothing
is sent:

| Entry | Address | `API_ARGS` |
|---|---|---|
| `API_GFX2_PIXEL` | $10e4 | x16, y16, g |
| `API_GFX2_FILL_RECT` | $10e7 | x16, y16, w16, h16, g |
| `API_GFX2_RECT` | $10ea | the same: a 1-pixel outline |
| `API_GFX2_LINE` | $10ed | x0_16, y0_16, x1_16, y1_16, g |
| `API_GFX2_BLIT1` | $10f0 | x16, y16, w16, h16, fg, bg ($ff transparent), then a pointer to ceil(w/8) x h bytes |
| `API_GFX2_BLIT2` | $10f3 | x16, y16, w16, h16, then a pointer to ceil(w/4) x h bytes |
| `API_GFX2_TEXT16` | $10f6 | x16, y16, fg, bg; `API_ARGS[7..8]` a pointer to the text (the kernel puts its length in `API_ARGS[6]`) |
| `API_GFX2_TEXT8` | $10f9 | the same, the 8 x 8 font |
| `API_GFX2_VSCROLL` | $10fc | dy16 (signed, down if negative), g |
| `API_GFX2_GETPIXEL` | $10ff | x16, y16; r1 = the grey |

A BLIT is one frame of at most 8128 bytes and w at most 1020; a bigger one
is not sent (r0 = $fe). The BLITs and texts wait for the card's FIFO to
have room for the whole frame (NOP frames until FREE says so,
`gpu-protocol.md`), since the card drops a frame that does not fit (it can
fill while a REFRESH holds it). BASIC's graphics statements use these and
the GFX entries.

### BASIC as a program (2026-09-26, `basic-program.md`)

BASIC (`basic/`) is a program at $7000 like any other and uses only this
API. The kernel loads it at boot and after each native program (from the
ROM, or `BASIC.PRG` on the SD card; `memory-map.md`) and calls its `main`.
Three entries were added for it (KRN-033):

| Entry | Address | |
|---|---|---|
| `API_TERM_HOOK` | $1021 | r0, r1 = the address (low, high) of a routine in the program at $7000, or 0, 0 for none: the terminal's hook. The terminal runs its own commands (`help`, `dir`, `del`, `net`, `refresh`, `exec`) and calls the hook, as a routine, with every other line: r0 = 0, `API_ARGS[0..1]` = a pointer to the line as typed (up to 78 characters, a CR, a 0). `exec "NAME"` calls it for a file with no program header: r0 = 1, `API_ARGS[0..1]` = a pointer to the name. `API_RUN` is 2 while it runs. With no hook the line is `ERROR: invalid cmd!` (and the file `bad program header`). The kernel clears the hook when it loads a program over $7000; BASIC sets it again in `main`. r0 = 0 |
| `API_READLINE` | $1087 | a line from the keyboard with the terminal's line editor (echoed; Backspace or DEL takes the last character back; Enter ends it) into the 80-byte buffer at the pointer in `API_ARGS[0..1]`: up to 78 characters, a CR, a 0. r1 = the characters' count, r0 = 0 |
| `API_ST_PERROR` | $11a1 | print the terminal's message for storage error r0 (not 0), as SAVE, LOAD, DIR and DEL do: `no SD card`, `file not found`, ... |

So the terminal owns the prompt, the line editor and the loop; BASIC owns
the lines it is handed: numbered lines (the editor), `new`, `run`, `list`,
`clr`, `save`, `load`. BASIC's program text is at $c000 (`memory-map.md`),
outside its own memory, so a native program that stays below $c000 leaves
it for BASIC to find when it is loaded again.

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
  time from the chipset's millisecond counter, and a summary.
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

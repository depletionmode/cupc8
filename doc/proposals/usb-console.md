# USB console through the system card

Status: **decided 2026-09-25 by David** ("build it; it's fine for the system
card to have this functionality"), **built** (2026-09-25; "As built" at the
end). Both directions: the terminal's text goes to the PC, and what is typed
on the PC comes in as keys.

## What it is

The PC sees the system card as a composite USB device with **two CDC serial
ports**: the first stays `cupc8.py`'s protocol port (`sysctl.md`), the second
is the **console**. Open it with any terminal program (`picocom
/dev/ttyACM1`, PuTTY): everything the kernel's terminal prints appears there
as well as on the graphics card, and what you type there is typed into the
machine, as from the USB keyboard. A BASIC program can be pasted in.

No new hardware. It works only with the system card fitted; without it the
machine is unchanged (nothing reads the rings, the kernel never waits on
them).

This widens the system card's role (`sysctl.md` said it only programs,
resets and debugs, and touches nothing at start-up): it now also reads and
writes two rings in RAM while the machine runs, through the chipset's
bridge, and only while a PC has the console port open.

## The rings (fixed addresses, in the API block)

| Address | Name | Written by | |
|---|---|---|---|
| $6f22 | CON_OUT_HEAD | kernel | next free byte of the output ring |
| $6f23 | CON_OUT_TAIL | system card | next byte the card will take |
| $6f24 | CON_IN_HEAD | system card | next free byte of the input ring |
| $6f25 | CON_IN_TAIL | kernel | next byte the kernel will take |
| $6f26 | CON_FLAGS | system card | bit 0 HOST: a PC has the console port open |
| $6f40–$6fbf | CON_OUT | kernel | output ring, 128 bytes |
| $6fc0–$6fff | CON_IN | system card | input ring, 64 bytes |

Indices are 8-bit offsets into their ring, modulo its size; head == tail is
empty, one slot stays free. Each side writes only its own index, **after**
the data it covers (the bridge's writes are atomic per byte, not across
bytes, `sysctl.md`), so no lock is needed.

- **Kernel, output:** every character the terminal prints (`print_ascii_char`
  and what calls it) is also put in CON_OUT. If the ring is full: with HOST
  set, the kernel waits (the PC is reading; it drains in milliseconds); with
  HOST clear it drops the character, so a machine with no system card, or
  no terminal open, never stalls.
- **Kernel, input:** the key wait and the key poll take bytes from CON_IN
  as well as from the IO card. The kernel's slow chipset tick (the key
  wait's ~20 Hz wake-up, `kernel-api.md`) bounds the latency.
- **Kernel, boot:** it zeroes the four indices and CON_FLAGS (RAM is junk at
  power-on); the system card sets HOST again on its next poll.
- **System card:** while the console port is open (DTR), every few
  milliseconds: set HOST, read CON_OUT_HEAD, copy the new bytes to the PC,
  write CON_OUT_TAIL; copy bytes from the PC into CON_IN (as room allows)
  and write CON_IN_HEAD. On close, clear HOST. Newlines: the kernel's `\n`
  goes out as CR LF; CR from the PC comes in as Enter.
- **API:** the console group gets the ring through PUTC/PUTS/GETKEY/POLLKEY
  unchanged; a program can check HOST if it cares.

## Emulator and simulator

- **Native emulator:** the system card runs its real firmware; the USB model
  grows the second CDC interface, and `Machine` gets a console stream (e.g.
  `m.console.write(bytes)`, `m.console.read()`), and the browser viewer a
  panel or a pipe for it.
- **Simulator:** no system card, so `--console` maps the rings to the
  terminal the simulator runs in (stdin raw, stdout), HOST set while it is
  on (kept up to date, as every kernel change).

## Tests

- System card host tests (SYS-): the composite descriptors, the ring
  protocol against a RAM model (wrap, full rings, HOST on open/close, CR LF),
  the bridge traffic only while open.
- Kernel on the simulator: output reaches the ring and wraps; full ring
  with and without HOST (waits vs drops); input from the ring reaches the
  prompt and BASIC; boot zeroes the rings.
- Whole machine (native): the kernel's banner and a typed command's output
  read from the console port; a BASIC program pasted through it runs; no
  console open: nothing waits.
- Every bug found: a test and a counterexample.

## As built

- **System card** (`fw/sysctl/core/console.c`, `fw/rp2040/sysctl`): a
  composite device, VID:PID 1209:C8C8, two CDC functions with their
  interface associations: interfaces 0/1 the protocol ("CUPC/8 sysctl"),
  2/3 the console ("CUPC/8 console"); `PING` says `CUPC8 sysctl 2.1`. The
  poll runs from the main loop (`sysctl_poll`), every `CON_POLL_MS` = 2 ms
  while DTR is set on interface 2 and the chipset is up: one 5-byte
  `RAM_RD` of the indices and flags, `HOST` written if clear, up to the
  USB buffer's room from `CON_OUT` (never half a CR LF), then its tail;
  up to CON_IN's room from the PC (CR Enter, CR LF one Enter, a lone LF
  Enter), then its head. Closed: `HOST` cleared once, then no bridge
  traffic. A PC that holds the port open without reading holds up the
  terminal, as flow control on a serial line would (`sysctl.md`).
- **Kernel** (`kernel/console.s`): `con_init` zeroes $6f22–$6f26 first
  thing at boot; `gpu_putc`, which everything the terminal and the console
  API print goes through, calls `con_putc` first (so it works with no
  graphics card too); `keyb_poll` takes `CON_IN` before the IO card, and
  the key wait looks at `CON_IN` each time the 20 Hz tick wakes it. A $ff
  byte from the PC is dropped (it reads as "no key").
- **cupc8.py** finds each port by its interface number; `cupc8.py console
  [PORT]` is a raw terminal on the console (`Ctrl-]` quits; piped, it types
  its input and quits after `--idle` seconds of quiet).
- **Native emulator**: the host side of both ports is `CdcHost`
  (`test/emu/cdchost.mjs`, C++ `emu/rp2040/src/usb/cdchost.cpp`), which
  enumerates like rp2040js's one-port `USBCDC` and then opens and closes
  each port with SET_CONTROL_LINE_STATE on its interface. `m.console`
  (`open`, `close`, `write`, `read`, `listen`) in machinenative.mjs;
  `tools/machine_view.mjs --native --console` shows a pane,
  `--console-port N` serves it on TCP for `cupc8.py console tcp:...`.
- **Simulator**: `tools/sim --console` (every 2 guest ms, as the card; input
  only once the kernel has reached its first WAI, so its boot does not zero
  what was typed ahead).
- **Tests**: SYS-008 (the core against the bridge model), SYS-006 (the real
  binary: two ports, polling only while open and the chipset up), HOST-002
  (`cupc8.py console` against `sysctl_sim --console`), KRN-030 (the kernel
  on the simulator), SIM-020 (`--console`), E2E-020 (the whole machine).
- **Known limit**: if the machine resets while the card is between reading
  `CON_OUT_HEAD` and writing `CON_OUT_TAIL` (a window of ~100 µs in each
  2 ms poll), the kernel's zeroed indices meet the card's late tail, and up
  to a ring's worth of stale bytes can reach the PC once. Nothing waits
  because of it.

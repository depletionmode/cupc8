# USB console through the system card

Status: **decided 2026-09-25 by David** ("build it; it's fine for the system
card to have this functionality"), being implemented. Both directions: the
terminal's text goes to the PC, and what is typed on the PC comes in as
keys.

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

# IO card: USB keyboard (card type $02)

An RP2040 runs TinyUSB in **host** mode on its native USB port, with a USB-A
receptacle. It turns a HID keyboard into a byte stream for the CPU, over the
common SPI framing in `slot.md`.

## Hardware

- **USB-A receptacle.** D+/D− go straight to the RP2040's USB pins, with 27 Ω
  series resistors per the RP2040 hardware design guide and ESD protection
  (USBLC6-2 class).
- **VBUS:** +5V from the slot through a current-limited power switch, 500 mA
  limit with soft start (SY6280/AP2553 class). Its fault flag goes to an
  RP2040 GPIO.
- **15 kΩ pull-downs on D+/D−,** as host mode requires.
- **Standard RP2040 minimal design:** 12 MHz crystal, W25Q16 QSPI flash, 3V3
  from the slot.
- **LEDs:** power, keyboard connected, and activity.
- **Debug pads:** BOOTSEL and a UART TX pad. SWD comes via the slot.

## Behaviour

- **Keyboards supported in M1:** one keyboard, directly attached, using the
  **HID boot protocol**. The card sends SET_PROTOCOL(boot) on enumeration.
  Hubs and composite devices are best-effort, not required.
- **FIFO:** key reports become bytes in a **64-byte FIFO**. If it overflows,
  the newest byte is dropped and `OVERFLOW` is set.
- **Typematic repeat:** done on the card. The default is a 500 ms delay and a
  33 ms rate.
- **Lock keys:** Caps Lock and Num Lock are handled on the card, which also
  drives the keyboard's LEDs.
- **IRQ_n:** asserted while the FIFO is non-empty (if `IRQ_EN`).

## Status byte (returned during every opcode byte)

```
bit 7  0
bit 6  OVERFLOW  (sticky; cleared by GETKEY that empties the FIFO)
bit 5  KBD_CONNECTED
bit 4  VBUS_FAULT
bit 3:0 FIFO count, capped at 15
```

## Commands

| Op | Name | Args → response | Description |
|---|---|---|---|
| $00 | GETKEY | → key | Pop one byte, or `$FF` if the FIFO is empty |
| $01 | GETKEYS | n → n bytes | Pop up to `n` (1–16) bytes, padded with `$FF` |
| $02 | GETMODS | → mods | Current HID modifier bits: LCtrl, LShift, LAlt, LGUI, RCtrl, RShift, RAlt, RGUI |
| $03 | SETREPEAT | delay, rate | In units of 10 ms. `delay=0` turns repeat off. |
| $04 | SETMODE | m | 0 = ASCII (default). 1 = raw: each key event becomes 2 bytes, `usage, flags` (bit0 = pressed). |
| $05 | FLUSH | — | Empty the FIFO |

## ASCII mode key map (US layout, M1)

| Key | Byte |
|---|---|
| Printable keys, with Shift and Caps Lock | ASCII `$20–$7E` |
| Enter / keypad Enter | `$0D` |
| Backspace | `$08` |
| Tab | `$09` |
| Esc | `$1B` |
| Delete | `$7F` |
| Ctrl + A…Z | `$01–$1A` |
| Up, Down, Left, Right | `$80`, `$81`, `$82`, `$83` |
| Home, End, PgUp, PgDn, Insert | `$84`, `$85`, `$86`, `$87`, `$88` |
| F1…F12 | `$91–$9C` |
| Keypad (Num Lock on) | digits and `. + - * /` |
| Keypad (Num Lock off) | navigation codes above |

- **Reserved:** `$FF` is never produced as a key. It means "empty".
- **Unmapped keys:** produce nothing in ASCII mode.
- **Polling:** the status byte's FIFO count arrives free with any frame, so
  the kernel only sends `GETKEY` plus a READ frame when a key is waiting, or on
  IRQ. `GETKEY` still returns today's "key or `$FF`" byte.

## Firmware structure

`fw/io/core/` is hardware-independent. It contains the HID report → key-event
diff, the keymap, typematic repeat, the FIFO and the SPI command
interpreter. The same core runs in:
- host unit tests (the full keymap table, rollover, repeat timing, overflow)
- the co-simulation (keystrokes injected as HID reports)
- the RP2040 build (with TinyUSB host and the PIO SPI slave)

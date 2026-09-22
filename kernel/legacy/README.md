# Legacy drivers

The Milestone 1 machine drives an SPI graphics card (`doc/hardware/gpu-protocol.md`)
instead of a directly attached TFT, so these are no longer built into the kernel:

- `ili9340.s`, `st7735.s` — SPI TFT panel drivers (the display used up to 2016).
- `charset.s` — the Commodore 64 character ROM the old pixel path rendered
  with. The graphics card carries its own public-domain CP437 font.

They are kept for reference and for anyone driving a panel directly.

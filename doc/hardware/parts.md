# Key parts: JLCPCB assembly availability

Stock is from JLCPCB's assembly parts library, which is what JLC can
actually place. It was checked on 2026-09-22 with `hw/tools/jlcparts.py`.
Re-run the check before ordering:

```
hw/tools/jlcparts.py check C1521989 C645939 C632851 C1348955 ...
```

"ext" means an extended part, which costs a small per-part-type loading fee.
None of the key ICs are basic parts. Passives will be chosen from basic parts
during schematic capture.

**Build quantity: 2 systems.** JLC fabricates 5 bare PCBs of each design;
we assemble **3 main boards** (one spare, since there is no prototype) and
**2 of each card** (CPU, GPU, IO, Wi-Fi) (JLC's minimum for assembly). "Qty" is parts placed across
all assembled boards, before JLC's attrition extras.

| Function | Part | LCSC | Stock | Qty | Notes |
|---|---|---|---|---|---|
| Chipset FPGA **and** CPU card FPGA | ICE40HX4K-TQ144 | C1521989 | 51 | 5 | Same part on both boards: one footprint, one loading fee, no `cpu.vhd` fit risk. $17.45 vs $16.47 for the HX1K-VQ100 it replaced. |
| ROM | SST39VF040-70-4I-NHE (512 KB, PLCC-32) | C645939 | **11** | 3 | ⚠ low stock. Pin-compatible fallbacks below. |
| ROM (fallback) | SST39VF040-70-4C-NHE-T | C632853 | 8 | | same die, commercial temperature range |
| ROM (fallback) | SST39VF010-70-4I-NHE-T (128 KB, PLCC-32) | C632851 | 33 | | Same footprint and pinout. A17/A18 are NC, so ROM_BANK is limited to 0–63. Enough for boot + kernel (≤ 56 KB). |
| SRAM | IS62WV5128EBLL-45HLI (512K×8, 45 ns, 3.3 V, sTSOP-32) | C1348955 | 234 | 3 | AS6C1008 isn't stocked. A16–A18 are tied to GND, so 64 KB is used. |
| System controller + card MCUs | RP2040 | C2040 | 75,161 | 7 | 3 main + 2 GPU + 2 IO |
| MCU flash | W25Q16JVSSIQ | C131025 | 18,196 | 7 | one per RP2040 |
| FPGA config flash | W25Q32JVSSIQ | C179173 | 20,724 | 3 | holds both bitstreams |
| 12 MHz crystal | X322512MSB4SI | C9002 | 68,389 (basic) | 7 | one per RP2040; FPGA clocks come from sysctl |
| 3V3 buck | TLV62569DBVR (2 A) | C141836 | 233,257 | 3 | TI reference layout |
| 1V2 LDO | RT9013-12GB (500 mA) | C58464 | 17,201 | 5 | main board + CPU card |
| USB power switch | SY6280AAC | C55136 | 86,882 | 5 | main input + IO card VBUS |
| USB-C receptacle | TYPE-C-31-M-12 (16P) | C165948 | 105,121 | 3 | USB 2.0 + CC |
| USB ESD | USBLC6-2SC6 | C7519 | 41,334 | 5 | main USB-C + IO card USB-A |
| 5V TVS | SMF5.0A | C193402 | 583,437 | 3 | |
| Input fuse | SMD1812P200TF (2 A PTC) | C20812 | 30,584 | 3 | |
| Slot +5V fuse | SMD1206P075TFT (0.75 A PTC) | C545214 | 16,650 | 18 | 6 per main board |
| CPU socket | UMAX 3183-10112P1T, PCIe x8 98-pin, vertical THT | C404111 | 418 | 3 | THT with posts, which is mechanically robust |
| I/O slot socket | UMAX 3183-10200P1T, PCIe x1 36-pin, vertical THT | C404113 | 2,418 | 18 | 6 per main board. Same family and datasheet as the x8. |
| HDMI connector | HDMI 19PIN 043 (type A, SMD right angle) | C2858275 | 48,197 | 2 | |
| USB-A receptacle | USB-302S-T (SMD right angle) | C112455 | 3,794 | 2 | |
| Wi-Fi module | ESP32-C3-MINI-1U-N4 | C2911374 | 2,240 | 2 | Pre-certified, U.FL external antenna, so the RF can't be affected by our layout |
| Wi-Fi antenna (loose, not assembled) | KH-FPC2.4G-1.13IPEX-240 | C4943394 | 50 | 2 | Buy with the order and plug it in by hand |
| Wi-Fi card 3V3 LDO | AMS1117-3.3 | C6186 | 1,191,759 (basic) | 2 | |
| Slot control expanders | TCA9555PWR (16-bit I²C) | C465732 | 40,504 | 6 | 2 per main board: CARD_RST_n, PROG_n, PRSNT |
| Slot programming-port mux | CD74HC4051PWR (8:1 analog) | C352826 | 26,607 | 6 | 2 per main board: SWCLK, SWDIO |

All of the key parts above have a JLC minimum purchase of 1. The small parts
have a minimum of 2–5 plus 1–4 attrition spares, which costs cents.

## Risks and actions

1. **ROM stock.** The whole PLCC-32 SST39VF family at JLC is under 60 parts.
   JLC can buy parts into **your JLC parts inventory** ahead of the PCB
   order, which reserves them. Do that for 3–4 × C645939 (or C632851)
   once the specs are approved. Only you can do this, because it needs
   payment.
2. **FPGAs.** 5 × HX4K out of 51 in stock. Reserve them the same way.
3. **Datasheet checks:** still to do during schematic capture, when each
   footprint is imported:
   - the connector suffixes (-10112P1T / -10200P1T: plating and post style)
   - the HDMI connector's mechanical drawing against the card edge
   - the USB-A mechanical drawing against the card edge

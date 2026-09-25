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
**2 of each card** (CPU, system, GPU, IO, Wi-Fi) (JLC's minimum for assembly).
"Qty" is parts placed across all assembled boards, before JLC's attrition
extras. Stock checked 2026-09-23 (the power parts: 2026-09-24).

| Function | Part | LCSC | Stock | Qty | Board |
|---|---|---|---|---|---|
| Chipset FPGA **and** CPU card FPGA | ICE40HX4K-TQ144 | C1521989 | 51 | 5 | main, CPU |
| ROM | SST39VF040-70-4I-NHE (512 KB, PLCC-32) | C645939 | **11** | 3 | main. ⚠ low stock: fallbacks below |
| ROM (fallback) | SST39VF010-70-4I-NHE-T (128 KB, PLCC-32) | C632851 | 33 | | same footprint; A17/A18 NC, ROM_BANK 0–63, enough for boot + kernel |
| SRAM | IS62WV5128EBLL-45HLI (512K×8, 45 ns, sTSOP-32) | C1348955 | 224 | 3 | main; A16–A18 tied low |
| FPGA config flash | W25Q32JVSSIQ | C179173 | 25,178 | 5 | main (FL0), CPU (FL1) |
| 12 MHz clock | HSO321S 12 MHz 3.3 V CMOS oscillator | C160457 | 3,086 | 3 | main: CLK12 and CPU_CLK, 33 Ω each (cpu-bus.md) |
| Reset supervisor | MAX811TEUS+T (3.08 V, 140 ms, manual reset) | C7272 | 11,115 | 3 | main: nPOR; MR from the button and SYS_nRST |
| USB-C power policy | TLV7011DBVR comparator | C702117 | 6,161 | 3 | main: PWR_HI (a 3.0 A source) when CC ≥ ~1.30 V (`power.md`, POW-005) |
| 3V3 buck | TLV62569PDDCR (2 A, SOT-23-6, 106 °C/W) | C398365 | 16,188 | 3 | main: the DBV (188 °C/W) reaches 100 °C at 1.21 A of 3V3 (THM-001) |
| 1V2 LDO | RT9013-12GB (500 mA) | C58464 | 16,404 | 5 | main, CPU |
| Input eFuse | TPS259470ARPWR (2.7–23 V, 28 mΩ, adjustable limit, OVLO, dVdt) | C3662799 | 2,749 | 3 | main input: RILM 1.13 kΩ (2.63–3.21 A), OVLO 37.4k/10.0k 0.1 %, dVdt 680 pF. Fallback: the latch-off TPS259470LRPWR, C3662793 (2,832) |
| USB power switch | SY6280AAC | C55136 | 142,696 | 2 | IO card VBUS (the main input moved to the eFuse: the SY6280 can't pass the 3 A case) |
| USB-C receptacle | TYPE-C-31-M-12 (16P) | C165948 | 98,793 | 5 | main (power), system card (USB) |
| USB ESD | USBLC6-2SC6 | C7519 | 38,417 | 5 | main, system card, IO card |
| 5V TVS | SMF5.0A | C193402 | 582,382 | 3 | main |
| Input fuse | SMD1812P350TF/16 (3.5 A PTC, 16 V, 8–30 mΩ) | C46970911 | 310 | 3 | main. Fallback: SMD1812P350TF (6 V rating), C20815 (2,858) |
| Slot +5V fuse | SMD1206P110TFT (1.1 A PTC, 0.92 A hold at 40 °C, 0.04–0.21 Ω) | C143975 | 1,442 | 21 | main: 6 slots + system slot. Up from the 0.75 A part: the IO card's keyboard boost draws up to 0.75 A at the worst corner (POW-006 B10b) |
| IO card keyboard boost | TPS61023DRLR (sync boost, SOT-563), 1 µH FXL0420-1R0-M (C167203, 27 mΩ, Isat 7 A), 750k (C23240) / 100k (C25803) 1 % | C919459 | 14,097 | 2 | IO: holds the keyboard's VBUS at 5.06 V from a card +5V down to 3.9 V (POW-007); feeds the SY6280 port switch (`power.md`) |
| CPU socket | UMAX 3183-10112P1T, PCIe x8 98-pin, THT | C404111 | 418 | 3 | main |
| I/O slot socket | UMAX 3183-10200P1T, PCIe x1 36-pin, THT | C404113 | 2,418 | 18 | main |
| System slot socket | PCIE-64P11L, PCIe x4 64-pin, SMD with posts | C19188869 | 201 | 3 | main |
| Slot control expanders | TCA9555PWR | C465732 | 39,970 | 6 | main |
| Programming-port mux | CD74HC4051PWR | C352826 | 26,017 | 6 | main |
| Card MCUs and sysctl | RP2040 | C2040 | 74,212 | 6 | system, GPU, IO |
| MCU flash | W25Q16JVSSIQ | C131025 | 17,654 | 6 | one per RP2040 |
| 12 MHz crystal | X322512MSB4SI | C9002 | 74,175 (basic) | 6 | one per RP2040 |
| Wi-Fi card 3V3 buck | TLV62569DBVR (2 A), with a 2.2 µH FNR3015S2R2MT (C167747) | C141836 | 251,932 | 2 | Wi-Fi: an LDO failed the TX-burst and thermal checks (`hw/power`, POW-003, THM-001). The system, GPU and IO cards run from the slot's +3V3 (`power.md`). |
| HDMI connector | HDMI 19PIN 043 (type A, SMD right angle) | C2858275 | 47,920 | 2 | GPU |
| HDMI ESD | TPD4E05U06DQAR (4 lines) | C138714 | 182,893 | 4 | GPU: two, for the 8 TMDS lines |
| HDMI +5V boost | TPS61023DRLR, 1 µH FXL0420-1R0-M (C167203), 732k (C2849083) / 100k (C122538) 0.1 % | C919459 | 14,097 | 2 | GPU: the pin at 4.95 V (HDMI: 4.8–5.3 V) from a card +5V down to 3.75 V (POW-008); replaces the B5819W Schottky |
| HDMI +5V fuse | SMD0805P020TF (200 mA PTC, 0.5–3.5 Ω) | C20976 | 16,020 | 2 | GPU: ahead of the boost (POW-008); the 100 mA C20975 holds only 0.08 A at 40 °C there |
| USB-A receptacle | USB-302S-T (SMD right angle) | C112455 | 3,791 | 2 | IO |
| Wi-Fi module | ESP32-C3-MINI-1U-N4 | C2911374 | 2,225 | 2 | Wi-Fi |
| Wi-Fi MISO buffer | 74LVC1G125GW | C52140430 | 9,721 | 2 | Wi-Fi: releases MISO when not selected |
| Wi-Fi antenna lead (loose, not assembled) | KH-IPEX3-SMA-RG081-150mm, MHF III (IPEX gen 3) to SMA, 150 mm | C709347 | 162 | 2 | the module's receptacle is MHF III: a 1st-gen U.FL antenna (C4943394, first listed here) does not mate (MECH-007). Buy with the order, plug in by hand |
| Wi-Fi antenna (loose, not assembled) | HJ-2.4GHz-SMA, 2.45 GHz rubber duck | C1509156 | 329 | 2 | screws onto the lead's SMA; check the lead is SMA female (jack) and the antenna SMA male, not RP-SMA, when ordering |

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

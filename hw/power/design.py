#!/usr/bin/env python3
"""Power design values for CUPC/8 M1, with where each one comes from.

    python3 hw/power/design.py      list the assumptions the boards must meet

Every check in hw/power reads its numbers from here. Each value is one of:

  DS      a datasheet figure (the datasheet is named)
  SPEC    a USB / USB Type-C requirement
  BOARD   taken from a finished board script (hw/boards/*.py)
  ASSUME  not decided yet. The board named in the note must meet it; these
          are listed by running this file, and in doc/hardware/power.md.

Datasheets (fetched 2026-09-24): TLV62569 SLVSDG1C; RT9013 DS9013-09;
AMS1117 (Advanced Monolithic, LCSC C6186); SY6280 AN_SY6280 Rev 0.1;
TLV7011 SLVSDM5F; SMD1812P200TF16 (Ruilon); SMD1206P075TFT (PTTC); SMF5.0A
(MDD); ESP32-C3-MINI-1U datasheet v2.2; LM1117 SNOS412Q (for the 1117-class
load-step figure the AMS1117 datasheet lacks).
"""

AMBIENT_C = 40.0            # verification.md row 4.5
TJ_LIMIT_C = 100.0          # verification.md row 4.5

ASSUMPTIONS = []            # (board, text), filled by assume()


def assume(board, text, value):
    ASSUMPTIONS.append((board, text))
    return value


# ---------------------------------------------------------------------------
# USB-C source and cable (SPEC)
# ---------------------------------------------------------------------------
VBUS_MIN = 4.75             # SPEC vSafe5V at the source receptacle
VBUS_NOM = 5.00
VBUS_MAX = 5.50             # SPEC vSafe5V max (USB 2.0 alone: 5.25)
# SPEC Type-C cable IR drop at the cable's 3 A rating: <= 500 mV on VBUS and
# <= 250 mV on GND (USB Type-C spec, cable IR drop), as resistances
CABLE_R_VBUS = 0.500 / 3.0
CABLE_R_GND = 0.250 / 3.0
# Source classes, and the current each lets the sink draw (SPEC)
SOURCE_CLASSES = {"default USB 2.0": 0.5, "default USB 3.x": 0.9, "Type-C 1.5 A": 1.5, "Type-C 3.0 A": 3.0}
WIFI_MIN_CLASS = "Type-C 1.5 A"     # power.md policy: PWR_HI needed for the radio

# ---------------------------------------------------------------------------
# Main board input path: receptacle -> fuse -> TVS -> SY6280 -> 5V_SYS
# ---------------------------------------------------------------------------
R_RECEPTACLE = assume("main", "USB-C receptacle + VBUS/GND copper to the fuse: <= 20 mOhm loop", 0.020)
FUSE_IN_R_MIN, FUSE_IN_R_MAX = 0.020, 0.100     # DS SMD1812P200TF16: Rmin, R1max
FUSE_IN_IHOLD_40C = 1.80                        # DS derating chart, 40 C
TVS_VRWM, TVS_VBR_MIN, TVS_VCLAMP = 5.0, 6.4, 9.2   # DS SMF5.0A
SY6280_RON_TYP = 0.080                          # DS (typ only)
SY6280_RON_MAX = assume("main/IO", "SY6280 RDS(on) taken as 1.5 x the 80 mOhm typ (hot, no max in the datasheet)", 0.120)
SY6280_ILIM_K = 6800.0                          # DS: ILIM (A) = 6800 / RSET (ohm)
SY6280_ILIM_TOL = 0.25                          # DS: 0.75..1.25 A at RSET = 6.8k
SY6280_ILIM_PROG_MAX = 2.0                      # DS: highest programmable ILIM
SY6280_TON = 120e-6                             # DS turn-on time
SY6280_UVLO = 2.3                               # DS
SY6280_THETA_JA = 200.0                         # DS, JEDEC 51-3 (low-K board)
# power.md: "1.5 A limit". hw/power/budget.py shows why this is too low.
SY6280_MAIN_RSET = assume("main", "SY6280 RSET (power.md: 1.5 A limit -> 4.53 kOhm)", 4530.0)
R_5VSYS = assume("main", "5V_SYS copper, switch to the farthest slot / the buck: <= 20 mOhm", 0.020)
# capacitance directly on VBUS, ahead of the switch (the USB 2.0 10 uF rule)
C_VBUS_PRE = assume("main", "capacitance on VBUS ahead of the SY6280: 1 uF (<= 10 uF allowed)", 1.0e-6)

# ---------------------------------------------------------------------------
# Slot +5V feed: PTC -> 0 ohm link -> 50 mOhm sense -> 3 contacts -> card
# ---------------------------------------------------------------------------
SLOT_PTC_R_MIN, SLOT_PTC_R_MAX = 0.090, 0.290   # DS SMD1206P075TFT
SLOT_PTC_IHOLD_40C = 0.65                       # DS derating chart, 40 C
R_SLOT_LINK = assume("main", "slot 0 ohm isolation link: <= 50 mOhm (0 ohm jumper spec)", 0.050)
R_SLOT_SENSE = 0.050                            # power.md
R_SLOT_CONTACTS = assume("main/cards", "slot +5V: 3 contacts at <= 30 mOhm each, plus 10 mOhm card copper", 0.030 / 3 + 0.010)
SLOT_3V3_MAX = 0.300                            # slot.md
SLOT_CARD_MAX = 1.0                             # slot.md: <= 1 A per card, +5V and +3V3 together

# ---------------------------------------------------------------------------
# 3V3 buck: TLV62569DBV (TI model for dynamics)
# ---------------------------------------------------------------------------
BUCK_L = assume("main", "3V3 buck inductor 2.2 uH (TI's standard LC), Isat >= 2.5 A, DCR <= 50 mOhm", 2.2e-6)
BUCK_COUT = assume("main", "3V3 buck output: 22 uF X5R/X7R 10 V at the buck (TI table 4: 2.2 uH + 22 uF)", 22e-6)
BUCK_COUT_EFF = 0.6         # DC-bias derating of an 0805 22 uF at 3.3 V (TI table 4 allows -50%)
C_3V3_DECOUPLE_MIN = assume("main", "3V3 decoupling besides the buck's own 22 uF: >= 20 uF effective "
                            "(after DC-bias derating), spread over the loads", 20e-6)
BUCK_CIN = assume("main", "3V3 buck input: 10 uF at the VIN pin", 10e-6)
BUCK_R1, BUCK_R2 = assume("main", "3V3 feedback divider 453k / 100k (VOUT = 3.318 V)", (453e3, 100e3))
# 1 % resistors put the light-load (power-save) 3V3 9 mV over 3.465 V at the
# high corner (POW-001 P3/P5) and leave the MAX811T 29 mV (P1)
BUCK_RES_TOL = assume("main", "3V3 feedback divider resistors 0.1 % (1 % fails POW-001 P3/P5 by 6-9 mV)", 0.001)
BUCK_VFB_NOM, BUCK_VFB_TOL = 0.600, 0.020       # DS 0.588..0.612
BUCK_RHS, BUCK_RLS = 0.100, 0.060               # DS typ RDS(on)
BUCK_RDS_HOT = 1.4 * 1.2    # Tj 100 C (~1.4x) and process spread (1.2x): no max in the datasheet
BUCK_FSW = 1.5e6            # DS
BUCK_T_EDGE = 5e-9          # switching-loss estimate: 5 ns per edge
BUCK_IQ_LOSS = 0.010        # gate drive + control, W (estimate)
BUCK_THETA_JA = {"DBV": 188.2, "DDC": 106.2, "DRL": 146.3}  # DS
BUCK_PACKAGE = "DBV"        # parts.md: TLV62569DBVR
BUCK_DCR = 0.050
BUCK_ETA_BUDGET = 0.90      # 5 V -> 3.3 V: DS figure 9 shows 94-95 % from 0.1 to 1 A;
                            # 0.90 leaves room for hot RDS(on) and a cheaper inductor

# 3V3 rail: the tightest loads
V3V3_MIN = 3.135            # 3.3 V - 5 %: iCE40 VCCIO (3.3 V LVCMOS), RP2040 USB_VDD >= 3.0
V3V3_MAX = 3.465
MAX811T_VTH_MAX = 3.17      # MAX811T reset threshold, -40..85 C: 2.98-3.17 V. From the ADI
                            # datasheet table; not re-fetched (LCSC and ADI unavailable 2026-09-24)
MAX811_GLITCH_S = 10e-6     # dips shorter than this don't reset it. ASSUMED: the datasheet's
                            # transient-immunity curve (tens of us at small overdrive) not re-fetched

# ---------------------------------------------------------------------------
# 1V2 LDO: RT9013-12 (main board chipset core; the CPU card has its own)
# ---------------------------------------------------------------------------
RT9013 = dict(VSET=1.2, TSS=100e-6, DROP0=0.0, RDROP=0.400 / 0.5, ILIM=0.5, IQ=50e-6,
              # DS PSRR figure: -50 dB flat to ~10 kHz, then +20 dB/decade
              PSRR_DC=10 ** (-50 / 20), F_PSRR=10e3, VIN_NOM=3.3,
              # fitted to the DS load-step figure (RT9013-15, 10 -> 300 mA, 1 uF
              # ceramic: -25 mV); the fit gives -26 mV (hw/power/ldo.py re-checks it)
              RDC=0.010, LEQ=0.1e-6, RP=0.15)
RT9013_TOL = 0.02           # DS output accuracy
RT9013_THETA_JA = 250.0     # DS SOT-23-5
RT9013_COUT = assume("main/CPU", "1V2 LDO output: 1 uF at the LDO + 4 x 100 nF at the iCE40 VCC pins", 1.0e-6 + 4 * 100e-9)
V1V2_MIN, V1V2_MAX = 1.14, 1.26                 # iCE40 HX VCC recommended range
# the 3V3 ripple the 1V2 LDO sees: (Hz, Vpp). POW-001 measures 10-17 mVpp at
# 17-30 kHz in power-save (10 mA) and 1.5-1.6 mVpp at 1.1-1.4 MHz in PWM;
# these are those with a 2-3x allowance
BUCK_RIPPLE = [(17e3, 0.030), (30e3, 0.030), (1.1e6, 0.005), (1.5e6, 0.005)]
I_1V2_MAX = 0.040                               # power.md (chipset core)

# ---------------------------------------------------------------------------
# Card 3V3 LDO: AMS1117-3.3 (Wi-Fi card: BOARD hw/boards/wifi.py)
# ---------------------------------------------------------------------------
AMS1117_VOUT_MIN, AMS1117_VOUT_NOM = 3.201, 3.300   # DS over line, load and temperature
AMS1117 = dict(VSET=3.3, TSS=20e-6,
               # dropout: DS gives only 1.1 typ / 1.3 V max at 0.8 A, "decreasing at lower
               # currents"; the LM1117's typical curve (1.00 V at 0 A to 1.16 V at 0.8 A)
               # scaled to meet 1.3 V at 0.8 A: 1.12 V + 0.225 ohm
               DROP0=1.12, RDROP=0.225,
               ILIM=0.9,                    # DS minimum current limit
               IQ=11e-3,                    # DS max quiescent
               PSRR_DC=10 ** (-60 / 20), F_PSRR=1e3, VIN_NOM=5.0,  # DS 60 dB min at 120 Hz
               # fitted to LM1117 figure 7-8 (0.1 -> 0.5 A, 10 uF tantalum at the
               # 0.3 ohm minimum ESR TI allows: -0.13 V at ~2 us, settled by ~5 us).
               # The fit matches the peak (-0.124 V) and recovers ~3x slower than
               # the figure, which errs on the safe side for a droop check.
               RDC=0.004, LEQ=2e-6, RP=2.0)
AMS1117_THETA_JA = 90.0     # DS SOT-223 (46..90 by copper; table 1: 65 with 225 mm^2 top + plane)
WIFI_CIN = 22e-6            # BOARD wifi.py C1
WIFI_COUT = 22e-6           # BOARD wifi.py C2 (0805 22 uF, derated below)
WIFI_COUT_HF = 100e-9       # BOARD wifi.py C3
CERAMIC_DERATE = 0.6        # DC bias at 3.3-5 V on 0805 22 uF parts
ESP32_VDD_MIN = 3.0         # DS ESP32-C3-MINI-1U: 3.0..3.6 V
ESP32_I_TX = 0.350          # DS: 802.11b 20.5 dBm, rated at 100 % duty
ESP32_I_IDLE = 0.010        # a light-sleep / idle floor for the step (DS: RX is 82 mA)
ESP32_SUPPLY_MIN = 0.5      # DS: supply must deliver >= 0.5 A
WIFI_I_LEDS = 0.0013 + 0.006 + 0.001   # power LED (1k), link LED (100 ohm), EN/strap pull-ups

# ---------------------------------------------------------------------------
# Loads (power.md budget, max column), in A
# ---------------------------------------------------------------------------
LOADS_3V3 = {
    "chipset iCE40 I/O": 0.040,
    "CPU card iCE40 core + I/O": 0.040,
    "SRAM": 0.022,
    "ROM": 0.030,
    "W25Q32": 0.015,
    "sysctl RP2040 + flash": 0.050,
    "GPU card RP2040 + flash": 0.100,
    "GPU card TMDS": 0.045,
    "IO card RP2040 + flash": 0.050,
    "I2C expanders, SWD mux": 0.005,
    "LEDs": 0.030,
    "1V2 LDO (chipset core)": I_1V2_MAX,
}
I_KEYBOARD = 0.500          # USB 2.0 high-power device (IO card's switch limits it)
I_HDMI_5V = 0.055           # HDMI +5V pin, per spec
I_WIFI_5V = ESP32_I_TX + WIFI_I_LEDS + AMS1117["IQ"]     # the Wi-Fi card from slot +5V
FUTURE_SLOTS = 3            # slots 4-6

# Capacitance on 5V_SYS, charged through the SY6280 at attach
C_5VSYS = [
    ("main 5V_SYS bulk", assume("main", "5V_SYS bulk: 22 uF", 22e-6)),
    ("3V3 buck input", BUCK_CIN),
    ("Wi-Fi card C1", WIFI_CIN),                                   # BOARD
    ("IO card VBUS switch input", assume("IO", "IO card +5V input capacitance: <= 10 uF", 10e-6)),
    ("GPU card +5V", assume("GPU", "GPU card +5V capacitance: <= 10 uF", 10e-6)),
    ("system card +5V", assume("system", "system card +5V capacitance: <= 10 uF", 10e-6)),
]
C_3V3_TOTAL = assume("main/cards", "total 3V3 capacitance (buck output + all decoupling): <= 100 uF", 100e-6)

# ---------------------------------------------------------------------------
# USB-C CC: Rd, the PWR_HI comparator, the sysctl ADC (SPEC + ASSUME)
# ---------------------------------------------------------------------------
RD = 5100.0
RD_TOL = assume("main", "CC Rd 5.1 kOhm 1%", 0.01)
# Source advertisement (SPEC, USB Type-C Rp): current source (A, tol) or
# pull-up (ohm, tol, to 5 V or 3.3 V)
RP_SOURCES = {
    "default": [("I", 80e-6, 0.20), ("R5", 56e3, 0.20), ("R3", 36e3, 0.20)],
    "1.5A": [("I", 180e-6, 0.08), ("R5", 22e3, 0.05), ("R3", 12e3, 0.05)],
    "3.0A": [("I", 330e-6, 0.08), ("R5", 10e3, 0.05), ("R3", 4.7e3, 0.05)],
}
RP_PULLUP = {"R5": (4.75, 5.50), "R3": (3.135, 3.465)}
# SPEC sink-side vRd ranges (Type-C, Rd = 5.1 kOhm) and the detection thresholds
VRD_RANGES = {"default": (0.25, 0.61), "1.5A": (0.70, 1.16), "3.0A": (1.31, 2.04)}
VRD_THRESH = {"connect": 0.20, "1.5A": 0.66, "3.0A": 1.23}
# PWR_HI comparator: one TLV7011 for both CC lines, so CC1 and CC2 are
# averaged through two equal resistors (the unused CC sits at 0 V on its Rd);
# the reference is half of 0.66 V from 3V3
CC_AVG_R = assume("main", "PWR_HI: CC1, CC2 -> 1 MOhm 1% each -> TLV7011 IN+ (averaged)", 1.0e6)
CC_REF_R = assume("main", "PWR_HI reference: 3V3 -> 90.9k / 10k 1% -> IN- (0.330 V)", (90.9e3, 10.0e3))
CC_REF_TOL_R = 0.01
TLV7011_VIO = 0.008         # DS max
TLV7011_VHYS = (0.0012, 0.014)  # DS min, max
# sysctl ADC (RP2040 on the system card)
ADC_VREF_TOL = assume("system", "system card RP2040 ADC reference = its 3.3 V rail, +-3 %", 0.03)
ADC_ERR_V = assume("system", "RP2040 ADC offset + INL + DNL (errata E11): <= 12 LSB = 10 mV", 12 * 3.3 / 4096)
ADC_LEAK = 1e-6             # RP2040 GPIO/ADC pin leakage, max (loads the CC line)


def buck_vout(r1=None, r2=None, vfb=BUCK_VFB_NOM):
    r1, r2 = r1 or BUCK_R1, r2 or BUCK_R2
    return vfb * (1 + r1 / r2)


def buck_vout_range():
    """3V3 DC extremes: VFB tolerance and the divider's resistor tolerance."""
    lo = buck_vout(BUCK_R1 * (1 - BUCK_RES_TOL), BUCK_R2 * (1 + BUCK_RES_TOL), BUCK_VFB_NOM * (1 - BUCK_VFB_TOL))
    hi = buck_vout(BUCK_R1 * (1 + BUCK_RES_TOL), BUCK_R2 * (1 - BUCK_RES_TOL), BUCK_VFB_NOM * (1 + BUCK_VFB_TOL))
    return lo, hi


def sy6280_ilim(rset=SY6280_MAIN_RSET):
    nom = SY6280_ILIM_K / rset
    return nom * (1 - SY6280_ILIM_TOL), nom, nom * (1 + SY6280_ILIM_TOL)


def main():
    print("Values the boards must meet (hw/power/design.py):")
    for board, text in ASSUMPTIONS:
        print("  %-11s %s" % (board, text))


if __name__ == "__main__":
    main()

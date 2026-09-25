#!/usr/bin/env python3
"""Power design values for CUPC/8 M1, with where each one comes from.

    python3 hw/power/design.py      list the assumptions the boards must meet

Every check in hw/power reads its numbers from here. Each value is one of:

  DS      a datasheet figure (the datasheet is named)
  SPEC    a USB / USB Type-C requirement
  BOARD   taken from a finished board script (hw/boards/*.py)
  ASSUME  not decided yet. The board named in the note must meet it; these
          are listed by running this file, and in doc/hardware/power.md.

Datasheets (fetched 2026-09-24): TLV62569 SLVSDG1C (the main board's 3V3
and the Wi-Fi card's); RT9013 DS9013-09; SY6280 AN_SY6280 Rev 0.1;
TLV7011 SLVSDM5F; SMD1812P350TF (Ruilon); SMD1206P110TFT (PTTC); SMF5.0A
(MDD); ESP32-C3-MINI-1U datasheet v2.2; TPS25947 SLVSFC9C; TPS61023 SLVSF14B
(2026-09-25).
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
# power.md policy (David, 2026-09-24): the full machine needs a 3.0 A source.
# PWR_HI = "Type-C 3.0 A"; below it the radio stays off and SD writes are refused
FULL_CLASS = "Type-C 3.0 A"
REDUCED_CLASS = "Type-C 1.5 A"      # what a 1.5 A source must still run: radio off, no SD writes

# ---------------------------------------------------------------------------
# Main board input path: receptacle -> PTC -> TVS -> eFuse (TPS25947) -> 5V_SYS
# The SY6280 (limit at most 2.5 A, +-25 %) can't pass the 3 A case with
# margin, so the input switch is a TI TPS259470ARPWR eFuse (C3662799, 2,749
# at JLC 2026-09-24; the latch-off TPS259470LRPWR C3662793 is the fallback).
# DS SLVSFC9C (sha256 8f96de38...), fetched 2026-09-24.
# ---------------------------------------------------------------------------
R_RECEPTACLE = assume("main", "USB-C receptacle + VBUS/GND copper to the fuse: <= 20 mOhm loop", 0.020)
# input PTC: SMD1812P350TF/16 (Ruilon, C46970911, 310 at JLC; the 6 V
# SMD1812P350TF C20815, 2,858, is the fallback). Rmin/R1max from the LCSC
# listing; the 40 C hold uses the Ruilon family's 90 % derating (P200: 1.80/2.00)
FUSE_IN = assume("main", "input PTC SMD1812P350TF/16 (C46970911): 3.5 A hold, 8-30 mOhm, 16 V", "SMD1812P350TF/16")
FUSE_IN_R_MIN, FUSE_IN_R_MAX = 0.008, 0.030
FUSE_IN_IHOLD_40C = 3.5 * 0.90
TVS_VRWM, TVS_VBR_MIN, TVS_VCLAMP = 5.0, 6.4, 9.2   # DS SMF5.0A (C193402)
INSW_PART = assume("main", "input switch TPS259470ARPWR eFuse (C3662799), EN/UVLO tied to IN", "TPS259470ARPWR")
INSW_RON_TYP, INSW_RON_MAX = 0.0283, 0.045      # DS: 28.3 mOhm typ, 45 mOhm max over -40..125 C
INSW_ILIM_K = 3340.0        # DS table: ILIM ~ 3340 / RILM (1.007 A at 3.32k, 2.028 at 1.65k, 4.452 at 750)
INSW_ILIM_TOL = (0.112, 0.087)  # DS: 1.800..2.200 A at 1.65k and 3.96..4.84 at 750 ohm (-11.2 %, +8.7 %)
# RILM: the limit's max stays under 3.3 A (a 3.0 A source + 10 %), its min
# well over the machine's worst case (budget.py B2)
INSW_RILM = assume("main", "eFuse RILM 1.13 kOhm 1 % (limit 2.63 / 2.96 / 3.21 A min/nom/max)", 1130.0)
INSW_THETA_JA = 74.5        # DS RPW, JEDEC board (41.7 on TI's EVM)
# OVLO: IN -> R1 -> OVLO -> R2 -> GND; trips at 1.2 V (1.183..1.223) x (R1 + R2) / R2.
# Must stay above vSafe5V max and below the 6 V absolute maximum of what 5V_SYS feeds
# (TLV62569 VIN, the IO card's SY6280)
INSW_OVLO_R = assume("main", "eFuse OVLO divider 37.4k / 10.0k 0.1 % from IN (1 % puts the trip up to "
                     "6.00 V; see budget.py B20)", (37.4e3, 10.0e3))
INSW_OVLO_TOL = 0.001
INSW_OVLO_VTH = (1.183, 1.223)
DOWNSTREAM_ABS_MAX = 6.0    # DS TLV62569, SY6280: VIN absolute maximum
# dVdt: SR (V/ms) = 2000 / CdVdt (pF), with the pin current's spread
# (0.81..3.82 uA around 2.21 typ) scaling it
INSW_CDVDT = assume("main", "eFuse dVdt capacitor 680 pF (5V_SYS rises at 1.1..5.1 V/ms)", 680e-12)
INSW_IDVDT = (0.81e-6, 2.21e-6, 3.82e-6)
INSW_UVLO = 2.7             # DS: input UVLO (EN/UVLO tied to IN)
R_5VSYS = assume("main", "5V_SYS copper, eFuse to the farthest slot / the buck: <= 20 mOhm", 0.020)
# capacitance directly on VBUS, ahead of the switch (the USB 2.0 10 uF rule)
C_VBUS_PRE = assume("main", "capacitance on VBUS ahead of the eFuse: 1 uF (<= 10 uF allowed)", 1.0e-6)

# SY6280: now only the IO card's keyboard port switch (500 mA)
SY6280_RON_TYP = 0.080                          # DS (typ only)
SY6280_RON_MAX = assume("IO", "SY6280 RDS(on) taken as 1.5 x the 80 mOhm typ (hot, no max in the datasheet)", 0.120)
SY6280_THETA_JA = 200.0                         # DS, JEDEC 51-3 (low-K board)

# ---------------------------------------------------------------------------
# Slot +5V feed: PTC -> 0 ohm link -> 50 mOhm sense -> 3 contacts -> card
# ---------------------------------------------------------------------------
# The IO card's keyboard boost draws up to ~0.72 A at the worst corner, over
# the 0.75 A PTC's 0.65 A hold at 40 C, so the slot PTC goes up one size
# (all slots are alike). PTTC SMD1206P110TFT (C143975): hold 1.10 A (0.92 A at
# 40 C), R 0.040..0.210 ohm, same 1206 footprint and family as before
SLOT_PTC = assume("main", "slot +5V PTCs SMD1206P110TFT (C143975, 1.1 A; was SMD1206P075TFT)", "SMD1206P110TFT")
SLOT_PTC_R_MIN, SLOT_PTC_R_MAX = 0.040, 0.210   # DS
SLOT_PTC_IHOLD_40C = 0.92                       # DS derating chart, 40 C
R_SLOT_LINK = assume("main", "slot 0 ohm isolation link: <= 50 mOhm (0 ohm jumper spec)", 0.050)
R_SLOT_SENSE = 0.050                            # power.md
R_SLOT_CONTACTS = assume("main/cards", "slot +5V: 3 contacts at <= 30 mOhm each, plus 10 mOhm card copper", 0.030 / 3 + 0.010)
SLOT_3V3_MAX = 0.300                            # slot.md: <= 300 mA of +3V3 per card
SLOT_5V_MAX = 0.80                              # slot.md: <= 0.80 A of +5V per card (David, 2026-09-24; was 0.55)

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
# the DBV (SOT-23-5) reaches 100 C at 1.21 A of 3V3 (THM-001); the machine can
# ask for 1.22 A with slots 5-6 at their 300 mA each
BUCK_PACKAGE = assume("main", "3V3 buck TLV62569PDDCR (C398365, SOT-23-6, 106 C/W; PG pin unused or to sysctl)",
                      "DDC")
WIFI_BUCK_PACKAGE = "DBV"   # BOARD wifi.py U2: TLV62569DBVR
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
# Wi-Fi card 3V3 buck: TLV62569DBV, the main board's part (BOARD hw/boards/wifi.py U2)
# ---------------------------------------------------------------------------
WIFI_BUCK_L = 2.2e-6        # BOARD wifi.py L1, FNR3015S2R2MT (C167747, CJiang, not Sunlord)
# L1 per LCSC's C167747 listing: 2.2 uH +-20 %, Isat 2 A, rated 2 A, DCR 78 mOhm.
# Not yet read from CJiang's own datasheet (LCSC and oneyac blocked 2026-09-24),
# so it stays an assumption; Isat 2 A against a 0.36 A load (+ ~0.2 A ripple)
WIFI_BUCK_DCR = assume("Wi-Fi", "buck inductor L1 (FNR3015S2R2MT): DCR 78 mOhm, Isat 2 A (LCSC listing; "
                       "CJiang datasheet not yet read)", 0.078)
WIFI_BUCK_R1, WIFI_BUCK_R2 = 453e3, 100e3       # BOARD wifi.py R9 / R10 (VOUT = 3.318 V)
# R10 C25803 is UNI-ROYAL 0603WAF1003T5E (the WAF series is +-1 %). R9 C25818
# is assumed to be the same series (0603WAF4533T5E): not yet confirmed
WIFI_BUCK_RES_TOL = assume("Wi-Fi", "buck feedback R9 (C25818) 1 %, as R10 (C25803, UNI-ROYAL 0603WAF, 1 %)", 0.01)
WIFI_CIN = 22e-6            # BOARD wifi.py C1
WIFI_COUT = 22e-6           # BOARD wifi.py C2 (0805 22 uF, derated below)
WIFI_COUT_HF = 100e-9       # BOARD wifi.py C3
# what the values above say hw/boards/wifi.py places: wifi_board_mismatches()
# fails POW-003 and THM-001 if the board script no longer agrees
WIFI_BOARD = {"U2": "TLV62569DBVR", "L1": "2.2u", "R9": "453k", "R10": "100k",
              "C1": "22u", "C2": "22u", "C3": "100n"}
CERAMIC_DERATE = 0.6        # DC bias at 3.3-5 V on 0805 22 uF parts
ESP32_VDD_MIN, ESP32_VDD_MAX = 3.0, 3.6     # DS ESP32-C3-MINI-1U
ESP32_I_TX = 0.350          # DS: 802.11b 20.5 dBm, rated at 100 % duty
ESP32_I_IDLE = 0.010        # a light-sleep / idle floor for the step (DS: RX is 82 mA)
ESP32_SUPPLY_MIN = 0.5      # DS: supply must deliver >= 0.5 A
WIFI_I_LEDS = 0.0013 + 0.006 + 0.001   # power LED (1k), link LED (100 ohm), EN/strap pull-ups
WIFI_I_3V3 = ESP32_I_TX + WIFI_I_LEDS   # the Wi-Fi card's 3V3 load, TX at 100 % duty

# ---------------------------------------------------------------------------
# IO card keyboard port: slot +5V -> TPS61023 boost -> SY6280 (500 mA, FLT to
# GPIO8) -> USB-A VBUS. Without the boost the port sat at 3.97 V at the worst
# corner (USB 2.0 wants >= 4.40 V at a low-power port). The IO board agent
# builds this circuit (power.md, "IO card keyboard boost").
# DS TPS61023 SLVSF14B (sha256 a3359fee...), model SLVMD68A (fetch.py).
# ---------------------------------------------------------------------------
IOB_PART = assume("IO", "keyboard-port boost TPS61023DRLR (C919459), EN to the card's +5V", "TPS61023DRLR")
IOB_L = assume("IO", "boost inductor 1 uH FXL0420-1R0-M (C167203): 27 mOhm, Isat 7 A (over the 3.7 A "
               "valley limit into a fault)", 1.0e-6)
IOB_L_DCR = 0.027
IOB_CIN = assume("IO", "boost input 10 uF 25 V 0805 (C15850) at VIN", 10e-6)
IOB_COUT = assume("IO", "boost output 2 x 22 uF 25 V 0805 (C45783), then the SY6280", 2 * 22e-6)
IOB_R1, IOB_R2 = assume("IO", "boost feedback 750k (C23240) / 100k (C25803) 1 %: 5.06 V", (750e3, 100e3))
IOB_RES_TOL = 0.01
IOB_VREF = (0.580, 0.595, 0.610)                # DS, PWM mode
IOB_RHS, IOB_RLS = 0.068, 0.047                 # DS typ RDS(on) at VOUT = 5 V
IOB_ILIM_VALLEY_MIN = 2.7                       # DS
IOB_VIN_MAX, IOB_VIN_ABS = 5.5, 6.0             # DS recommended, absolute max (VIN, SW, VOUT)
IOB_OVP_MIN = 5.5                               # DS: stops switching above 5.5..6.0 V
IOB_THETA_JA = 142.7                            # DS SOT-563, JEDEC
IOB_ETA = 0.91              # DS figure 6-1: 96-97 % at 0.5 A from 3.6-4.2 V to 5 V, less 5 points (as the buck)
USB_PORT_MIN = 4.40         # SPEC USB 2.0 low-power port (a high-power port: 4.75 V)
USB_PORT_MAX = VBUS_MAX     # SPEC vSafe5V max (USB 2.0 alone: 5.25 V)

# ---------------------------------------------------------------------------
# GPU card HDMI +5V pin (David, 2026-09-25): a TPS63802 buck-boost from the
# slot's +5V, feeding HDMI pin 18. As built (+5V -> 100 mA PTC -> B5819W ->
# pin) the pin was 3.73 V at the worst corner. A TPS61023 boost (POW-008's
# first version) passed its input through above its set point and put the pin
# at 5.40 V from a 5.5 V source; the buck-boost regulates both ways.
# DS TPS63802 SLVSEU9D (sha256 be07deca...), fetched 2026-09-25.
# ---------------------------------------------------------------------------
HDMI_PIN_MIN, HDMI_PIN_MAX = 4.8, 5.3           # SPEC HDMI: +5V power at the source, 4.8..5.3 V
I_HDMI_PIN = 0.055                              # SPEC HDMI: the source supplies >= 55 mA
# the card's PTCs (Ruilon, DS sha256 7ac532af..., fetched 2026-09-25):
#   (name, LCSC, Rmin, R1max, hold at 40 C)
GPU_PTCS = {
    "P010": ("SMD0805P010TF", "C20975", 0.75, 6.0, 0.08),     # on the card as built
    "P020": ("SMD0805P020TF", "C20976", 0.50, 3.5, 0.17),
}
GPU_PTC = assume("GPU", "HDMI +5V: slot +5V -> PTC SMD0805P020TF (C20976) -> TPS63802DLAR -> pin 18; "
                 "no Schottky (the TPS63802 disconnects its output when off)", "P020")
GPU_PTC_POS = "ahead"       # of the converter: POW-008 shows why not after it
GPUB_PART = assume("GPU", "HDMI +5V buck-boost TPS63802DLAR (C2845237), EN to its VIN, MODE to GND "
                   "(power save: it never sinks current from the pin)", "TPS63802DLAR")
GPUB_L = assume("GPU", "buck-boost inductor 0.47 uH FXL0420-R47-M (C167200): 14 mOhm, Isat 9.5 A "
                "(over the 5.75 A boost-mode peak limit)", 0.47e-6)
GPUB_L_DCR = 0.014
GPUB_CIN = assume("GPU", "buck-boost input 10 uF 25 V 0805 (C15850) at VIN", 10e-6)
GPUB_COUT = assume("GPU", "buck-boost output 2 x 22 uF 25 V 0805 (C45783): TI asks 2 x 22 uF above 3.6 V",
                   2 * 22e-6)
GPUB_R1, GPUB_R2 = assume("GPU", "buck-boost feedback 825k (C25823) / 91k (C23265) 1 %: 5.03 V", (825e3, 91e3))
GPUB_RES_TOL = 0.01
GPUB_VFB = (0.495, 0.500, 0.505)                # DS: 500 mV +-1 % (PWM mode)
# DS figure 10-21 (0.1 -> 1 A, power save allowed): a ~50 mVpp band at light
# load; the DC range is widened by half of it each way
GPUB_PFM_RIPPLE = 0.050
GPUB_VIN_OVP = (5.5, 5.7, 5.9)                  # DS: input over-voltage (VIN rising): the device stops
GPUB_VIN_MIN = 1.3                              # DS input range 1.3..5.5 V
GPUB_THETA_JA = 81.0                            # DS VSON-10
GPUB_ETA = 0.80             # at 55 mA in power save: DS curves ~88-90 %, less a generous allowance
# the behavioural model (models/behavioural.lib BB_BEH), fitted to DS figure
# 10-21 (0.1 -> 1 A, 15 uF effective: -130 mV, ~20 mV left at 50 us); the fit
# gives -148 mV and 23 mV, a little worse than the figure
GPUB_BEH = dict(TSS=500e-6, IQ=11e-6, RDC=0.005, LEQ=4e-6, RP=0.2)

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
    "storage card RP2040 + flash": 0.050,       # power.md / storage-card.md
    "storage card microSD (writing)": 0.100,    # storage-card.md: up to ~100 mA writing
    "I2C expanders, SWD mux": 0.005,
    "LEDs": 0.030,
    "1V2 LDO (chipset core)": I_1V2_MAX,
}
# power.md's Typ column, same rows: what B6/B7 check on a default USB source
LOADS_3V3_TYP = {
    "chipset iCE40 I/O": 0.015, "CPU card iCE40 core + I/O": 0.015, "SRAM": 0.010, "ROM": 0.010,
    "W25Q32": 0.002, "sysctl RP2040 + flash": 0.025, "GPU card RP2040 + flash": 0.060,
    "GPU card TMDS": 0.030, "IO card RP2040 + flash": 0.025, "storage card RP2040 + flash": 0.025,
    "storage card microSD (writing)": 0.005, "I2C expanders, SWD mux": 0.001, "LEDs": 0.015,
    "1V2 LDO (chipset core)": 0.015,
}
I_KEYBOARD_TYP = 0.100      # power.md Typ: an ordinary keyboard
I_HDMI_5V_TYP = 0.010       # power.md Typ
# the graphics slot holds the HDMI card or the e-ink card (type $01 either
# way); the budget carries the HDMI card, the heavier of the two
GPU_CARD_3V3 = LOADS_3V3["GPU card RP2040 + flash"] + LOADS_3V3["GPU card TMDS"]
EINK_CARD_3V3 = 0.095       # proposals/eink-gpu.md: ~45 mA typ, ~95 mA max, nothing from +5V
STORAGE_CARD_3V3 = LOADS_3V3["storage card RP2040 + flash"] + LOADS_3V3["storage card microSD (writing)"]
I_SD_WRITE = LOADS_3V3["storage card microSD (writing)"]
I_KEYBOARD = 0.500          # USB 2.0 high-power device (IO card's switch limits it)

FUTURE_SLOTS = 2            # slots 5-6 (slot 4 holds the storage card in M1)

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
# averaged through two equal resistors (the unused CC sits at 0 V on its Rd).
# PWR_HI means a 3.0 A source (power.md policy), so it trips between the 1.5 A
# and 3.0 A ranges. With our 1 % Rd those are 1.090 V max and 1.524 V min
# (cc.py); the reference puts the trip near their middle (1.30 V on CC, 0.648
# V at the comparator) rather than at the spec's 1.23 V, which sits closer to
# the 1.5 A side. The sysctl ADC keeps the spec's 1.23 V.
CC_AVG_R = assume("main", "PWR_HI: CC1, CC2 -> 1 MOhm 1% each -> TLV7011 IN+ (averaged)", 1.0e6)
CC_REF_R = assume("main", "PWR_HI reference: 3V3 -> 41.2k / 10.0k 1% -> IN- (0.648 V: PWR_HI = 3.0 A source)",
                  (41.2e3, 10.0e3))
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


def buck_vout_range(r1=None, r2=None, tol=None):
    """3V3 DC extremes: VFB tolerance and the divider's resistor tolerance.
    The main board's buck by default; the Wi-Fi card's with its own values."""
    r1, r2 = r1 or BUCK_R1, r2 or BUCK_R2
    tol = BUCK_RES_TOL if tol is None else tol
    lo = buck_vout(r1 * (1 - tol), r2 * (1 + tol), BUCK_VFB_NOM * (1 - BUCK_VFB_TOL))
    hi = buck_vout(r1 * (1 + tol), r2 * (1 - tol), BUCK_VFB_NOM * (1 + BUCK_VFB_TOL))
    return lo, hi


def wifi_vout_range():
    return buck_vout_range(WIFI_BUCK_R1, WIFI_BUCK_R2, WIFI_BUCK_RES_TOL)


def wifi_board_mismatches():
    """[(ref, value here, value in hw/boards/wifi.py)] for each WIFI_BOARD part
    whose value in the board script differs (None: not on the board)."""
    import os
    import re
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "boards", "wifi.py")
    # s.add(lib_id, ref, value, ...) and passive(kind, ref, value, ...)
    placed = dict(re.findall(r'(?:s\.add|passive)\(\s*"[^"]*",\s*"([A-Z]+\d+)",\s*"([^"]+)"', open(path).read()))
    return [(ref, want, placed.get(ref)) for ref, want in sorted(WIFI_BOARD.items()) if placed.get(ref) != want]


def wifi_i_5v(v_card, i3=WIFI_I_3V3):
    """The Wi-Fi card's draw from the slot's +5V, given the voltage that
    reaches it: its buck at the budget efficiency and its DC high output."""
    return i3 * wifi_vout_range()[1] / (BUCK_ETA_BUDGET * v_card)


def gpub_vout_range():
    """The GPU card's buck-boost output (min, nom, max): VFB +-1 % and its 1 %
    divider, widened by half the power-save ripple band each way."""
    r1, r2, t = GPUB_R1, GPUB_R2, GPUB_RES_TOL
    h = GPUB_PFM_RIPPLE / 2
    return (GPUB_VFB[0] * (1 + r1 * (1 - t) / (r2 * (1 + t))) - h, GPUB_VFB[1] * (1 + r1 / r2),
            GPUB_VFB[2] * (1 + r1 * (1 + t) / (r2 * (1 - t))) + h)


def iob_vout_range():
    """The keyboard boost's regulated output (min, nom, max): VREF and its 1 % divider."""
    r1, r2, t = IOB_R1, IOB_R2, IOB_RES_TOL
    return (IOB_VREF[0] * (1 + r1 * (1 - t) / (r2 * (1 + t))), IOB_VREF[1] * (1 + r1 / r2),
            IOB_VREF[2] * (1 + r1 * (1 + t) / (r2 * (1 - t))))


def iob_i_in(v_in, i_out):
    """The boost's input current for i_out: at its highest set point (the most
    it draws), or i_out itself in pass-through (v_in above the set point)."""
    vset = iob_vout_range()[2]
    return i_out if v_in >= vset * 1.01 else vset * i_out / (IOB_ETA * v_in)


def gpu_i_5v(v_card, i_pin=I_HDMI_PIN, worst=True):
    """The GPU card's +5V draw for its HDMI pin: through the PTC (ahead of the
    buck-boost) and the buck-boost at its highest output. Returns (current,
    the buck-boost's input voltage)."""
    r = GPU_PTCS[GPU_PTC][3 if worst else 2]
    vout = gpub_vout_range()[2]
    i = 0.0
    for _ in range(40):
        v_b = v_card - i * r
        i = vout * i_pin / (GPUB_ETA * max(v_b, 0.5))
    return i, v_card - i * r


def iob_vout(v_in, i_out, corner):
    """The output side of the boost: regulated at the corner's set point, or
    v_in less the inductor and high-side drop in pass-through."""
    lo, nom, hi = iob_vout_range()
    vset = {"lo": lo, "nom": nom, "hi": hi}[corner]
    through = v_in - i_out * (IOB_L_DCR + IOB_RHS * BUCK_RDS_HOT)
    return max(vset, through) if v_in >= vset * 1.01 else vset


def insw_ilim(rilm=None):
    """The eFuse's current limit (min, nom, max) for an RILM."""
    nom = INSW_ILIM_K / (rilm or INSW_RILM)
    return nom * (1 - INSW_ILIM_TOL[0]), nom, nom * (1 + INSW_ILIM_TOL[1])


def insw_ovlo():
    """The eFuse's OVLO trip range (V): threshold spread and divider tolerance."""
    r1, r2 = INSW_OVLO_R
    t = INSW_OVLO_TOL
    lo = INSW_OVLO_VTH[0] * (r1 * (1 - t) + r2 * (1 + t)) / (r2 * (1 + t))
    hi = INSW_OVLO_VTH[1] * (r1 * (1 + t) + r2 * (1 - t)) / (r2 * (1 - t))
    return lo, hi


def insw_ramp(v):
    """Time (s) for the eFuse's output to rise to v: (fastest, typical, slowest)."""
    sr_typ = 2000e-12 / INSW_CDVDT * 1e3        # V/s, DS equation 4
    return tuple(v / (sr_typ * i / INSW_IDVDT[1]) for i in (INSW_IDVDT[2], INSW_IDVDT[1], INSW_IDVDT[0]))


def r_in(worst):
    """Source to 5V_SYS: cable (VBUS + GND), receptacle, PTC, eFuse, copper.
    Worst: the cable's full IR drop and every part at its max; typical: half
    the cable limit and the parts at their min / typ."""
    return ((1.0 if worst else 0.5) * (CABLE_R_VBUS + CABLE_R_GND) + R_RECEPTACLE
            + (FUSE_IN_R_MAX if worst else FUSE_IN_R_MIN)
            + (INSW_RON_MAX if worst else INSW_RON_TYP) + R_5VSYS)


def main():
    print("Values the boards must meet (hw/power/design.py):")
    for board, text in ASSUMPTIONS:
        print("  %-11s %s" % (board, text))


if __name__ == "__main__":
    main()

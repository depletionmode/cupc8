"""Compare every external connector contact in a KiCad netlist with its contract.

The three card-edge pinouts come from the published tables. Local net names
and non-edge connector contacts are specified here, independently of the
schematic generators. None means that a contact must be unconnected.
"""
from pathlib import Path
import re

import kicadgen as kg

ROOT = Path(__file__).resolve().parents[2]
GND = "GND"


def table(name):
    result = {}
    path = ROOT / "doc/hardware" / name
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if match:
            number, b, a = match.groups()
            result["B" + number] = b.split()[0]
            result["A" + number] = a.split()[0]
    if not result:
        raise ValueError("empty connector table: " + str(path))
    return result


def card_slot(name, board):
    if name.startswith("RSVD_") or name == "PROG_n" and board != "wifi":
        return None
    if name in ("PRSNT1_n", "PRSNT2_n"):
        return "PRSNT"
    if board == "wifi":
        return {"+3V3": None, "SWCLK": "U0RXD", "SWDIO": "U0TXD",
                "CARD_RST_n": "EN", "PROG_n": "BOOT"}.get(name, name)
    return {"+3V3": "3V3", "CARD_RST_n": "RUN", "SWCLK": "SWCLK",
            "SWDIO": "SWDIO"}.get(name, name)


def cpu_card(name):
    if name.startswith("RSVD") or name in ("+5V", "CARD_ID1"):
        return None
    if name in ("PRSNT1_n", "PRSNT2_n"):
        return "PRSNT"
    return {"+3V3": "3V3", "CARD_ID0": "GND", "/STB": "CPU_nSTB",
            "/RDY": "CPU_nRDY", "/CPU_RST": "CPU_nRST", "CRESET_n": "CRESET_n",
            "CDONE": "CDONE"}.get(name, "CPU_" + name if name.startswith(("A", "D", "IRQ", "TMR_EXP"))
                 or name in ("RW", "SYNC", "HALTED", "WAITING") else name)


def system_card(name):
    if name == "+5V" or name.startswith("RSVD_A"):
        return None
    if name.startswith("RSVD_B"):
        return name
    if name in ("PRSNT1_n", "PRSNT2_n"):
        return "PRSNT"
    return {"+3V3": "+3V3"}.get(name, name)


def main_slot(name, number):
    if name == "+5V":
        return f"SLOT{number}_5V"
    if name == "PRSNT1_n":
        return GND
    if name in ("SCK", "MOSI", "MISO"):
        return "SPI_" + name
    return {"CARD_RST_n": f"SLOT{number}_RST_n", "IRQ_n": f"SLOT_nIRQ{number-1}",
            "CS_n": f"SLOT{number}_CS_n"}.get(name,
            f"SLOT{number}_{name}" if name.startswith("RSVD") or name in
            ("SWCLK", "SWDIO", "PRSNT2_n", "PROG_n") else name)


def main_cpu(name):
    if name == "PRSNT1_n":
        return GND
    if name.startswith("RSVD"):
        return "CPU_" + name
    return {"CRESET_n": "CPUCARD_nCRESET", "CDONE": "CPU_CDONE",
            "PRSNT2_n": "CPU_PRSNT2_n", "/STB": "CPU_nSTB", "/RDY": "CPU_nRDY",
            "/CPU_RST": "CPU_nRST"}.get(name,
            "CPU_" + name if name.startswith(("A", "D", "IRQ", "TMR_EXP", "CARD_ID"))
            or name in ("RW", "SYNC", "HALTED", "WAITING") else name)


def main_system(name):
    if name == "PRSNT1_n":
        return GND
    if name.startswith("RSVD"):
        return "SYS_" + name
    return {"SYS_nRST": "nMR", "CPUCARD_CDONE": "CPU_CDONE",
            "PRSNT2_n": "SYS_PRSNT2_n"}.get(name, name)


USB_GROUND = {"A1B12", "B1A12", "1", "2", "3", "4"}
USB_NC = {"A8", "B8"}
USB_POWER = {"A4B9", "B4A9"}


def usb_c(power, cc1, cc2, data=False):
    pins = {p: GND for p in USB_GROUND}
    pins.update({p: power for p in USB_POWER})
    pins.update(A5=cc1, B5=cc2)
    pins.update({p: None for p in USB_NC})
    pins.update({p: None for p in ("A6", "B6", "A7", "B7")})
    if data:
        pins.update(A6="USB_DP", B6="USB_DP", A7="USB_DM", B7="USB_DM")
    return pins


def expected(board):
    slot = table("slot.md")
    cpu = table("cpu-bus.md")
    system = table("system-slot.md")
    if board == "main":
        result = {"J1": usb_c("VBUS", "CC1", "CC2"),
                  "J2": {p: main_cpu(n) for p, n in cpu.items()},
                  "J3": {str(int(p[1:]) + (32 if p[0] == "B" else 0)): main_system(n)
                         for p, n in system.items()},
                  "J4": {str(p): n for p, n in enumerate(
                      ("+3V3", "GND", "SPI_SCK", "GND", "SPI_MOSI", "GND",
                       "SPI_MISO", "AUX_CS_n", "+5V", "GND"), 1)}}
        result["J3"]["65"] = GND
        for i in range(1, 7):
            result[f"J{10+i}"] = {p: main_slot(n, i) for p, n in slot.items()}
        return result
    if board == "cpu":
        return {"J1": {p: cpu_card(n) for p, n in cpu.items()}}
    if board == "system":
        return {"J1": usb_c("USB_VBUS", "USB_CC1", "USB_CC2", True),
                "J2": {p: system_card(n) for p, n in system.items()}}
    result = {"J1": {p: card_slot(n, board) for p, n in slot.items()}}
    if board == "gpu":
        result["J2"] = {str(p): n for p, n in {
            1: "HD_D2P", 2: GND, 3: "HD_D2N", 4: "HD_D1P", 5: GND,
            6: "HD_D1N", 7: "HD_D0P", 8: GND, 9: "HD_D0N", 10: "HD_CKP",
            11: GND, 12: "HD_CKN", 13: None, 14: None, 15: "DDC_SCL",
            16: "DDC_SDA", 17: GND, 18: "HDMI_5V", 19: "HPD_5V", 20: GND}.items()}
    elif board == "io":
        result["J2"] = {"1": "VBUS", "2": "USB_CONN_DM", "3": "USB_CONN_DP",
                         "4": GND, "5": GND, "6": GND}
    elif board == "storage":
        result["J2"] = {str(p): n for p, n in enumerate(("SD_DAT2", "SD_nCS", "SD_MOSI",
            "3V3", "SD_SCK", GND, "SD_MISO", "SD_DAT1", "SD_nDETECT", GND, GND, GND, GND), 1)}
    elif board == "eink":
        result["J2"] = {str(p): n for p, n in enumerate(("EPD_VCC", GND, "EPD_DIN_J",
            "EPD_CLK_J", "EPD_nCS_J", "EPD_DC_J", "EPD_nRST_J", "EPD_BUSY_J", "EPD_PWR_J"), 1)}
    return result


def contacts(path):
    """Return {ref: {pin: /net or None}}; reject malformed and duplicate nodes."""
    tree = kg.parse(Path(path).read_text())
    components = kg.find1(tree, "components")
    nets = kg.find1(tree, "nets")
    if components is None or nets is None:
        raise ValueError("netlist lacks components or nets")
    result = {}
    seen = set()
    for comp in kg.find(components, "comp"):
        ref = str(kg.find1(comp, "ref")[1])
        if not ref.startswith("J"):
            continue
        units = kg.find1(comp, "units")
        pins = {str(kg.find1(pin, "num")[1]) for unit in kg.find(units, "unit")
                for pin in kg.find(kg.find1(unit, "pins"), "pin")}
        if not pins:
            raise ValueError(f"{ref}: connector has no defined pins")
        result[ref] = {p: None for p in pins}
    for net in kg.find(nets, "net"):
        name = str(kg.find1(net, "name")[1]).removeprefix("/")
        for node in kg.find(net, "node"):
            ref = str(kg.find1(node, "ref")[1])
            if ref not in result:
                continue
            pin = str(kg.find1(node, "pin")[1])
            if pin not in result[ref] or (ref, pin) in seen:
                raise ValueError(f"{ref}.{pin}: unknown or duplicate net node")
            seen.add((ref, pin))
            # KiCad exports an isolated, explicitly no-connected pin as a
            # private net. It must contain just that contact.
            if name.startswith("unconnected-"):
                nodes = kg.find(net, "node")
                if len(nodes) != 1 or not name.startswith(f"unconnected-({ref}-") or not name.endswith("-Pad" + pin + ")"):
                    raise ValueError(f"{ref}.{pin}: malformed isolated net {name}")
                result[ref][pin] = None
            else:
                result[ref][pin] = name
    return result


def check(board, netlist):
    want = expected(board)
    got = contacts(netlist)
    errors = []
    for ref in sorted(set(want) | set(got)):
        a, b = want.get(ref, {}), got.get(ref, {})
        for pin in sorted(set(a) | set(b)):
            if pin not in a:
                errors.append(f"{ref}.{pin}: unexpected contact (found {b[pin] or 'NC'})")
            elif pin not in b:
                errors.append(f"{ref}.{pin}: missing contact (expected {a[pin] or 'NC'})")
            elif a[pin] != b[pin]:
                errors.append(f"{ref}.{pin}: expected {a[pin] or 'NC'}, found {b[pin] or 'NC'}")
    if errors:
        raise ValueError("connector netlist mismatch:\n" + "\n".join(errors[:30]) +
                         (f"\n... {len(errors)-30} more" if len(errors) > 30 else ""))
    return sum(map(len, want.values()))

#!/usr/bin/env python3
"""BOM risk table for the eight boards: JLC stock, basic/extended, price, lifecycle.

  tools/bom_risk.py --fetch            query JLC for every LCSC code and record
                                       the answers in the JSON (network)
  tools/bom_risk.py [--pending]        print the markdown tables from the JSON
                                       (no network; --pending applies PENDING)

The JSON (doc/hardware/bom-risk-20260928.json) holds JLC's answer per part
("jlc") and the hand-researched lifecycle / alternative notes ("notes"), which
--fetch keeps. The BOMs are read from build/hw/<board>/fab/bom.csv.

Cost model (JLC standard PCBA): each board type is its own order. Per BOM line,
JLC buys max(qty x boards + attrition, minimum purchase) at the price tier for
that quantity; each distinct extended part that is not "preferred" adds
EXT_FEE. PCB, stencil, setup, THT/hand-solder and shipping are not included.
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "doc", "hardware", "bom-risk-20260928.json")
BOARDS = ["main", "cpu", "gpu", "io", "storage", "wifi", "eink", "system"]
LCSC_API = "https://wmsc.lcsc.com/ftps/wm/product/detail?productCode="
EXT_FEE = 3.00          # USD per distinct extended part per order (JLC standard PCBA)
FIRST_ARTICLE = 2       # assembled per board type

# Approved or proposed changes not yet in build/hw (doc/m1-live-status.md):
# board -> list of (designators, old LCSC or None, new LCSC or None, note)
PENDING = {
    # IC-005 (David, 2026-09-29): TPS2553DBVR-1 port switch, RILIM 45.3k, no R13
    "io": [(["U5"], "C55136", "C111738", "TPS2553DBVR-1 port switch (latch-off)"),
           (["R10"], "C25752", "C26980", "RILIM 45.3k 1 %"),
           (["R12"], "C25756", "C25744", "FAULT pull-up 10k to 3V3"),
           (["R13"], "C25768", None, "removed"),
           (["C25"], None, "C52923", "1 uF at U5 IN")],
    "gpu": [(["RN1", "RN2"], "C425067", "C182716", "TMDS arrays 270 -> 360 ohm (A.2)")],
    "wifi": [(["R9"], "C25818", "C861412", "feedback 453k 0.1 %"),
             (["R10"], "C25803", "C122538", "feedback 100k 0.1 %")],
    # hw/power/reset_supervisor.py (MB-051, proposed, unreviewed)
    "main": [(["U17"], None, "C187836", "REF3425 reference"),
             (["U18", "U20"], None, "C42134", "OPA376 comparators"),
             (["U19"], None, "C7809", "SN74LVC07A slot reset buffer"),
             (["D7"], None, "C92068", "BAT54A OR"),
             (["R7", "R8"], "C17888", "C393098", "1 mOhm links"),
             (["R_L1"], None, "C860320", "30k 0.1 %"),
             (["R_L2"], None, "C408766", "20k 0.1 %"),
             (["R_L3"], None, "C860392", "43k 0.1 %"),
             (["R_T"], None, "C861593", "8.87k 0.1 %"),
             (["R_BT"], None, "C860067", "10k 0.1 %"),
             (["R_S"], None, "C21190", "1k 1 %"),
             (["R_F33"], None, "C23213", "6.8M 1 %"),
             (["R_F12"], None, "C26095", "2.7M 1 %"),
             (["R_NPOR_PD"], None, "C25803", "100k 1 %")],
}


def read_bom(board):
    """{lcsc: [designators]} from the board's fab BOM."""
    lines = {}
    with open(os.path.join(ROOT, "build", "hw", board, "fab", "bom.csv")) as f:
        for row in csv.DictReader(f):
            refs = [r.strip() for r in row["Designator"].split(",")]
            lines.setdefault(row["LCSC Part #"], []).extend(refs)
    return lines


def apply_pending(board, lines):
    lines = {k: list(v) for k, v in lines.items()}
    for refs, old, new, _ in PENDING.get(board, []):
        if old:
            lines[old] = [r for r in lines.get(old, []) if r not in refs]
            if not lines[old]:
                del lines[old]
        if new:
            lines.setdefault(new, []).extend(refs)
    return lines


def all_boms(pending):
    boms = {b: read_bom(b) for b in BOARDS}
    return {b: apply_pending(b, l) for b, l in boms.items()} if pending else boms


def price_at(part, n):
    tiers = sorted(part["prices"], key=lambda t: t[0])
    price = tiers[0][1]
    for start, p in tiers:
        if n >= start:
            price = p
    return price


def line_cost(part, per_board, boards):
    n = per_board * boards + part.get("attrition", 0)
    n = max(n, part.get("min_buy", 1))
    return n * price_at(part, n)


def board_cost(lines, parts, boards):
    """(parts USD, extended fees USD, missing codes) for one order of `boards`."""
    total, fees, missing = 0.0, 0.0, []
    for code, refs in lines.items():
        part = parts.get(code)
        if not part or not part.get("prices"):
            missing.append(code)
            continue
        total += line_cost(part, len(refs), boards)
        if part["library"] == "extended" and not part.get("preferred"):
            fees += EXT_FEE
    return total, fees, missing


def usage(boms):
    """{lcsc: {board: qty}} over all boards."""
    use = {}
    for b, lines in boms.items():
        for code, refs in lines.items():
            use.setdefault(code, {})[b] = len(refs)
    return use


def fetch(codes):
    sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
    import jlcparts
    out = {}
    for code in sorted(codes, key=lambda c: int(c[1:])):
        hits = [p for p in jlcparts.query(code, 5) if p["componentCode"] == code]
        if not hits:
            out[code] = {"found": False}
            continue
        p = hits[0]
        out[code] = {
            "found": True,
            "brand": p["componentBrandEn"], "mpn": p["componentModelEn"],
            "package": p["componentSpecificationEn"], "describe": p["describe"],
            "library": {"base": "basic", "expand": "extended"}.get(
                p["componentLibraryType"], p["componentLibraryType"]),
            "preferred": bool(p.get("preferredComponentFlag")),
            "stock": p["stockCount"],
            "min_buy": p.get("minPurchaseNum") or 1,
            "attrition": p.get("lossNumber") or 0,
            "prices": [[t["startNumber"], t["productPrice"]]
                       for t in p.get("componentPrices") or []],
        }
        out[code].update(lcsc(code))
    return out


def lcsc(code):
    """LCSC's own stock and its product-cycle flag ('normal', or e.g. 'discontinued')."""
    import urllib.request
    req = urllib.request.Request(LCSC_API + code, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            r = json.load(resp).get("result") or {}
    except (OSError, ValueError):
        return {"lcsc_stock": None, "lcsc_cycle": None}
    return {"lcsc_stock": r.get("stockNumber"), "lcsc_cycle": r.get("productCycle"),
            "lcsc_min_buy": r.get("minBuyNumber")}


def render(data, pending):
    parts, notes = data["jlc"], data.get("notes", {})
    boms = all_boms(pending)
    use = usage(boms)
    per_set = {c: sum(q.values()) for c, q in use.items()}
    out = []
    for b in BOARDS:
        out.append("### %s\n" % b)
        out.append("| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |")
        out.append("|---|---|---|---:|---|---:|---:|---|---|")
        for code in sorted(boms[b], key=lambda c: int(c[1:])):
            refs = boms[b][code]
            p = parts.get(code, {"found": False})
            n = notes.get(code, {})
            if not p.get("found"):
                out.append("| %s | NOT FOUND | %s | %d | - | 0 | 0 | %s | %s |" % (
                    code, ",".join(refs), len(refs), n.get("lifecycle", "?"), n.get("risk", "")))
                continue
            lib = p["library"] + (" (pref)" if p.get("preferred") else "")
            sets = p["stock"] // per_set[code]
            ref_s = ",".join(refs) if len(refs) <= 4 else "%s..%s" % (refs[0], refs[-1])
            out.append("| %s | %s %s | %s | %d | %s | %d | %d | %s | %s |" % (
                code, p["brand"].split("(")[0].replace(" Electronics Technology Co., Ltd.", "").strip(), p["mpn"], ref_s, len(refs), lib, p["stock"], sets,
                n.get("lifecycle", "?"), n.get("risk", "")))
        out.append("")
    out.append("### Cost per board type (parts + extended fees, USD)\n")
    out.append("| Board | Lines | Extended lines | 2 boards: total | per board | 10 boards: total | per board |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    for b in BOARDS:
        row = [b, str(len(boms[b]))]
        ext = sum(1 for c in boms[b] if parts.get(c, {}).get("library") == "extended"
                  and not parts[c].get("preferred"))
        row.append(str(ext))
        miss = set()
        for n in (2, 10):
            cost, fees, missing = board_cost(boms[b], parts, n)
            miss.update(missing)
            row += ["%.2f" % (cost + fees), "%.2f" % ((cost + fees) / n)]
        out.append("| " + " | ".join(row) + " |" + (" missing: %s" % ",".join(sorted(miss)) if miss else ""))
    out.append("")
    short = [(c, parts[c]["stock"], per_set[c]) for c in per_set
             if parts.get(c, {}).get("found") and parts[c]["stock"] < per_set[c] * 100]
    out.append("Parts with stock for fewer than 100 full sets: " + (
        ", ".join("%s (%d in stock, %d/set)" % s for s in sorted(short)) or "none"))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--data", default=DATA)
    args = ap.parse_args()
    if args.fetch:
        old = json.load(open(args.data)) if os.path.exists(args.data) else {}
        codes = set(usage(all_boms(False))) | set(usage(all_boms(True)))
        data = {"fetched": old.get("fetched"), "jlc": fetch(codes),
                "notes": old.get("notes", {})}
        with open(args.data, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        print("recorded %d parts in %s" % (len(data["jlc"]), args.data))
        return 0
    print(render(json.load(open(args.data)), args.pending))
    return 0


if __name__ == "__main__":
    sys.exit(main())

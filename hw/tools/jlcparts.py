#!/usr/bin/env python3
"""Query JLCPCB's assembly parts library (stock is what JLC can place).

  jlcparts.py search <keyword> [-n N]   search by keyword / MPN
  jlcparts.py check <C-number>...       stock + library type for LCSC codes

Uses the same unauthenticated endpoint as jlcpcb.com/parts. Output is one
line per part: code, basic/extended, stock, package, model, description.
"""
import argparse
import json
import sys
import urllib.request

API = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"


def query(keyword, size=10):
    body = json.dumps({"keyword": keyword, "currentPage": 1, "pageSize": size}).encode()
    req = urllib.request.Request(API, body, {"Content-Type": "application/json",
                                             "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return (data.get("data") or {}).get("componentPageInfo", {}).get("list") or []


def fmt(part):
    lib = {"base": "basic", "expand": "ext"}.get(part["componentLibraryType"],
                                                  part["componentLibraryType"])
    return "%-10s %-5s %7d  %-22s %-28s %s" % (
        part["componentCode"], lib, part["stockCount"],
        (part["componentSpecificationEn"] or "")[:22],
        (part["componentModelEn"] or "")[:28], (part["describe"] or "")[:70])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("keyword", nargs="+")
    s.add_argument("-n", type=int, default=10)
    c = sub.add_parser("check")
    c.add_argument("codes", nargs="+")
    args = ap.parse_args()

    if args.cmd == "search":
        for part in query(" ".join(args.keyword), args.n):
            print(fmt(part))
        return 0

    missing = 0
    for code in args.codes:
        hits = [p for p in query(code, 5) if p["componentCode"] == code]
        if hits:
            print(fmt(hits[0]))
        else:
            print("%-10s NOT FOUND" % code)
            missing += 1
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

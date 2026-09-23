#!/usr/bin/env python3
"""Query JLCPCB's assembly parts library (stock is what JLC can place).

  jlcparts.py search <keyword> [-n N]   search by keyword / MPN
  jlcparts.py check <C-number>... [--min-stock N]
                                        stock + library type for LCSC codes;
                                        exits 1 if any is missing or short

JLCPARTS_RECORD=dir saves every API answer there; JLCPARTS_RECORDED=dir
answers from those files instead of the network (the HOST-001 test).

Uses the same unauthenticated endpoint as jlcpcb.com/parts. Output is one
line per part: code, basic/extended, stock, package, model, description.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

API = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"


def _recording(keyword, size):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", keyword) + "-%d.json" % size


def query(keyword, size=10):
    replay = os.environ.get("JLCPARTS_RECORDED")
    if replay:
        with open(os.path.join(replay, _recording(keyword, size))) as f:
            data = json.load(f)
    else:
        body = json.dumps({"keyword": keyword, "currentPage": 1, "pageSize": size}).encode()
        req = urllib.request.Request(API, body, {"Content-Type": "application/json",
                                                 "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        record = os.environ.get("JLCPARTS_RECORD")
        if record:
            os.makedirs(record, exist_ok=True)
            with open(os.path.join(record, _recording(keyword, size)), "w") as f:
                json.dump(data, f)
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
    c.add_argument("--min-stock", type=int, default=1)
    args = ap.parse_args()

    if args.cmd == "search":
        for part in query(" ".join(args.keyword), args.n):
            print(fmt(part))
        return 0

    missing = 0
    for code in args.codes:
        hits = [p for p in query(code, 5) if p["componentCode"] == code]
        if hits and hits[0]["stockCount"] < args.min_stock:
            print(fmt(hits[0]) + "  SHORT (< %d)" % args.min_stock)
            missing += 1
        elif hits:
            print(fmt(hits[0]))
        else:
            print("%-10s NOT FOUND" % code)
            missing += 1
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fetch the vendor SPICE models the power checks use, and port them to ngspice.

    python3 hw/power/models/fetch.py        (idempotent; uses the cache)

TI's model licence ("provided as an aid ... as is") has no redistribution
grant, so the models are not committed. Each download is pinned by URL and
SHA-256. A mismatch stops the run, because it means TI has changed the model
under us; the numbers in power.md were produced with these exact files.

The zips are cached in build/power/models/, next to the ported .lib files.

Porting: ngspice runs these PSpice models in PSpice-compatibility mode
(`set ngbehavior=psa`, see spice.py), except for PSpice's VSWITCH, which
ngspice-47 reports as a model type mismatch and then leaves open, so the
TLV62569 never switches. VSWITCH (a resistance that moves smoothly from Roff
to Ron as the control goes from Voff to Von) becomes ngspice's SW with its
threshold halfway between (VT = (Von + Voff) / 2, VH = 0). Where Von < Voff
(the TLV7011 has several: on while the control is low) Ron and Roff swap
places. Every control in these models is a 0/1 logic level, so the two agree
except within the transition itself.
"""

import hashlib
import io
import os
import re
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE = os.path.join(ROOT, "build", "power", "models")

# name: (url, sha256 of the zip, member to extract)
MODELS = {
    # TLV62569 PSpice transient model, Rev. A (datasheet SLVSDG1, EVM SLVUAY6)
    "TLV62569_TRANS.lib": (
        "https://www.ti.com/lit/mo/slvmbw3a/slvmbw3a.zip",
        "af0d920f2659195de7ba1437b4b435a33f01e128abf99a4c8a39abbcf515bd5d",
        "TLV62569_PSPICE_TRANS/TLV62569_TRANS.lib"),
    # TLV7011 PSpice model, Rev. A (datasheet SLVSDM5F), version 2.0
    "tlv7011.lib": (
        "https://www.ti.com/lit/mo/slvmde3a/slvmde3a.zip",
        "ec8249caebf471890191f21a7366355f6154c720c3d6cd098bc7a1084a44ff87",
        "tlv7011.lib"),
}


def port(text):
    """PSpice VSWITCH models -> ngspice SW (see the module docstring)."""
    def sw(m):
        params = dict((k.lower(), v) for k, v in re.findall(r"(\w+)\s*=\s*([^\s)]+)", m.group(2)))
        num = lambda s: float(re.sub(r"[vV]$", "", s))
        von, voff = num(params["von"]), num(params["voff"])
        ron, roff = params["ron"], params["roff"]
        if von < voff:          # an inverted switch: on while the control is low
            ron, roff = roff, ron
        return "%s SW Ron=%s Roff=%s VT=%g VH=0" % (m.group(1), ron, roff, (von + voff) / 2)
    return re.sub(r"(?im)^(\.MODEL\s+\S+)\s+VSWITCH\s*\(?([^\n]*?)\)?\s*$", sw, text)


def fetch(name):
    url, sha, member = MODELS[name]
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, name)
    if os.path.exists(out):
        return out
    zpath = os.path.join(CACHE, os.path.basename(url))
    if not os.path.exists(zpath):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        got = hashlib.sha256(data).hexdigest()
        if got != sha:
            sys.exit("fetch: %s has sha256 %s, expected %s (TI changed the model?)" % (url, got, sha))
        with open(zpath, "wb") as f:
            f.write(data)
    with open(zpath, "rb") as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != sha:
        sys.exit("fetch: cached %s does not match its pinned sha256; delete it" % zpath)
    text = zipfile.ZipFile(io.BytesIO(data)).read(member).decode("latin-1")
    with open(out, "w") as f:
        f.write("* fetched from %s (sha256 %s) and ported by hw/power/models/fetch.py\n" % (url, sha))
        f.write(port(text))
    return out


def main():
    for name in MODELS:
        print(fetch(name))


if __name__ == "__main__":
    main()

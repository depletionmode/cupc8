#!/usr/bin/env python3
"""Fetch the vendor SPICE models the power checks use, and port them to ngspice.

    python3 hw/power/models/fetch.py        (idempotent; uses the cache)

TI's model licence ("provided as an aid ... as is") has no redistribution
grant, so the models are not committed. Each download is pinned by URL and
SHA-256. A mismatch stops the run, because it means TI has changed the model
under us; the numbers in power.md were produced with these exact files.

The zips are cached in build/power/models/, next to the ported .lib files.

Porting (see port()): continuation lines are joined, a current source's
PSpice unit "A" is dropped (ngspice would read it as atto), and ngspice runs
these PSpice models in PSpice-compatibility mode
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
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE = os.path.join(ROOT, "build", "power", "models")

# name: (url, sha256 of the zip, member to extract[, [(regex, replacement)] for
# this model only, after port()])
MODELS = {
    # TLV62569 PSpice transient model, Rev. A (datasheet SLVSDG1, EVM SLVUAY6)
    "TLV62569_TRANS.lib": (
        "https://www.ti.com/lit/mo/slvmbw3a/slvmbw3a.zip",
        "af0d920f2659195de7ba1437b4b435a33f01e128abf99a4c8a39abbcf515bd5d",
        "TLV62569_PSPICE_TRANS/TLV62569_TRANS.lib"),
    # TPS61023 PSpice transient model, Rev. A (datasheet SLVSF14B); the IO
    # card's keyboard-port boost. Its test benches set .PARAM ss (0: start-up)
    "TPS61023_TRANS.lib": (
        "https://www.ti.com/lit/mo/slvmd68a/slvmd68a.zip",
        "82d3996e813e134d703f32908b63f260def2064837810ac84c2c353883ec9363",
        "SLVMD68/TPS61023_TRANS_PSPICE/library/TPS61023_TRANS.LIB",
        # its diode models have an emission coefficient of 0.01 (a near-ideal
        # diode); ngspice's time step collapses on them at start-up. 0.1 still
        # drops under 0.1 V at 10 A, and the output-stage bridge's four drops
        # cancel. Its pre-charge PMOS (MbreakP) is a bare level-1 FET with its
        # gate driven by +-30 uA sources; behind a resistive source (the card's
        # feed) ngspice's step collapses at the end of pre-charge. 1 pF junction
        # and overlap capacitances (next to the model's own 208 pF on that gate)
        # let it converge. hw/power/boost.py checks the model against the datasheet
        [(r"(?im)^(\.model\s+\S+\s+d\s.*?)\bn=0\.01\b", r"\1n=0.1"),
         (r"(?im)^(\.model\s+MbreakP\s+pmos\s.*)$", r"\1 cbd=1p cbs=1p cgso=1e-6 cgdo=1e-6")]),
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
    text = re.sub(r"\r?\n\+", " ", text)       # continuation lines (the TPS61023 has one model split so)
    # PSpice ignores a unit after a number; ngspice reads a trailing "a" as atto,
    # so the TPS61023's "I_I1 ... DC 10A" (the 10 A source that joins its output
    # stage to VOUT) became 1e-17 A and the boost never reached its pin
    text = re.sub(r"(?m)^(I\S*\s+\S+\s+\S+\s+(?:DC\s+)?[-+0-9.eE]+)[aA]\b", r"\1", text)
    return re.sub(r"(?im)^(\.MODEL\s+\S+)\s+VSWITCH\s*\(?([^\n]*?)\)?\s*$", sw, text)


def write_atomic(path, data):
    """Tests run in parallel and may fetch the same model at once: each
    writes its own temporary file and renames it into place, so no reader
    ever sees half a file."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")   # unique per thread too
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


PORT_VERSION = 3               # bump when port() or a model's fixes change: re-ports the cache


def fetch(name):
    url, sha, member, *fixes = MODELS[name]
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, name)
    stamp = "* port v%d: fetched from %s (sha256 %s) and ported by hw/power/models/fetch.py\n" % (
        PORT_VERSION, url, sha)
    if os.path.exists(out):
        with open(out) as f:
            if f.readline() == stamp:
                return out
    zpath = os.path.join(CACHE, os.path.basename(url))
    if not os.path.exists(zpath):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        got = hashlib.sha256(data).hexdigest()
        if got != sha:
            sys.exit("fetch: %s has sha256 %s, expected %s (TI changed the model?)" % (url, got, sha))
        write_atomic(zpath, data)
    with open(zpath, "rb") as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != sha:
        sys.exit("fetch: cached %s does not match its pinned sha256; delete it" % zpath)
    text = port(zipfile.ZipFile(io.BytesIO(data)).read(member).decode("latin-1"))
    for pattern, repl in (fixes[0] if fixes else []):
        text = re.sub(pattern, repl, text)
    write_atomic(out, (stamp + text).encode("latin-1"))
    return out


def main():
    for name in MODELS:
        print(fetch(name))


if __name__ == "__main__":
    main()

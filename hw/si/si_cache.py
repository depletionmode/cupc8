"""On-disk cache for route_si cross-section solves (GC/IC/YC-007).

Each distinct cut key costs 10-40 s of finite-element solving and a routed
board needs hundreds, so results are kept under build/si/cache/.  An entry is
named by the SHA-256 of the key and of the solver sources (route_si.py,
xsection.py), so editing either one, or any change in the copper, misses the
cache instead of reusing a stale number.  Only a cut key is cached, never a
verdict: a mutated board simply produces different keys.
"""
import hashlib
from pathlib import Path
import pickle

import route_si

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent.parent / 'build/si/cache'
_SOURCES = hashlib.sha256(b''.join((HERE / name).read_bytes()
                                   for name in ('route_si.py', 'xsection.py'))).hexdigest()


def _path(key):
    return CACHE / (hashlib.sha256((_SOURCES + repr(key)).encode()).hexdigest() + '.pkl')


def solve_all(keys, jobs=None):
    """route_si.solve_all with a disk cache; returns {key: result}."""
    keys = sorted(set(keys))
    found, missing = {}, []
    for key in keys:
        try:
            found[key] = pickle.loads(_path(key).read_bytes())
        except (OSError, pickle.UnpicklingError, EOFError):
            missing.append(key)
    if missing:
        import multiprocessing
        CACHE.mkdir(parents=True, exist_ok=True)
        # Written as each solve finishes, so an interrupted run keeps its work.
        with multiprocessing.get_context('fork').Pool(jobs) as pool:
            for key, result in pool.imap_unordered(route_si._solve_one, missing, chunksize=1):
                found[key] = result
                temporary = _path(key).with_suffix('.tmp')
                temporary.write_bytes(pickle.dumps(result))
                temporary.replace(_path(key))
    return found

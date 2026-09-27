# Main-board SES replay (conditional recovery)

The ordinary `hw/boards/main.py [outdir]` build still launches Freerouting.
The replay option imports one **completed** Freerouting session from an earlier
main-board route attempt, then runs the same main-board post-route repair,
connectivity, zone fill, DRC with schematic parity, fabrication export, and
evidence receipt steps. It is intended only for a session whose remaining
connections can be repaired by the source-owned post-route code. It does not
declare an incomplete route acceptable.

After `route-parallel/route-<salt>.ses` has finished writing in the source
package, snapshot that package. Use the salt in the DSN and SES filenames:

```sh
python3 hw/tools/sesreplay.py snapshot /absolute/source/build/hw/main 9 /absolute/snapshot.json
python3 hw/boards/main.py /absolute/new/build/hw/main --replay-manifest /absolute/snapshot.json
```

Use a fresh destination directory separate from the source route package. The snapshot
records SHA-256 hashes for its pre-route `main.kicad_pcb`, salted canonical
DSN, and SES. Replay rejects absent, changed, empty, or syntactically
incomplete files; a salt outside the configured three routing rounds; or an
SES whose session/base-design name does not match the DSN basename. It rebuilds
the pre-route board from the current source and checks a fingerprint with only
pcbnew's random item UUIDs removed. It exports the same salted canonical DSN
and compares a fingerprint with only the output-directory prefix in the DSN
header removed. Every other byte must match.

The selected source board, DSN, SES, and snapshot, plus the independently
rebuilt pre-route board and DSN, are copied to `replay-source/` and covered
by `evidence.json`. `route-replay.json` records
their raw hashes, both canonical comparisons, and the route salt; it is also
covered by the receipt. The importer rejects a session that moves a footprint.
The normal final DRC and parity steps must pass before an evidence receipt is
written. A failed replay has no success receipt and never falls back to
Freerouting or another session.

The SES format names its base DSN but does not embed that DSN's content hash.
The snapshot therefore binds the selected pair by their common source package,
salt, filenames, and captured hashes; the regenerated DSN independently binds
that DSN to this board source. The final board checks remain the authority on
whether the imported copper is complete and valid.

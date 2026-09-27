"""Content-bound replay of one completed main-board Freerouting session.

The snapshot manifest is an explicit selection of a route salt and three
immutable source hashes. Replay rebuilds the pre-route board and canonical
DSN, checks both against that snapshot, then imports the captured SES through
the normal board pipeline. It never starts Freerouting.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile


FIELDS = ('preroute_board', 'dsn', 'ses')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
UUID_FIELD = re.compile(r'\(uuid "[0-9a-fA-F-]{36}"\)')
MODEL_FIELD = re.compile(r'\(model "([^"\n]+)"')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def preroute_digest(path):
    """Fingerprint routed geometry across worktree paths and KiCad item order.

    pcbnew saves footprints in a nondeterministic order, gives every item a
    fresh UUID, and embeds the current worktree's absolute 3D model paths.
    None of those values affect the DSN. Every other top-level board item,
    including net identities, footprints, pads, tracks, zones and rules,
    remains byte-exact after canonicalization.
    """
    source = Path(path).read_text()
    normalized, count = UUID_FIELD.subn('(uuid "<item>")', source)
    if not normalized.startswith('(kicad_pcb\n') or count < 1:
        raise ValueError('unsupported pre-route PCB for replay fingerprint')

    def model(match):
        value = match.group(1)
        if '/hw/lib/' in value:
            return '(model "<hw/lib>/' + value.split('/hw/lib/', 1)[1] + '"'
        return match.group(0)

    normalized = MODEL_FIELD.sub(model, normalized)
    items = []
    depth = 0
    start = None
    quoted = escaped = False
    for index, char in enumerate(normalized):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == '(':
            if depth == 1:
                start = index
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                raise ValueError('unbalanced pre-route PCB')
            if depth == 1:
                items.append(normalized[start:index + 1])
                start = None
    if quoted or depth or not items:
        raise ValueError('incomplete pre-route PCB')
    return hashlib.sha256('\n'.join(sorted(items)).encode()).hexdigest()


def canonical_dsn_digest(path):
    """Hash KiCad's DSN line multiset after removing its export path.

    pcbnew emits geometry declarations in board item order. The source DSN
    is also checked exactly against its saved source board, so this digest
    only bridges that harmless ordering difference in a fresh build.
    """
    path = Path(path).resolve()
    text = path.read_text()
    match = re.match(r'^\(pcb "([^"\n]+)"', text)
    if not match or Path(match[1]).resolve() != path:
        raise ValueError('DSN embedded source path differs from its file')
    normalized = text[:match.start(1)] + path.name + text[match.end(1):]
    return hashlib.sha256('\n'.join(sorted(normalized.splitlines())).encode()).hexdigest()


def verify_source_dsn(board_path, dsn_path, salt):
    """Prove the captured DSN is exactly the source board's salted export."""
    import pcbnew
    import kicadgen as kg

    board = pcbnew.LoadBoard(str(board_path))
    kg.stable_uuids(board, salt)
    with tempfile.TemporaryDirectory(prefix='cupc8-ses-source-') as tmp:
        check = Path(tmp) / 'check.dsn'
        if not pcbnew.ExportSpecctraDSN(board, str(check)):
            raise ValueError('source pre-route board DSN export failed')
        generated = kg.canonical_dsn(check.read_text(), salt)
    source = Path(dsn_path).read_text()
    if generated.split('\n', 1)[1] != source.split('\n', 1)[1]:
        raise ValueError('source salted DSN differs from source pre-route board')


def _source_paths(package, salt):
    package = Path(package).resolve()
    return {'preroute_board': package / 'main.kicad_pcb',
            'dsn': package / 'route-parallel' / ('route-%d.dsn' % salt),
            'ses': package / 'route-parallel' / ('route-%d.ses' % salt)}


def _check_session(path, salt):
    # A truncated Freerouting output cannot be replayed. The base_design
    # identifies the DSN basename; the full DSN content is bound separately
    # by its SHA-256 and by regenerating it from this source revision.
    text = Path(path).read_text()
    name = 'route-%d' % salt
    # Freerouting quotes both names in a real Specctra session. Accept the
    # unquoted form as well, but still require the exact selected salt.
    atom = r'"?' + re.escape(name) + r'"?'
    if not re.match(r'^\s*\(session\s+' + atom +
                    r'\s+\(base_design\s+' + atom + r'\s*\)', text):
        raise ValueError('SES session/base_design does not match route salt')
    depth = 0
    quoted = escaped = False
    closed = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == '(':
            if closed:
                raise ValueError('commands after SES session')
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                raise ValueError('unbalanced SES session')
            if depth == 0:
                closed = True
        elif closed and not char.isspace():
            raise ValueError('commands after SES session')
    if quoted or depth != 0 or not closed:
        raise ValueError('incomplete SES session')


def snapshot(package, salt, manifest_path):
    """Record the completed source package selected for a later replay."""
    if type(salt) is not int or salt < 0:
        raise ValueError('route salt must be a nonnegative integer')
    paths = _source_paths(package, salt)
    for name, path in paths.items():
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('missing or empty replay %s: %s' % (name, path))
    _check_session(paths['ses'], salt)
    verify_source_dsn(paths['preroute_board'], paths['dsn'], salt)
    payload = {'version': 1, 'board': 'main', 'salt': salt,
               'sources': {name: str(paths[name]) for name in FIELDS},
               'sha256': {name: digest(paths[name]) for name in FIELDS},
               'canonical': {'preroute_board': preroute_digest(paths['preroute_board']),
                             'dsn': canonical_dsn_digest(paths['dsn'])}}
    destination = Path(manifest_path)
    if destination.resolve() in paths.values():
        raise ValueError('snapshot manifest must not replace a route input')
    destination.write_text(json.dumps(payload, indent=2) + '\n')
    return payload


def load(manifest_path, output, maximum_salt):
    """Validate the manifest and its source files before board generation."""
    path = Path(manifest_path).resolve()
    payload = json.loads(path.read_text())
    if (set(payload) != {'version', 'board', 'salt', 'sources', 'sha256', 'canonical'} or
            payload['version'] != 1 or payload['board'] != 'main' or
            type(payload['salt']) is not int or not 0 <= payload['salt'] < maximum_salt or
            set(payload['sources']) != set(FIELDS) or set(payload['sha256']) != set(FIELDS) or
            set(payload['canonical']) != {'preroute_board', 'dsn'}):
        raise ValueError('unsupported main-board SES replay manifest')
    paths = {name: Path(payload['sources'][name]) for name in FIELDS}
    package = paths['preroute_board'].parent
    expected = _source_paths(package, payload['salt'])
    if any(not paths[name].is_absolute() or paths[name] != expected[name] for name in FIELDS):
        raise ValueError('replay files must be one main route package and salt')
    out = Path(output).resolve()
    if out == package or out.is_relative_to(package) or package.is_relative_to(out):
        raise ValueError('replay output must be separate from source route package')
    for name, source in paths.items():
        if not source.is_file() or not source.stat().st_size:
            raise ValueError('missing or empty replay %s: %s' % (name, source))
        expected_hash = payload['sha256'][name]
        if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash):
            raise ValueError('invalid replay %s SHA-256' % name)
        if digest(source) != expected_hash:
            raise ValueError('changed replay %s' % name)
    _check_session(paths['ses'], payload['salt'])
    verify_source_dsn(paths['preroute_board'], paths['dsn'], payload['salt'])
    for name, actual in (('preroute_board', preroute_digest(paths['preroute_board'])),
                         ('dsn', canonical_dsn_digest(paths['dsn']))):
        wanted = payload['canonical'][name]
        if not isinstance(wanted, str) or not SHA256.fullmatch(wanted) or actual != wanted:
            raise ValueError('changed canonical replay %s' % name)
    payload['manifest_sha256'] = digest(path)
    payload['manifest_path'] = str(path)
    return payload


def capture(payload, output, regenerated_board, regenerated_dsn):
    """Bind the regenerated inputs and captured SES into receipt artifacts."""
    output = Path(output)
    hashes = payload['sha256']
    if preroute_digest(regenerated_board) != payload['canonical']['preroute_board']:
        raise ValueError('rebuilt pre-route board differs from replay source')
    if canonical_dsn_digest(regenerated_dsn) != payload['canonical']['dsn']:
        raise ValueError('canonical salted DSN differs from replay source')
    source = output / 'replay-source'
    source.mkdir()
    targets = {'preroute_board': source / 'main-preroute.kicad_pcb',
               'dsn': source / ('route-%d.dsn' % payload['salt']),
               'ses': source / ('route-%d.ses' % payload['salt'])}
    rebuilt_board = source / 'rebuilt-preroute.kicad_pcb'
    rebuilt_dsn = source / ('rebuilt-route-%d.dsn' % payload['salt'])
    captured_manifest = source / 'snapshot.json'
    shutil.copyfile(payload['manifest_path'], captured_manifest)
    if digest(captured_manifest) != payload['manifest_sha256']:
        raise ValueError('replay manifest changed during capture')
    shutil.copyfile(payload['sources']['preroute_board'], targets['preroute_board'])
    shutil.copyfile(regenerated_board, rebuilt_board)
    shutil.copyfile(regenerated_dsn, rebuilt_dsn)
    for name in ('dsn', 'ses'):
        shutil.copyfile(payload['sources'][name], targets[name])
    for name in FIELDS:
        if digest(targets[name]) != hashes[name]:
            raise ValueError('replay %s changed during capture' % name)
    if (digest(rebuilt_board) != digest(regenerated_board) or
            digest(rebuilt_dsn) != digest(regenerated_dsn)):
        raise ValueError('rebuilt replay inputs changed during capture')
    receipt = {'version': 1, 'mode': 'ses-replay', 'board': 'main',
               'salt': payload['salt'], 'manifest_sha256': payload['manifest_sha256'],
               'source_sha256': hashes, 'canonical_sha256': payload['canonical'],
               'rebuilt_preroute_sha256': digest(regenerated_board),
               'rebuilt_preroute_canonical_sha256': preroute_digest(regenerated_board),
               'rebuilt_dsn_sha256': digest(regenerated_dsn),
               'rebuilt_dsn_canonical_sha256': canonical_dsn_digest(regenerated_dsn),
               'captured': {**{name: str(targets[name].relative_to(output)) for name in FIELDS},
                            'manifest': str(captured_manifest.relative_to(output)),
                            'rebuilt_preroute_board': str(rebuilt_board.relative_to(output)),
                            'rebuilt_dsn': str(rebuilt_dsn.relative_to(output))}}
    (output / 'route-replay.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return targets['ses']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('snapshot',))
    parser.add_argument('source_package', help='completed build/hw/main directory')
    parser.add_argument('salt', type=int, help='route-parallel/route-<salt>')
    parser.add_argument('manifest', help='new JSON snapshot manifest')
    args = parser.parse_args()
    snapshot(args.source_package, args.salt, args.manifest)


if __name__ == '__main__':
    main()

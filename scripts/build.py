#!/usr/bin/env python3
"""Check public deployment files or export public/full directories and ZIPs. Never calls Docker."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import zipfile
from deploy import check_materials, material_files, read_source_bundle

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'README.md', 'LICENSE', 'UZZ-LICENSE.md', 'THIRD_PARTY.md', '.gitignore',
              'config.example.json', 'versions.json'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def public_files():
    # Runtime artifacts, source repositories and private state are never discovered recursively.
    files = [ROOT / name for name in ROOT_FILES]
    for pattern in ['scripts/*.py', 'tests/test_*.py', 'docs/*.md']:
        files.extend(ROOT.glob(pattern))
    for path in files:
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != ROOT and ROOT in p.parents):
            raise ValueError('Do not package symlinks: ' + str(path.relative_to(ROOT)))
        if not path.is_file():
            raise ValueError('Public deployment file missing: ' + str(path.relative_to(ROOT)))
    return sorted(files)


def check_plugins(required=False):
    lock = json.loads((ROOT / 'versions.json').read_text())
    if required:
        check_materials(lock, root=ROOT)
    license_text = (ROOT / 'UZZ-LICENSE.md').read_bytes()
    missing = []
    for relative, expected in material_files(lock):
        path = ROOT / relative
        if path.is_symlink() or path.exists() and not path.is_file():
            raise ValueError('Invalid artifact file: ' + relative.as_posix())
        if not path.is_file():
            missing.append(relative.as_posix())
        elif digest(path.read_bytes()) != expected:
            raise ValueError('Artifact checksum mismatch: ' + relative.as_posix())
    for plugin in lock['plugins']:
        path = ROOT / 'plugins' / plugin['file']
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('plugin.json'))
            contents = {n: archive.read(n) for n in archive.namelist()
                        if not n.endswith('/') and n != 'plugin.json'}
            canonical = ''.join(n + '\n' + digest(contents[n]) + '\n' for n in sorted(contents))
            valid = (manifest['version'] == plugin['version'] and manifest['entryPath'] == plugin['entryPath']
                     and manifest['permissions'] == plugin['permissions']
                     and digest(archive.read(manifest['main'])) == manifest['entryHash']
                     and digest(canonical.encode()) == manifest['zipHash'])
            if not valid:
                raise ValueError('Plugin manifest mismatch: ' + path.name)
            if plugin['entryPath'] == 'uzz-source':
                if (manifest['license'] != plugin['license'] or plugin['license'] != lock['uzz_source']['license']
                        or archive.read('LICENSE.txt') != license_text):
                    raise ValueError('UZZ plugin license mismatch.')
    bundle = ROOT / 'packages' / lock['uzz_source']['bundle']['file']
    if bundle.is_file():
        service = read_source_bundle(lock['uzz_source'], bundle)
        if service['LICENSE.txt'] != license_text or service['APACHE-2.0.txt'] != (ROOT / 'LICENSE').read_bytes():
            raise ValueError('UZZ service license mismatch.')
    return lock, missing


def checksums(files):
    return ''.join(digest(p.read_bytes()) + '  ' + p.relative_to(ROOT).as_posix() + '\n' for p in files)


def check_public_manifest():
    expected = checksums(public_files())
    if (ROOT / 'SHA256SUMS').read_text() != expected:
        raise ValueError('Public file list/content changed; review and regenerate SHA256SUMS.')


def export(target, output):
    output = output.expanduser().absolute()
    archive_path = output.with_name(output.name + '.zip')
    if output.resolve() == ROOT.resolve() or ROOT.resolve() in output.resolve().parents:
        raise ValueError('Export outside the project directory to keep delivery files separate.')
    if output.exists() or output.is_symlink() or archive_path.exists() or archive_path.is_symlink():
        raise ValueError('Output already exists; choose a new path. Existing files are never replaced.')
    lock, _ = check_plugins(required=target == 'full')
    check_public_manifest()
    files = public_files() + [ROOT / 'SHA256SUMS']
    if target == 'full':
        files.extend(ROOT / relative for relative, _ in material_files(lock))
    # Read and verify all inputs before creating the output directory.
    payload = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sorted(files)}
    output.mkdir(parents=True, exist_ok=False)
    for name, data in payload.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)
    with zipfile.ZipFile(archive_path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in payload.items():
            item = zipfile.ZipInfo('xiaoai-songloft-online-music/' + name, date_time=(2026, 10, 22, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    print('Exported ' + target + ' directory: ' + str(output))
    print('ZIP: ' + str(archive_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true', help='Check public files and any runtime artifacts already present')
    group.add_argument('--target', choices=['public', 'full'])
    parser.add_argument('--output', type=Path, help='New output directory outside this project; also creates a sibling ZIP')
    args = parser.parse_args()
    if bool(args.target) != bool(args.output):
        parser.error('--target and --output must be supplied together')
    if args.target:
        export(args.target, args.output)
        return
    _, missing = check_plugins()
    if args.check:
        check_public_manifest()
        print('Public deployment files and all present artifacts verified.')
    else:
        (ROOT / 'SHA256SUMS').write_text(checksums(public_files()))
        print('Updated public SHA256SUMS; runtime artifact checksums remain in versions.json.')
    if missing:
        print('Runtime materials missing: ' + str(len(missing)) + '. Run scripts/deploy.py check before installation.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        print('Failed: ' + str(error), file=sys.stderr)
        sys.exit(1)

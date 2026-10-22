#!/usr/bin/env python3
"""Import a fixed local UZZ release; never copies editable source or touches containers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=Path, help='Path to the local songloft-plugin-uzz repository')
    args = parser.parse_args()
    release = json.loads((args.repository / 'release.json').read_text())
    if release['repository'] != 'songloft-plugin-uzz' or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', release['version']):
        raise ValueError('Unexpected UZZ release metadata.')
    for key in ['plugin', 'bundle']:
        item = release[key]
        if Path(item['file']).name != item['file']:
            raise ValueError('Unexpected release filename.')
        source = args.repository / 'dist' / item['file']
        if hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Release checksum mismatch: ' + key)
    if release['plugin']['version'] != release['version'] or release['plugin']['entryPath'] != 'uzz-source':
        raise ValueError('UZZ plugin version/identity mismatch.')
    # Validate the service package before updating the deployment lock.
    from deploy import read_source_bundle
    dependency = {key: release[key] for key in ['repository', 'version', 'license', 'bundle']}
    service = read_source_bundle(dependency, args.repository / 'dist' / release['bundle']['file'])
    if release['plugin']['license'] != release['license']:
        raise ValueError('UZZ plugin/service license mismatch.')
    with zipfile.ZipFile(args.repository / 'dist' / release['plugin']['file']) as archive:
        for name in ['LICENSE.txt', 'THIRD_PARTY.md', 'APACHE-2.0.txt']:
            if archive.read(name) != service[name]:
                raise ValueError('UZZ plugin/service notice mismatch: ' + name)
    for key, folder in [('plugin', 'plugins'), ('bundle', 'packages')]:
        (ROOT / folder).mkdir(exist_ok=True)
        shutil.copy2(args.repository / 'dist' / release[key]['file'], ROOT / folder / release[key]['file'])
    lock = json.loads((ROOT / 'versions.json').read_text())
    lock['uzz_source'] = dependency
    plugin = dict(release['plugin'], repository=release['repository'])
    lock['plugins'] = [plugin if item['entryPath'] == 'uzz-source' else item for item in lock['plugins']]
    (ROOT / 'versions.json').write_text(json.dumps(lock, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'UZZ-LICENSE.md').write_bytes(service['LICENSE.txt'])
    print('Imported UZZ ' + release['version'] + ' release artifacts and updated versions.json. Run scripts/build.py next.')


if __name__ == '__main__':
    main()

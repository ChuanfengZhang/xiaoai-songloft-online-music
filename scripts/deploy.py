#!/usr/bin/env python3
"""New-install helper. Uses Docker CLI directly and never reads another deployment."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
SONG = 'xiaoai-songloft-online-music-songloft'
SOURCE = 'xiaoai-songloft-online-music-uzz'
NETWORK = 'xiaoai-songloft-online-music'
LABEL = 'io.xiaoai-songloft-online-music.deployment'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def material_files(lock):
    """Return the fixed relative paths and hashes, without reading any artifacts."""
    materials = []
    for item in lock['plugins']:
        require(Path(item['file']).name == item['file'], 'Invalid plugin filename.')
        materials.append((Path('plugins') / item['file'], item['sha256']))
    bundle = lock['uzz_source']['bundle']
    require(Path(bundle['file']).name == bundle['file'], 'Invalid UZZ bundle filename.')
    materials.append((Path('packages') / bundle['file'], bundle['sha256']))
    return materials


def check_materials(lock=None, root=None):
    root = ROOT if root is None else root
    lock = read_json(root / 'versions.json') if lock is None else lock
    materials = material_files(lock)
    missing = [rel for rel, _ in materials if not (root / rel).is_file()]
    if missing:
        raise ValueError('缺少部署所需文件：\n' + '\n'.join('  - ' + rel.as_posix() for rel in missing)
                         + '\n项目目录：' + str(root)
                         + '\n请取得与 versions.json 对应版本的配套物料，按上述相对路径放入项目目录。'
                         + '\n插件 ZIP 和服务 tar.gz 保持原文件，不要手工解包或只修改文件名。补齐后重新执行原命令。')
    invalid = [rel for rel, expected in materials
               if (root / rel).is_symlink() or hashlib.sha256((root / rel).read_bytes()).hexdigest() != expected]
    if invalid:
        raise ValueError('部署文件校验不通过（版本不符、文件损坏或使用了符号链接）：\n'
                         + '\n'.join('  - ' + rel.as_posix() for rel in invalid)
                         + '\n项目目录：' + str(root)
                         + '\n请用 versions.json 对应版本的原始文件替换上述文件，再重新执行原命令。')
    return lock


def private_file(path, text, exclusive=False):
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    require(not path.is_symlink(), 'Refusing a symlink for a private file.')
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(text)
    path.chmod(0o600)


def init():
    config = read_json(ROOT / 'config.example.json')
    config.update(admin_password=secrets.token_hex(24), uzz_token=secrets.token_hex(24), deployment_id=str(uuid.uuid4()))
    private_file(ROOT / 'config.json', json.dumps(config, ensure_ascii=False, indent=2) + '\n', exclusive=True)
    print('Created private config.json (0600). Edit host_ip, music_dir and data_dir. No Docker calls made.')


def config():
    value = read_json(ROOT / 'config.json')
    value.setdefault('host_ip', value.get('nas_ip'))
    address = ipaddress.ip_address(value['host_ip'])
    require(address.version == 4 and not address.is_unspecified and not address.is_loopback and not address.is_multicast,
            'host_ip must be the Docker host LAN IPv4 address.')
    require(type(value['songloft_port']) is int and 1 <= value['songloft_port'] <= 65535, 'Invalid songloft_port.')
    for key in ['music_dir', 'data_dir']:
        path = value[key]
        require(isinstance(path, str) and Path(path).is_absolute() and not any(c in path for c in ',\n\r\0'), 'Use an absolute directory without commas/control characters: ' + key)
    for key in ['admin_username', 'admin_password', 'uzz_token']:
        text = value[key]
        require(isinstance(text, str) and text and not any(c in text for c in '\n\r\0') and text != 'GENERATED_BY_INIT', 'Invalid private configuration field: ' + key)
    require(re.fullmatch(r'[0-9a-f-]{36}', value['deployment_id']) is not None, 'Invalid deployment_id.')
    return value


def pull():
    lock = read_json(ROOT / 'versions.json')
    for component in ['songloft', 'browserless']:
        docker('pull', '--platform', lock[component]['platform'], lock[component]['image'])
    print('Pulled the two configured images. No application containers created.')


def local_image_id(image, platform):
    if existing('image', image) is None:
        docker('pull', '--platform', platform, image)
    image_id = docker('image', 'inspect', '--format', '{{.Id}}', image, capture=True).strip()
    require(re.fullmatch(r'sha256:[a-f0-9]{64}', image_id) is not None, 'Invalid local image identity.')
    return image_id


def docker(*args, capture=False):
    result = subprocess.run(['docker', *args], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else ''


def existing(kind, name):
    result = subprocess.run(['docker', kind, 'inspect', name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if result.returncode:
        return None
    return json.loads(result.stdout)[0]


def filesystem_options(path, mounts):
    """Match the longest real mount point, including a not-yet-created data path."""
    path = Path(path).resolve()
    best, options = -1, set()
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        mount = Path(fields[1].replace('\\040', ' ').replace('\\011', '\t').replace('\\134', '\\')).resolve()
        if path == mount or mount in path.parents:
            if len(str(mount)) > best:
                best, options = len(str(mount)), set(fields[3].split(','))
    return options


def prepare_paths(value):
    music, data = Path(value['music_dir']), Path(value['data_dir'])
    require(data.resolve() != Path('/'), 'data_dir cannot be the filesystem root.')
    require(music.is_dir(), 'music_dir must already exist. Original songs are never moved.')
    require(music.resolve() not in data.resolve().parents and music.resolve() != data.resolve(), 'data_dir must be outside music_dir.')
    downloads = music / 'uzz-online'
    require(not downloads.is_symlink() and not data.is_symlink(), 'Refusing symlink data/download directories.')
    if Path('/proc/mounts').exists():
        require('noexec' not in filesystem_options(data, Path('/proc/mounts').read_text()),
                'data_dir is on a noexec filesystem. Use persistent storage on an exec-capable filesystem.')
    data.mkdir(parents=True, exist_ok=True)
    claim_data_directory(data, value['deployment_id'])
    downloads.mkdir(exist_ok=True)
    for path in [data, downloads]:
        require(os.access(path, os.W_OK), 'Directory is not writable: ' + str(path))
    # The nested mountpoint exists before Docker applies the read-only parent.
    return music, data, downloads


DATA_OWNER_FILE = '.xiaoai-songloft-online-music.json'


def claim_data_directory(data, deployment_id):
    """Only claim an empty directory; retain ownership for safe same-install retries."""
    marker = data / DATA_OWNER_FILE
    if marker.exists() or marker.is_symlink():
        require(marker.is_file() and not marker.is_symlink() and marker.stat().st_size <= 4096,
                'Invalid data directory ownership file; directory not adopted.')
        owner = read_json(marker)
        require(isinstance(owner, dict) and owner.get('deployment_id') == deployment_id,
                'data_dir belongs to a different deployment; directory not adopted.')
        return
    require(not any(data.iterdir()),
            'data_dir is not empty and has no deployment ownership file. Use a new empty directory; existing data is not adopted.')
    private_file(marker, json.dumps({'deployment_id': deployment_id}) + '\n', exclusive=True)


SERVICE_FILES = {'health.mjs', 'page-api.mjs', 'source-service.mjs', 'start.sh',
                 'LICENSE.txt', 'THIRD_PARTY.md', 'APACHE-2.0.txt'}


def read_source_bundle(dependency, path=None):
    bundle = dependency['bundle']
    filename = bundle['file']
    require(Path(filename).name == filename, 'Invalid UZZ bundle filename.')
    path = path if path is not None else ROOT / 'packages' / filename
    require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == bundle['sha256'], 'UZZ service bundle missing or checksum mismatch.')
    require(set(bundle['files']) == SERVICE_FILES, 'Unexpected UZZ service file list.')
    result = {}
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        require(len(members) == len(SERVICE_FILES), 'Unexpected UZZ bundle member count.')
        for member in members:
            require(member.isfile() and member.name in SERVICE_FILES and member.name not in result and member.size <= 512 * 1024,
                    'Unsafe or unexpected UZZ bundle member.')
            data = archive.extractfile(member).read()
            require(hashlib.sha256(data).hexdigest() == bundle['files'][member.name], 'UZZ service file checksum mismatch.')
            result[member.name] = data
    require(set(result) == SERVICE_FILES, 'UZZ bundle is incomplete.')
    return result


def prepare_source(dependency):
    files = read_source_bundle(dependency)
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', dependency['version']) is not None, 'Invalid UZZ dependency version.')
    runtime = ROOT / '.runtime'
    require(not runtime.is_symlink(), 'Refusing a symlink runtime directory.')
    runtime.mkdir(mode=0o700, exist_ok=True)
    target = runtime / ('uzz-source-' + dependency['version'])
    require(not target.is_symlink(), 'Refusing a symlink service directory.')
    target.mkdir(mode=0o755, exist_ok=True)
    for name, data in files.items():
        path = target / name
        require(not path.is_symlink(), 'Refusing a symlink service file.')
        path.write_bytes(data)
        path.chmod(0o644)
    target.chmod(0o755)
    return target


def start():
    lock = check_materials()
    value = config()
    require(not any(c in str(ROOT) for c in ',\n\r'), 'Project path cannot contain commas or line breaks.')
    require(sys.platform.startswith('linux'), 'This installation helper currently requires execution on the Linux Docker host; other environments need adaptation.')
    for name in [SONG, SOURCE]:
        require(existing('container', name) is None, 'Container name already exists: ' + name + '. No existing container is replaced. See docs/operations.md.')
    server = json.loads(docker('info', '--format', '{{json .}}', capture=True))
    require(server.get('OSType') == 'linux' and server.get('Architecture') in ['x86_64', 'amd64'], 'The current helper and pinned images require Linux amd64; other platforms need adaptation.')
    require(not os.environ.get('DOCKER_HOST'), 'This helper requires a local Docker daemon, without DOCKER_HOST.')
    context = docker('context', 'inspect', capture=True)
    require(json.loads(context)[0]['Endpoints']['docker']['Host'].startswith('unix://'), 'This helper requires a local Unix Docker socket.')
    music, data, downloads = prepare_paths(value)
    songloft = lock['songloft']
    image_id = local_image_id(songloft['image'], songloft['platform'])
    output = docker('run', '--rm', '--network', 'none', '--entrypoint', '/app/songloft', image_id, '-version', capture=True)
    require(re.search(r'(?<![\w.])v?2\.13\.5(?![\w.])', output) is not None, 'Image binary does not report v2.13.5; no application containers started.')
    source_image = lock['browserless']['image']
    if existing('image', source_image) is None:
        docker('pull', '--platform', lock['browserless']['platform'], source_image)
    runtime = ROOT / '.runtime'
    require(not runtime.is_symlink(), 'Refusing a symlink runtime directory.')
    runtime.mkdir(mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    source_path = prepare_source(lock['uzz_source'])
    private_file(runtime / 'songloft.env', 'ADMIN_USERNAME=' + value['admin_username'] + '\nADMIN_PASSWORD=' + value['admin_password'] + '\nPUID=\nPGID=\nTZ=Asia/Shanghai\n')
    private_file(runtime / 'uzz.env', 'TOKEN=' + value['uzz_token'] + '\nCONCURRENT=1\nQUEUED=1\nTIMEOUT=900000\nSESSION_MS=900000\nENABLE_DEBUGGER=false\nDEBUG=\n')
    network = existing('network', NETWORK)
    if network is None:
        docker('network', 'create', '--driver', 'bridge', '--label', LABEL + '=' + value['deployment_id'], NETWORK)
    else:
        require((network.get('Labels') or {}).get(LABEL) == value['deployment_id'], 'Existing network belongs to a different deployment; not changed.')
    common = ['--restart', 'unless-stopped', '--memory', '1g', '--network', NETWORK,
              '--label', LABEL + '=' + value['deployment_id'], '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3']
    docker('create', '--name', SONG, *common, '--network-alias', 'songloft',
           '--env-file', str(runtime / 'songloft.env'), '--publish', value['host_ip'] + ':' + str(value['songloft_port']) + ':58091',
           '--mount', 'type=bind,src=' + str(data) + ',dst=/app/data',
           '--mount', 'type=bind,src=' + str(music) + ',dst=/app/music,readonly',
           '--mount', 'type=bind,src=' + str(downloads) + ',dst=/app/music/uzz-online',
           '--health-cmd', 'wget -q -O /dev/null http://127.0.0.1:58091/api/v1/health || exit 1',
           '--health-interval', '30s', '--health-timeout', '5s', '--health-start-period', '60s', '--health-retries', '3', image_id)
    # Local playback starts independently of online-source readiness.
    docker('start', SONG)
    docker('create', '--name', SOURCE, *common, '--network-alias', 'uzz-source', '--init', '--shm-size', '512m',
           '--env-file', str(runtime / 'uzz.env'), '--mount', 'type=bind,src=' + str(source_path) + ',dst=/uzz-code,readonly',
           '--health-cmd', 'node /uzz-code/health.mjs', '--health-interval', '30s', '--health-timeout', '5s',
           '--health-start-period', '90s', '--health-retries', '3', source_image, 'sh', '/uzz-code/start.sh')
    docker('start', SOURCE)
    print('Started two new containers. Open http://' + value['host_ip'] + ':' + str(value['songloft_port']))
    print('Wait about 30-90 seconds, run status, then follow README plugin configuration. Credentials are only in config.json.')


def status():
    value = config()
    for name in [SONG, SOURCE]:
        item = existing('container', name)
        if item is None:
            print(json.dumps({'container': name, 'state': 'missing'}))
            continue
        require((item.get('Config', {}).get('Labels') or {}).get(LABEL) == value['deployment_id'], 'Refusing a container owned by another deployment: ' + name)
        state = item['State']
        print(json.dumps({'container': name, 'state': state['Status'], 'health': state.get('Health', {}).get('Status'),
                          'restartCount': item.get('RestartCount'), 'oomKilled': state.get('OOMKilled')}))
    source = existing('container', SOURCE)
    if source and source['State'].get('Running'):
        docker('exec', SOURCE, 'node', '/uzz-code/health.mjs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'init', 'pull', 'start', 'status'])
    args = parser.parse_args()
    try:
        if args.action == 'check':
            check_materials()
            print('Deployment materials verified. No configuration or Docker calls required.')
        elif args.action == 'init':
            init()
        elif args.action == 'pull':
            pull()
        elif args.action == 'start':
            start()
        else:
            status()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        # Do not echo configuration or subprocess argv containing private values.
        if isinstance(error, subprocess.CalledProcessError):
            print('Failed: external command exited with code ' + str(error.returncode) + '. See the command output; no existing service was removed.', file=sys.stderr)
        elif isinstance(error, OSError):
            print('Failed: filesystem/tool error (' + type(error).__name__ + '). Check paths, permissions and required tools.', file=sys.stderr)
        else:
            print('Failed: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

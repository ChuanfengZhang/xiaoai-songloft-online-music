import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import tarfile
import shutil
import subprocess
import sys
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deployment', ROOT / 'scripts/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)



def write_fixture_materials(root):
    """Synthetic artifacts keep the public test suite independent of private UZZ files."""
    lock = json.loads((ROOT / 'versions.json').read_text())
    notices = {'LICENSE.txt': (ROOT / 'UZZ-LICENSE.md').read_bytes(),
               'APACHE-2.0.txt': (ROOT / 'LICENSE').read_bytes(),
               'THIRD_PARTY.md': b'Test fixture notices only.\n'}
    service = {name: ('// Synthetic test fixture: ' + name + '\n').encode()
               for name in deploy.SERVICE_FILES if name not in notices}
    service.update(notices)
    bundle = root / 'packages' / lock['uzz_source']['bundle']['file']
    bundle.parent.mkdir(exist_ok=True)
    with tarfile.open(bundle, 'w:gz') as archive:
        for name, data in sorted(service.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    lock['uzz_source']['bundle']['sha256'] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    lock['uzz_source']['bundle']['files'] = {name: hashlib.sha256(data).hexdigest() for name, data in service.items()}
    (root / 'plugins').mkdir(exist_ok=True)
    for item in lock['plugins']:
        contents = {'main.js': b'// Synthetic plugin fixture, not a working music plugin.\n'}
        if item['entryPath'] == 'uzz-source':
            contents.update(notices)
        canonical = ''.join(name + '\n' + hashlib.sha256(contents[name]).hexdigest() + '\n' for name in sorted(contents))
        manifest = dict(item, main='main.js', entryHash=hashlib.sha256(contents['main.js']).hexdigest(),
                        zipHash=hashlib.sha256(canonical.encode()).hexdigest())
        path = root / 'plugins' / item['file']
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in contents.items(): archive.writestr(name, data)
            archive.writestr('plugin.json', json.dumps(manifest))
        item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / 'versions.json').write_text(json.dumps(lock))
    return lock


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(deploy, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        example = json.loads((ROOT / 'config.example.json').read_text())
        (self.root / 'config.example.json').write_text(json.dumps(example))
        self.stdout = io.StringIO()
        with contextlib.redirect_stdout(self.stdout):
            deploy.init()
        self.config = json.loads((self.root / 'config.json').read_text())
        self.music = self.root / 'music'
        self.music.mkdir()
        (self.music / 'original.mp3').write_bytes(b'original')
        self.config.update(host_ip='192.168.1.100', music_dir=str(self.music), data_dir=str(self.root / 'data'))
        (self.root / 'config.json').write_text(json.dumps(self.config))
        self.lock = write_fixture_materials(self.root)
        self.dependency = self.lock['uzz_source']

    def image(self):
        (self.root / 'versions.json').write_text(json.dumps({
            'songloft': {'image': 'songloft/songloft:2.13.5', 'platform': 'linux/amd64'},
            'browserless': {'image': 'ghcr.io/browserless/chromium@sha256:' + 'a' * 64, 'platform': 'linux/amd64'},
            'plugins': self.lock['plugins'],
            'uzz_source': self.dependency
        }))
        return 'sha256:' + 'b' * 64

    def docker_result(self, *args, **kwargs):
        if args[:1] == ('info',):
            return json.dumps({'OSType': 'linux', 'Architecture': 'x86_64'})
        if args[:2] == ('context', 'inspect'):
            return json.dumps([{'Endpoints': {'docker': {'Host': 'unix:///var/run/docker.sock'}}}])
        if args[:2] == ('image', 'inspect'):
            return 'sha256:' + 'b' * 64 + '\n'
        if args[:1] == ('run',):
            return 'Songloft Version: v2.13.5\nBuild Type: full\n'
        return ''

    def test_missing_materials_list_all_locations_before_configuration_or_docker(self):
        missing = [Path('plugins') / p['file'] for p in self.lock['plugins']]
        missing.append(Path('packages') / self.dependency['bundle']['file'])
        for relative in missing:
            (self.root / relative).unlink()
        (self.root / 'config.json').unlink()
        with patch.object(deploy, 'docker') as docker, patch.object(deploy, 'existing') as existing:
            with self.assertRaises(ValueError) as error:
                deploy.start()
        for relative in missing:
            self.assertIn(relative.as_posix(), str(error.exception))
        self.assertIn(str(self.root), str(error.exception))
        self.assertIn('不要手工解包', str(error.exception))
        docker.assert_not_called()
        existing.assert_not_called()
        self.assertFalse((self.root / 'data').exists())
        self.assertFalse((self.music / 'uzz-online').exists())
        self.assertFalse((self.root / '.runtime').exists())

    def test_wrong_plugin_or_service_material_is_rejected_before_docker(self):
        for relative in [Path('plugins') / self.lock['plugins'][1]['file'],
                         Path('packages') / self.dependency['bundle']['file']]:
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(b'wrong-version-or-corrupt-download')
                try:
                    with patch.object(deploy, 'docker') as docker, patch.object(deploy, 'existing') as existing:
                        with self.assertRaisesRegex(ValueError, '校验不通过') as error:
                            deploy.start()
                    self.assertIn(relative.as_posix(), str(error.exception))
                    docker.assert_not_called()
                    existing.assert_not_called()
                finally:
                    path.write_bytes(original)

    def test_check_cli_needs_neither_private_configuration_nor_docker(self):
        (self.root / 'scripts').mkdir()
        shutil.copy2(ROOT / 'scripts/deploy.py', self.root / 'scripts/deploy.py')
        (self.root / 'config.json').unlink()
        supplemental = [self.root / 'plugins' / self.lock['plugins'][1]['file'],
                        self.root / 'packages' / self.dependency['bundle']['file']]
        saved = {path: path.read_bytes() for path in supplemental}
        for path in supplemental:
            path.unlink()
        command = [sys.executable, '-B', str(self.root / 'scripts/deploy.py'), 'check']
        missing = subprocess.run(command, capture_output=True, text=True, env={'PATH': ''})
        self.assertEqual(missing.returncode, 1)
        for path in supplemental:
            self.assertIn(path.relative_to(self.root).as_posix(), missing.stderr)
            path.write_bytes(saved[path])
        self.assertNotIn('Traceback', missing.stderr)
        result = subprocess.run(command, capture_output=True, text=True, env={'PATH': ''})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('materials verified', result.stdout)
        self.assertFalse((self.root / 'config.json').exists())

    def test_full_export_cli_gives_missing_material_guidance_without_traceback(self):
        (self.root / 'scripts').mkdir()
        for name in ['deploy.py', 'build.py']:
            shutil.copy2(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        missing = [Path('plugins') / self.lock['plugins'][1]['file'],
                   Path('packages') / self.dependency['bundle']['file']]
        for relative in missing:
            (self.root / relative).unlink()
        result = subprocess.run([sys.executable, '-B', str(self.root / 'scripts/build.py'), '--target', 'full',
                                 '--output', str(self.root.parent / (self.root.name + '-delivery'))],
                                capture_output=True, text=True, env={'PATH': ''})
        self.assertEqual(result.returncode, 1)
        for relative in missing:
            self.assertIn(relative.as_posix(), result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_init_credentials_are_private_random_and_never_overwritten(self):
        data = (self.root / 'config.json').read_bytes()
        self.assertEqual((self.root / 'config.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(self.config['admin_password']), 48)
        self.assertNotEqual(self.config['admin_password'], self.config['uzz_token'])
        self.assertNotIn(self.config['admin_password'], self.stdout.getvalue())
        with self.assertRaises(FileExistsError):
            deploy.init()
        self.assertEqual((self.root / 'config.json').read_bytes(), data)

    def test_host_ip_configuration_and_legacy_field_are_accepted(self):
        self.assertEqual(deploy.config()['host_ip'], '192.168.1.100')
        legacy = dict(self.config)
        legacy['nas_ip'] = legacy.pop('host_ip')
        (self.root / 'config.json').write_text(json.dumps(legacy))
        self.assertEqual(deploy.config()['host_ip'], '192.168.1.100')

    def test_mount_matching_detects_noexec_and_prefers_longest_mount(self):
        text = '/dev/root / ext4 rw 0 0\ntmpfs /tmp tmpfs rw,noexec 0 0\n/dev/volume /volume1 btrfs rw 0 0\n'
        self.assertIn('noexec', deploy.filesystem_options('/tmp/new/data', text))
        self.assertNotIn('noexec', deploy.filesystem_options('/volume1/new/data', text))

    def test_data_outside_library_and_download_symlink_protection(self):
        bad = dict(self.config, data_dir=str(self.music / 'data'))
        with self.assertRaisesRegex(ValueError, 'outside music_dir'):
            deploy.prepare_paths(bad)
        (self.music / 'uzz-online').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            deploy.prepare_paths(self.config)
        self.assertEqual((self.music / 'original.mp3').read_bytes(), b'original')

    def test_empty_data_directory_is_claimed_and_same_deployment_can_retry(self):
        Path(self.config['data_dir']).mkdir()
        _, data, _ = deploy.prepare_paths(self.config)
        marker = data / deploy.DATA_OWNER_FILE
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(marker.read_text())['deployment_id'], self.config['deployment_id'])
        database = data / 'songloft.db'
        database.write_bytes(b'owned database')
        marker_bytes = marker.read_bytes()
        deploy.prepare_paths(self.config)
        self.assertEqual(database.read_bytes(), b'owned database')
        self.assertEqual(marker.read_bytes(), marker_bytes)

    @patch.dict('os.environ', {}, clear=True)
    def test_unowned_data_is_rejected_before_image_or_container_operations(self):
        data = Path(self.config['data_dir'])
        data.mkdir()
        database = data / 'songloft.db'
        database.write_bytes(b'existing database')
        with patch.object(deploy.sys, 'platform', 'linux'), patch.object(deploy, 'existing', return_value=None), \
             patch.object(deploy, 'docker', side_effect=self.docker_result) as docker:
            with self.assertRaisesRegex(ValueError, 'data_dir is not empty'):
                deploy.start()
        self.assertEqual([call.args[0] for call in docker.call_args_list], ['info', 'context'])
        self.assertEqual(database.read_bytes(), b'existing database')
        self.assertEqual([p.name for p in data.iterdir()], ['songloft.db'])
        self.assertFalse((self.music / 'uzz-online').exists())

    def test_foreign_or_invalid_data_ownership_is_not_overwritten(self):
        data = Path(self.config['data_dir'])
        data.mkdir()
        marker = data / deploy.DATA_OWNER_FILE
        for content in [json.dumps({'deployment_id': 'another-installation'}), '{}', '[]', 'invalid json']:
            with self.subTest(content=content):
                marker.write_text(content)
                with self.assertRaises(ValueError):
                    deploy.prepare_paths(self.config)
                self.assertEqual(marker.read_text(), content)
        marker.unlink()
        outside = self.root / 'ownership.json'
        outside.write_text(json.dumps({'deployment_id': self.config['deployment_id']}))
        marker.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'ownership file'):
            deploy.prepare_paths(self.config)
        self.assertTrue(marker.is_symlink())
        self.assertFalse((self.music / 'uzz-online').exists())

    def test_pull_uses_official_version_and_pinned_source_without_creating_containers(self):
        self.image()
        lock = json.loads((self.root / 'versions.json').read_text())
        with patch.object(deploy, 'docker') as docker, contextlib.redirect_stdout(io.StringIO()):
            deploy.pull()
        self.assertEqual([call.args for call in docker.call_args_list], [
            ('pull', '--platform', 'linux/amd64', lock[name]['image']) for name in ['songloft', 'browserless']
        ])

    @patch.dict('os.environ', {}, clear=True)
    def test_start_uses_pulled_image_id_and_readonly_library_with_writable_child(self):
        image_id = self.image()
        with patch.object(deploy.sys, 'platform', 'linux'), patch.object(deploy, 'existing', return_value=None), \
             patch.object(deploy, 'docker', side_effect=self.docker_result) as docker:
            with contextlib.redirect_stdout(io.StringIO()):
                deploy.start()
        calls = [call.args for call in docker.call_args_list]
        song = next(args for args in calls if args[:3] == ('create', '--name', deploy.SONG))
        mounts = [song[i + 1] for i, arg in enumerate(song) if arg == '--mount']
        self.assertTrue(any(item.endswith('dst=/app/music,readonly') for item in mounts))
        self.assertTrue(any(item.endswith('dst=/app/music/uzz-online') and 'readonly' not in item for item in mounts))
        self.assertEqual(song[-1], image_id)
        self.assertIn(('pull', '--platform', 'linux/amd64', 'songloft/songloft:2.13.5'), calls)
        self.assertFalse(any(args[0] == 'load' for args in calls))
        version_check = next(args for args in calls if args[0] == 'run')
        self.assertEqual(version_check[-2:], (image_id, '-version'))
        source = next(args for args in calls if args[:3] == ('create', '--name', deploy.SOURCE))
        self.assertNotIn('--publish', source)
        source_mount = source[source.index('--mount') + 1]
        self.assertIn(str(self.root / '.runtime' / ('uzz-source-' + self.dependency['version'])), source_mount)
        self.assertNotIn('src/source', source_mount)
        self.assertEqual(set(p.name for p in (self.root / '.runtime' / ('uzz-source-' + self.dependency['version'])).iterdir()), deploy.SERVICE_FILES)
        self.assertNotIn('--cpus', source)
        self.assertNotIn('--pids-limit', source)
        self.assertNotIn(self.config['admin_password'], str(calls))
        self.assertNotIn(self.config['uzz_token'], str(calls))
        self.assertEqual((self.root / '.runtime/songloft.env').stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.music / 'uzz-online').is_dir())
        self.assertEqual((self.music / 'original.mp3').read_bytes(), b'original')

    def test_existing_container_is_never_replaced(self):
        with patch.object(deploy.sys, 'platform', 'linux'), patch.object(deploy, 'existing', return_value={'Name': 'existing'}), \
             patch.object(deploy, 'docker') as docker:
            with self.assertRaisesRegex(ValueError, 'name already exists'):
                deploy.start()
        docker.assert_not_called()

    @patch.dict('os.environ', {}, clear=True)
    def test_wrong_binary_version_stops_before_application_container_creation(self):
        self.image()
        def fake(*args, **kwargs):
            return 'Songloft Version: v2.13.0' if args[0] == 'run' else self.docker_result(*args, **kwargs)
        with patch.object(deploy.sys, 'platform', 'linux'), patch.object(deploy, 'existing', return_value=None), \
             patch.object(deploy, 'docker', side_effect=fake) as docker:
            with self.assertRaisesRegex(ValueError, 'does not report v2.13.5'):
                deploy.start()
        self.assertFalse(any(call.args[0] == 'create' for call in docker.call_args_list))

    def test_cached_image_is_used_without_repull_and_invalid_identity_is_rejected(self):
        with patch.object(deploy, 'existing', return_value={'Id': 'cached'}), \
             patch.object(deploy, 'docker', side_effect=self.docker_result) as docker:
            image_id = deploy.local_image_id('songloft/songloft:2.13.5', 'linux/amd64')
        self.assertEqual(image_id, 'sha256:' + 'b' * 64)
        self.assertFalse(any(call.args[0] == 'pull' for call in docker.call_args_list))
        with patch.object(deploy, 'existing', return_value={'Id': 'cached'}), \
             patch.object(deploy, 'docker', return_value='not-an-image-id'):
            with self.assertRaisesRegex(ValueError, 'Invalid local image identity'):
                deploy.local_image_id('songloft/songloft:2.13.5', 'linux/amd64')

    def test_bundle_checksum_failure_stops_before_writing_runtime(self):
        path = self.root / 'packages' / self.dependency['bundle']['file']
        path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            deploy.prepare_source(self.dependency)
        self.assertFalse((self.root / '.runtime').exists())

    def test_service_bundle_extraction_is_exact_and_readable(self):
        target = deploy.prepare_source(self.dependency)
        self.assertEqual(target.stat().st_mode & 0o777, 0o755)
        self.assertEqual(set(p.name for p in target.iterdir()), deploy.SERVICE_FILES)
        for name, expected in self.dependency['bundle']['files'].items():
            self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), expected)
            self.assertEqual((target / name).stat().st_mode & 0o777, 0o644)
        self.assertEqual((target / 'LICENSE.txt').read_bytes(), (ROOT / 'UZZ-LICENSE.md').read_bytes())
        self.assertEqual((target / 'APACHE-2.0.txt').read_bytes(), (ROOT / 'LICENSE').read_bytes())

    def test_path_traversal_and_links_are_rejected_even_with_matching_archive_hash(self):
        for mode in ['traversal', 'link']:
            dependency = json.loads(json.dumps(self.dependency))
            path = self.root / 'packages' / dependency['bundle']['file']
            with tarfile.open(path, 'w:gz') as archive:
                for index, name in enumerate(sorted(deploy.SERVICE_FILES)):
                    member = tarfile.TarInfo('../escape' if mode == 'traversal' and index == 0 else name)
                    data = b'fixture'
                    if mode == 'link' and index == 0:
                        member.type = tarfile.SYMTYPE
                        member.linkname = '/tmp/outside'
                    else:
                        member.size = len(data)
                    archive.addfile(member, None if member.issym() else io.BytesIO(data))
            dependency['bundle']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                deploy.prepare_source(dependency)
            self.assertFalse((self.root / '.runtime').exists())


if __name__ == '__main__':
    unittest.main()

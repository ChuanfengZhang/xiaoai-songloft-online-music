import secrets
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from test_deploy import ROOT, write_fixture_materials


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project'
        self.project.mkdir()
        files = [ROOT / name for name in ['README.md', 'LICENSE', 'UZZ-LICENSE.md', 'THIRD_PARTY.md',
                                          '.gitignore', 'config.example.json', 'versions.json']]
        for pattern in ['scripts/*.py', 'tests/test_*.py', 'docs/*.md']:
            files.extend(ROOT.glob(pattern))
        for path in files:
            destination = self.project / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        self.lock = write_fixture_materials(self.project)
        self.materials = [Path('plugins') / item['file'] for item in self.lock['plugins']]
        self.materials.append(Path('packages') / self.lock['uzz_source']['bundle']['file'])
        self.run_cli(self.project, 'build.py', success=True)
        self.private_marker = secrets.token_hex(32)
        for relative in ['config.json', '.env', '.runtime/token.env', 'data/songloft.db',
                         'src/secret.js', 'docs/private.env', 'scripts/secret.private',
                         'plugins/unlisted-source.js', 'tests/private.json']:
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.private_marker)

    def run_cli(self, project, script, *args, success):
        result = subprocess.run([sys.executable, '-B', str(project / 'scripts' / script), *args],
                                capture_output=True, text=True, env={'PATH': ''})
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def export(self, target, name):
        output = self.base / name
        self.run_cli(self.project, 'build.py', '--target', target, '--output', str(output), success=True)
        return output

    def assert_no_private_state(self, directory):
        for path in directory.rglob('*'):
            if path.is_file():
                self.assertNotIn(self.private_marker.encode(), path.read_bytes(), str(path))
        for name in ['config.json', '.env', '.runtime', 'data', 'src']:
            self.assertFalse((directory / name).exists())

    def test_public_export_without_artifacts_and_supplemented_install_check(self):
        saved = {relative: (self.project / relative).read_bytes() for relative in self.materials}
        for relative in self.materials:
            (self.project / relative).unlink()
        public = self.export('public', 'public')
        self.assert_no_private_state(public)
        self.assertFalse((public / 'plugins').exists())
        self.assertFalse((public / 'packages').exists())
        self.run_cli(public, 'build.py', '--check', success=True)
        missing = self.run_cli(public, 'deploy.py', 'check', success=False)
        for relative in self.materials:
            self.assertIn(relative.as_posix(), missing.stderr)
        # Both editions use the exact same files and commands after supplementation.
        for relative, data in saved.items():
            destination = public / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        self.run_cli(public, 'deploy.py', 'check', success=True)
        self.run_cli(public, 'build.py', '--check', success=True)

    def test_full_export_contains_only_locked_materials_and_matching_zip(self):
        full = self.export('full', 'full')
        self.assert_no_private_state(full)
        for relative in self.materials:
            self.assertEqual((full / relative).read_bytes(), (self.project / relative).read_bytes())
        self.assertFalse((full / 'plugins/unlisted-source.js').exists())
        self.run_cli(full, 'deploy.py', 'check', success=True)
        self.run_cli(full, 'build.py', '--check', success=True)
        with zipfile.ZipFile(full.with_suffix('.zip')) as archive:
            members = {Path(name).relative_to('xiaoai-songloft-online-music').as_posix(): archive.read(name)
                       for name in archive.namelist()}
        disk = {p.relative_to(full).as_posix(): p.read_bytes() for p in full.rglob('*') if p.is_file()}
        self.assertEqual(members, disk)
        public = self.export('public', 'public-for-comparison')
        for p in public.rglob('*'):
            if p.is_file():
                self.assertEqual(p.read_bytes(), (full / p.relative_to(public)).read_bytes())

    def test_existing_output_is_not_overwritten(self):
        output = self.base / 'existing'
        output.mkdir()
        sentinel = output / 'keep.txt'
        sentinel.write_text('keep')
        result = self.run_cli(self.project, 'build.py', '--target', 'full', '--output', str(output), success=False)
        self.assertIn('already exists', result.stderr)
        self.assertEqual(sentinel.read_text(), 'keep')
        self.assertFalse(output.with_suffix('.zip').exists())

    def test_corrupt_or_missing_material_prevents_full_output(self):
        path = self.project / self.materials[1]
        path.write_bytes(b'corrupt')
        output = self.base / 'invalid'
        self.run_cli(self.project, 'build.py', '--target', 'full', '--output', str(output), success=False)
        self.assertFalse(output.exists())
        path.unlink()
        result = self.run_cli(self.project, 'build.py', '--target', 'full', '--output', str(output), success=False)
        self.assertIn(self.materials[1].as_posix(), result.stderr)
        self.assertFalse(output.exists())

    def test_identical_input_produces_identical_zip(self):
        first = self.export('full', 'first')
        second = self.export('full', 'second')
        self.assertEqual(first.with_suffix('.zip').read_bytes(), second.with_suffix('.zip').read_bytes())

    def test_changed_public_source_prevents_export(self):
        (self.project / 'README.md').write_text('Changed after checksum generation')
        output = self.base / 'changed'
        result = self.run_cli(self.project, 'build.py', '--target', 'public', '--output', str(output), success=False)
        self.assertIn('Public file list/content changed', result.stderr)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()

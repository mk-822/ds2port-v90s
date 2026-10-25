import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from ds2port.resources import root
from ds2port.installer import required_ext4_bytes


spec = importlib.util.spec_from_file_location('common_prefix', root() / 'runtime/templates/common_prefix.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
installer_spec = importlib.util.spec_from_file_location('common_remote_installer', root() / 'runtime/install_remote.py')
remote = importlib.util.module_from_spec(installer_spec)
installer_spec.loader.exec_module(remote)


class StorageWithoutMounts:
    """Exercise migration on Windows; actual mounts are checked on Linux/device."""
    def __init__(self, cache):
        self.cache = cache

    def layout(self, runtime):
        return [(runtime / 'prefix/drive_c/windows' / name,
                 self.cache / 'wine-10.0-amd64-wow64/lib/wine' / arch,
                 runtime / 'prefix-overlays' / name / 'upper',
                 runtime / 'prefix-overlays' / name / 'work')
                for name, arch in [('system32', 'x86_64-windows'), ('syswow64', 'i386-windows')]]

    def ensure(self, runtime):
        if runtime.parent.name == '.shared':
            (runtime / 'prefix-storage.json').write_text('{}')
            for target, lower, upper, work in self.layout(runtime):
                if not upper.exists():
                    upper.parent.mkdir(parents=True)
                    if target.exists():
                        target.rename(upper)
                    else:
                        upper.mkdir()
                    target.mkdir(parents=True, exist_ok=True)

    def unmount(self, runtime):
        pass


class CommonPrefix(unittest.TestCase):
    def test_shared_installation_lock_excludes_launch_and_preserves_an_existing_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'display.lock'
            with self.assertRaisesRegex(RuntimeError, 'failed transaction'):
                with remote.shared_environment_lock(lock):
                    self.assertTrue(lock.is_dir())
                    with self.assertRaises(ValueError):
                        with remote.shared_environment_lock(lock):
                            self.fail('Second installer acquired the shared lock')
                    self.assertTrue(lock.is_dir())
                    raise RuntimeError('failed transaction')
            self.assertFalse(lock.exists())

    def fixture(self, directory, ident, registry=None, ready=True):
        runtime = directory / ident
        cache = directory / '.shared' / ('runtime-' + 'a' * 64)
        runtime.mkdir(parents=True)
        cache.mkdir(parents=True, exist_ok=True)
        (runtime / 'shared-runtime.json').write_text(json.dumps({'schema': 1, 'path': str(cache)}))
        if ready:
            prefix = runtime / 'prefix'
            prefix.mkdir()
            for name in common.REGISTRIES:
                text = registry if name == 'user.reg' and registry else 'WINE REGISTRY Version 2\n\n'
                (prefix / name).write_text(text, encoding='utf-8')
            (runtime / 'prefix-configured-v2').touch()
        return runtime, StorageWithoutMounts(cache)

    def test_shared_registry_imports_application_values_without_overwriting_common_settings(self):
        destination = 'WINE REGISTRY Version 2\n\n[Software\\\\Compile] 1\n"GameA"="saved"\n"Locale"="ja"\n'
        source = 'WINE REGISTRY Version 2\n\n[software\\\\compile] 2\n"GameB"="続き"\n"Locale"="other"\n"Binary"=hex:01,02,\\\n  03,04\n#time=123\n\n[Software\\\\NewGame] 3\n@="default"\n'
        merged = common.merge_registry(destination, source)
        self.assertIn('"GameA"="saved"', merged)
        self.assertIn('"GameB"="続き"', merged)
        self.assertIn('"Locale"="ja"', merged)
        self.assertNotIn('"Locale"="other"', merged)
        self.assertIn('"Binary"=hex:01,02,\\\n  03,04', merged)
        self.assertIn('@="default"', merged)
        self.assertEqual(common.merge_registry(merged, source), merged)

    def test_two_existing_games_keep_their_saves_in_one_initialized_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            first, storage = self.fixture(directory, 'first', 'WINE REGISTRY Version 2\n\n[Software\\\\Compile]\n"A"="1"\n')
            second, _ = self.fixture(directory, 'second', 'WINE REGISTRY Version 2\n\n[Software\\\\Compile]\n"B"="2"\n')
            for runtime, name in [(first, 'save-a.dat'), (second, 'save-b.dat')]:
                folder = runtime / 'prefix/drive_c/users/root/Documents'
                folder.mkdir(parents=True)
                (folder / name).write_bytes(name.encode())
            shared = common.prepare(first, storage)
            self.assertEqual(common.prepare(second, storage), shared)
            for name in ('save-a.dat', 'save-b.dat'):
                self.assertEqual((shared / 'prefix/drive_c/users/root/Documents' / name).read_bytes(), name.encode())
            self.assertTrue(common.initialized(shared))
            self.assertIn('"A"="1"', (shared / 'prefix/user.reg').read_text())
            self.assertIn('"B"="2"', (shared / 'prefix/user.reg').read_text())
            self.assertEqual((second / 'prefix/user.reg').read_bytes(), (shared / 'migration-backups/second/user.reg').read_bytes())

    def test_old_prefix_does_not_overwrite_new_saves_on_later_launches(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime, storage = self.fixture(Path(directory), 'first')
            save = runtime / 'prefix/save.dat'
            save.write_bytes(b'old')
            shared = common.prepare(runtime, storage)
            (shared / 'prefix/save.dat').write_bytes(b'new progress')
            common.prepare(runtime, storage)
            self.assertEqual((shared / 'prefix/save.dat').read_bytes(), b'new progress')

    def test_conflicting_files_are_preserved_and_explicit_dlls_replace_only_builtins(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source, target, backup, lower = [directory / name for name in ('source', 'target', 'backup', 'lower')]
            for folder in (source, target, lower):
                folder.mkdir()
            (source / 'game.dll').write_bytes(b'custom')
            (target / 'game.dll').write_bytes(b'builtin')
            (lower / 'game.dll').write_bytes(b'builtin')
            (source / 'save.dat').write_bytes(b'other progress')
            (target / 'save.dat').write_bytes(b'current progress')
            common.merge_files(source, target, backup, lower)
            self.assertEqual((target / 'game.dll').read_bytes(), b'custom')
            self.assertEqual((target / 'save.dat').read_bytes(), b'current progress')
            self.assertEqual((backup / 'save.dat').read_bytes(), b'other progress')

    def test_new_games_reuse_existing_common_prefix_without_creating_private_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            first, storage = self.fixture(directory, 'first')
            shared = common.prepare(first, storage)
            new, _ = self.fixture(directory, 'newgame', ready=False)
            self.assertEqual(common.prepare(new, storage), shared)
            self.assertFalse((new / 'prefix').exists())
            self.assertTrue(common.initialized(shared))

    def test_common_initialization_and_migration_capacity_are_reserved_once(self):
        mib = 1024 ** 2
        first = required_ext4_bytes(0, 0, 0, runtime_cached=True)
        shared = required_ext4_bytes(0, 0, 0, runtime_cached=True, prefix_ready=True)
        seed = required_ext4_bytes(0, 0, 0, runtime_cached=True, prefix_ready=True, shared_prefix_seed_bytes=160*mib)
        self.assertEqual(first - shared, 640 * mib)
        self.assertEqual(seed - shared, 160 * mib)

    def test_first_install_defers_initialization_and_later_games_reuse_it(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            first, storage = self.fixture(directory, 'first', ready=False)
            shared = common.prepare(first, storage)
            self.assertFalse(common.initialized(shared))
            self.assertFalse((first / 'prefix').exists())
            # Simulate the launcher's successful Wineboot and Japanese setup.
            prefix = shared / 'prefix'
            prefix.mkdir()
            for name in common.REGISTRIES:
                (prefix / name).write_text('WINE REGISTRY Version 2\n\n')
            (shared / 'prefix-configured-v2').touch()
            second, _ = self.fixture(directory, 'second', ready=False)
            self.assertEqual(common.prepare(second, storage), shared)
            self.assertTrue(common.initialized(shared))
            self.assertFalse((second / 'prefix').exists())


if __name__ == '__main__':
    unittest.main()

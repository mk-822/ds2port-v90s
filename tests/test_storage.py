import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch, Mock
from ds2port.resources import root
from ds2port.installer import required_ext4_bytes


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


remote = module('cache_installer', root() / 'runtime/install_remote.py')
storage = module('prefix_storage', root() / 'runtime/templates/prefix_storage.py')


class SharedRuntime(unittest.TestCase):
    def fixture(self, directory):
        runtimes, ports = directory / 'runtimes', directory / 'ports'
        installed = runtimes / 'first'
        (ports / 'first').mkdir(parents=True)
        installed.mkdir(parents=True)
        (ports / 'first/ds2port-installed.json').write_text('{}')
        files, entries = {}, [['bundle.json', 'file', 0o644, '', 0]]
        for name in ['wine-10.0-amd64-wow64/lib/wine/ntdll.dll', 'native/tool', 'shared/runtime/box64']:
            path = ports / 'first/runtime/box64' if name.startswith('shared/') else installed / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            entries.append([name, 'file', stat.S_IMODE(path.stat().st_mode), '', path.stat().st_size])
        description = {'runtime_sha256': 'a' * 64, 'bundle': {'schema': 1, 'files': files}, 'entries': entries}
        return runtimes, ports, description

    def test_cache_reuses_existing_files_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            runtimes, ports, description = self.fixture(directory)
            cache = remote.prepare_cache(description, runtimes, ports)
            self.assertTrue(remote.cache_valid(cache, description))
            self.assertTrue(os.path.samefile(cache / 'native/tool', runtimes / 'first/native/tool'))
            clone = directory / 'clone'
            remote.copy_cache_layout(description, clone, {name: cache / name for name in description['bundle']['files']})
            (clone / 'replacement').write_bytes(b'new runtime version')
            (clone / 'replacement').replace(clone / 'native/tool')
            self.assertEqual((cache / 'native/tool').read_bytes(), b'native/tool')
            self.assertEqual(remote.prepare_cache(description, runtimes, ports), cache)
            (cache / 'native/tool').write_bytes(b'corruption')
            with self.assertRaises(ValueError):
                remote.prepare_cache(description, runtimes, ports)

    def test_incomplete_installation_requires_full_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtimes, ports, description = self.fixture(Path(temporary))
            (runtimes / 'first/native/tool').unlink()
            self.assertIsNone(remote.prepare_cache(description, runtimes, ports))
            self.assertFalse((runtimes / '.shared').exists())

    def test_cache_creation_does_not_consume_the_os_space_reserve(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtimes, ports, description = self.fixture(Path(temporary))
            with patch.object(remote.shutil, 'disk_usage', return_value=Mock(free=64*1024**2)):
                with self.assertRaises(ValueError):
                    remote.prepare_cache(description, runtimes, ports)
            self.assertFalse((runtimes / '.shared').exists())

    def test_archive_dot_prefix_is_normalized_without_mutating_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtimes, ports, description = self.fixture(Path(temporary))
            description['entries'][1][0] = './' + description['entries'][1][0]
            cache = remote.prepare_cache(description, runtimes, ports)
            self.assertTrue(remote.cache_valid(cache, description))

    @unittest.skipUnless(os.name == 'posix' and os.geteuid() == 0, 'root POSIX ownership test')
    def test_build_user_ownership_is_normalized_for_prefix_sharing(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            runtimes, ports, description = self.fixture(directory)
            wine = runtimes / 'first/wine-10.0-amd64-wow64/lib/wine/ntdll.dll'
            os.chown(wine, 1000, 1000)
            cache = remote.prepare_cache(description, runtimes, ports)
            lower = cache / 'wine-10.0-amd64-wow64/lib/wine'
            private = directory / 'private'; private.mkdir()
            (private / 'ntdll.dll').write_bytes(wine.read_bytes())
            self.assertEqual((lower / 'ntdll.dll').stat().st_uid, 0)
            self.assertEqual(storage.compact(private, lower)[0], 1)

    def test_cache_layout_rejects_escape_and_writes_below_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'cache'
            for entries in [
                [['../outside', 'directory', 0o755, '', 0]],
                [['link', 'symlink', 0o777, '../../outside', 0]],
                [['link', 'symlink', 0o777, 'target', 0], ['link/child', 'directory', 0o755, '', 0]],
            ]:
                with self.assertRaises(ValueError):
                    remote.cache_entries({'entries': entries, 'bundle': {'files': {}}}, destination)

    def test_shared_capacity_keeps_first_boot_reserve(self):
        mib = 1024 ** 2
        first = required_ext4_bytes(700*mib, 170*mib, 10*mib, runtime_cached=True)
        existing = required_ext4_bytes(700*mib, 170*mib, 10*mib, runtime_cached=True, prefix_ready=True)
        self.assertEqual(first - existing, 640*mib)
        self.assertEqual(required_ext4_bytes(700*mib, 170*mib, 10*mib) - first, 870*mib)
        self.assertGreaterEqual(existing, 128*mib + 30*mib)


class PrefixCompaction(unittest.TestCase):
    def test_only_identical_builtins_are_removed_from_private_layer(self):
        with tempfile.TemporaryDirectory() as temporary:
            lower, upper = Path(temporary)/'wine', Path(temporary)/'private'
            lower.mkdir(); upper.mkdir()
            for directory in (lower, upper):
                (directory/'ntdll.dll').write_bytes(b'builtin')
                (directory/'game.dll').write_bytes(b'original')
            (upper/'game.dll').write_bytes(b'game-specific replacement')
            (upper/'save.dat').write_bytes(b'private save')
            count, reclaimed = storage.compact(upper, lower)
            self.assertEqual((count, reclaimed), (1, len(b'builtin')))
            self.assertEqual((upper/'game.dll').read_bytes(), b'game-specific replacement')
            self.assertEqual((upper/'save.dat').read_bytes(), b'private save')
            self.assertEqual((lower/'game.dll').read_bytes(), b'original')

    @unittest.skipUnless(hasattr(os, 'getxattr'), 'xattrs require POSIX')
    def test_opaque_private_directory_is_not_deduplicated(self):
        with tempfile.TemporaryDirectory() as temporary:
            lower, upper = Path(temporary)/'wine', Path(temporary)/'private'
            for directory in (lower, upper):
                directory.mkdir()
                (directory/'same.dll').write_bytes(b'same')
            with patch.object(storage.os, 'getxattr', return_value=b'y'):
                self.assertEqual(storage.compact(upper, lower), (0, 0))
            self.assertTrue((upper/'same.dll').exists())


if __name__ == '__main__':
    unittest.main()

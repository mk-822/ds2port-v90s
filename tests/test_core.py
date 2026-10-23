import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from ds2port.installer import prepare_payload, render_template, validate_bundle
from ds2port.profiles import digest, game_executable, patch_executable, profiles
from ds2port.resources import root

spec=importlib.util.spec_from_file_location("remote_installer",root()/"runtime/install_remote.py")
remote=importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)
spec2=importlib.util.spec_from_file_location("prefix_config",root()/"runtime/templates/configure_prefix.py")
prefix_config=importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(prefix_config)


class PrefixConfiguration(unittest.TestCase):
    def test_preserves_unrelated_registry_values(self):
        text='WINE REGISTRY Version 2\n\n[System\\\\CurrentControlSet\\\\Control\\\\Nls\\\\CodePage] 1\n"ACP"="1252"\n"Other"="keep"\n\n[Unrelated] 2\n"X"="Y"\n'
        result=prefix_config.merge_section(text,r'System\\CurrentControlSet\\Control\\Nls\\CodePage',{'ACP':'932'})
        self.assertIn('"ACP"="932"',result)
        self.assertNotIn('"ACP"="1252"',result)
        self.assertIn('"Other"="keep"',result)
        self.assertIn('[Unrelated] 2\n"X"="Y"',result)

    def test_removes_only_requested_font_substitutes(self):
        text='[Software\\\\Wine\\\\Fonts\\\\Replacements] 1\n"MS Gothic"="Noto Sans CJK JP"\n"Other"="Keep Font"\n'
        result=prefix_config.merge_section(text,r'Software\\Wine\\Fonts\\Replacements',{},('MS Gothic',))
        self.assertNotIn('Noto Sans',result)
        self.assertIn('"Other"="Keep Font"',result)


class ArchiveSafety(unittest.TestCase):
    def reject(self, entries):
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/"bad.tar"
            with tarfile.open(archive,"w") as tf:
                for entry in entries:tf.addfile(entry)
            with self.assertRaises(ValueError):remote.safe_extract(archive,Path(temp)/"out")

    def test_parent_traversal(self):
        self.reject([tarfile.TarInfo("../outside")])

    def test_absolute_path(self):
        self.reject([tarfile.TarInfo("/outside")])

    def test_escaping_link(self):
        item=tarfile.TarInfo("link");item.type=tarfile.SYMTYPE;item.linkname="../../outside"
        self.reject([item])

    def test_duplicate_entry(self):
        self.reject([tarfile.TarInfo("file"),tarfile.TarInfo("file")])

    def test_duplicate_normalized_entry(self):
        self.reject([tarfile.TarInfo("file"),tarfile.TarInfo("./file")])

    def test_write_through_symlink(self):
        item=tarfile.TarInfo("link");item.type=tarfile.SYMTYPE;item.linkname="target"
        self.reject([item,tarfile.TarInfo("link/child")])


class Profiles(unittest.TestCase):
    def test_unknown_executable_is_never_patched(self):
        with self.assertRaises(ValueError):patch_executable(b"unrecognized binary",profiles()[0])

    def test_templates_have_no_unresolved_tokens(self):
        values={"PORT":"/mnt/plumos/roms/ports/jump3","RUNTIME":"/mnt/plumos/ports-runtime/jump3","EXE":"JUMP3.EXE"}
        for p in (root()/"runtime/templates").glob("*.in"):
            self.assertNotIn(b"@@",render_template(p.name,values))

    @unittest.skipUnless(os.environ.get("DS2PORT_TEST_GAME"),"set DS2PORT_TEST_GAME to an owned unmodified game folder")
    def test_owned_game_end_to_end_payload(self):
        source=Path(os.environ["DS2PORT_TEST_GAME"])
        profile=profiles()[0]
        exe=game_executable(source,profile)
        before=digest(exe.read_bytes())
        result=patch_executable(exe.read_bytes(),profile)
        self.assertEqual(digest(result),profile["patched_sha256"])
        with tempfile.TemporaryDirectory() as temp:
            payload=Path(temp)/"payload.tar.gz"
            config=prepare_payload(source,None,profile,"jump3-test",payload)
            self.assertEqual(config["preserve"],["SaveData"])
            with tarfile.open(payload) as tf:
                self.assertEqual(digest(tf.extractfile("game/JUMP3.EXE").read()),profile["patched_sha256"])
                self.assertEqual(digest(tf.extractfile("game/JUMP3.original.exe").read()),before)
                self.assertEqual(tf.extractfile("port/assets/fonts/msgothic.ttc").read(4),b"ttcf")
            self.assertEqual(digest(exe.read_bytes()),before)

    @unittest.skipUnless((root()/"bld/runtime.tar.gz").exists(),"build the runtime first")
    def test_runtime_bundle_contains_no_game_or_windows_font(self):
        path=root()/"bld/runtime.tar.gz"
        _,metadata=validate_bundle(path)
        forbidden={"jump3.exe","jump3.original.exe","msgothic.ttc"}
        self.assertFalse(any(Path(name).name.casefold() in forbidden for name in metadata["files"]))
        self.assertIn("native/bin/sb16-synth",metadata["files"])


if __name__=="__main__":unittest.main()

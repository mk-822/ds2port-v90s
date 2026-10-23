import importlib.util
import io
import json
import os
import struct
from pathlib import Path
import tarfile
import tempfile
import unittest
from ds2port.installer import prepare_payload, render_template, validate_bundle
from ds2port.profiles import digest, game_executable, patch_executable, profiles, detect_game, Win32Image, patch_common
from ds2port.resources import root

spec=importlib.util.spec_from_file_location("remote_installer",root()/"runtime/install_remote.py")
remote=importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)
spec2=importlib.util.spec_from_file_location("prefix_config",root()/"runtime/templates/configure_prefix.py")
prefix_config=importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(prefix_config)


class PrefixConfiguration(unittest.TestCase):
    def test_winebus_dword_values_are_idempotent(self):
        section=r'System\\CurrentControlSet\\Services\\winebus'
        values={'Enable SDL':0,'DisableInput':0,'DisableUdevd':1}
        text='WINE REGISTRY Version 2\n\n['+section+'] 1\n"Enable SDL"=dword:00000001\n"Other"="keep"\n'
        result=prefix_config.merge_section(text,section,values)
        self.assertIn('"Enable SDL"=dword:00000000',result)
        self.assertIn('"DisableUdevd"=dword:00000001',result)
        self.assertIn('"Other"="keep"',result)
        self.assertEqual(result,prefix_config.merge_section(result,section,values))

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
    def test_identical_runtime_tree_can_be_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            source, destination = Path(temp)/'source', Path(temp)/'destination'
            source.mkdir(); destination.mkdir()
            (source/'wine').write_bytes(b'unchanged runtime')
            (destination/'wine').write_bytes(b'unchanged runtime')
            self.assertTrue(remote.same_tree(source, destination))
            (destination/'wine').write_bytes(b'old runtime')
            self.assertFalse(remote.same_tree(source, destination))

    def test_runtime_tree_with_extra_files_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            source, destination = Path(temp)/'source', Path(temp)/'destination'
            source.mkdir(); destination.mkdir()
            (destination/'extra').write_bytes(b'extra')
            self.assertFalse(remote.same_tree(source, destination))

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
    def test_invalid_input_mode_does_not_create_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'payload.tar.gz'
            with self.assertRaises(ValueError):
                prepare_payload(temp,None,profiles()[0],'test',output,input_mode='invalid')
            self.assertFalse(output.exists())

    def common_fixture(self, base=0x600000, callback=0x1020):
        # Synthetic PE with a mouse-hook call, an import table and section padding.
        image = bytearray(0x600)
        image[:2] = b'MZ'
        struct.pack_into('<I', image, 0x3c, 0x80)
        image[0x80:0x84] = b'PE\0\0'
        struct.pack_into('<HH', image, 0x84, 0x14c, 1)
        struct.pack_into('<H', image, 0x94, 224)
        struct.pack_into('<H', image, 0x98, 0x10b)
        struct.pack_into('<I', image, 0x98 + 28, base)
        struct.pack_into('<I', image, 0x98 + 104, 0x1100)
        section = 0x98 + 224
        struct.pack_into('<IIII', image, section + 8, 0x200, 0x1000, 0x400, 0x200)
        struct.pack_into('<I', image, section + 36, 0x60000020)
        struct.pack_into('<IIIII', image, 0x300, 0x1140, 0, 0, 0x1180, 0x1160)
        struct.pack_into('<II', image, 0x340, 0x1190, 0)
        name = b'SetWindowsHookExA\0'
        image[0x392:0x392 + len(name)] = name
        code = b'\x6a\0\x68' + struct.pack('<I', base + callback) + b'\x6a\x07\xff\x15' + struct.pack('<I', base + 0x1160)
        image[0x240:0x240 + len(code)] = code
        return bytes(image)

    def test_common_patch_resolves_non_jump3_addresses(self):
        original = self.common_fixture()
        patched = patch_common(original)
        self.assertEqual(len(original), len(patched))
        self.assertEqual(patched[0x240], 0xe9)
        self.assertEqual(patched[0x400:0x409], bytes.fromhex('64a124000000890424'))
        self.assertEqual(original[0x249:0x24f], patched[0x249:0x24f])
        self.assertEqual(patch_common(patched), patched)

    def test_common_patch_ignores_callback_outside_code(self):
        original = self.common_fixture(callback=0x9000)
        self.assertEqual(patch_common(original), original)

    def test_common_patch_refuses_used_padding(self):
        original = bytearray(self.common_fixture())
        original[0x400] = 1
        with self.assertRaises(ValueError):
            patch_common(bytes(original))

    @unittest.skipUnless(os.environ.get('DS2PORT_TEST_FLOAT'), 'set DS2PORT_TEST_FLOAT to an owned FLOAT folder')
    def test_generic_float_detection_patch_and_payload(self):
        source = Path(os.environ['DS2PORT_TEST_FLOAT'])
        profile = detect_game(source)
        self.assertEqual(profile['id'], 'float')
        self.assertEqual(profile['patch'], 'discstation-common-v1')
        original = (source / profile['executable']).read_bytes()
        patched = patch_executable(original, profile)
        self.assertNotEqual(original, patched)
        self.assertEqual(len(original), len(patched))
        pe = Win32Image(patched)
        self.assertIn('SetWindowsHookExA', pe.imports())
        self.assertIn(bytes.fromhex('64a124000000890424'), patched)
        self.assertIn('SAVE_D0.DAT', profile['preserve'])
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp) / 'payload.tar.gz'
            config = prepare_payload(source, None, profile, 'float-test', payload)
            self.assertEqual(config['input_mode'],'mouse')
            self.assertEqual(config['launcher'], 'FLOAT (float-test).sh')
            with tarfile.open(payload) as tf:
                self.assertEqual(tf.extractfile('game/FLOAT.original.exe').read(), original)
                self.assertEqual(tf.extractfile('game/FLOAT.EXE').read(), patched)
                self.assertNotIn('game/JUMP3.original.exe', tf.getnames())
                self.assertEqual(tf.extractfile('port/input-mode').read(),b'mouse\n')
        self.assertEqual((source / profile['executable']).read_bytes(), original)

    @unittest.skipUnless(os.environ.get('DS2PORT_TEST_FLOAT'), 'set DS2PORT_TEST_FLOAT to an owned FLOAT folder')
    def test_multiple_executables_require_selection(self):
        original = (Path(os.environ['DS2PORT_TEST_FLOAT']) / 'FLOAT.EXE').read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'one.exe').write_bytes(original)
            (folder / 'two.exe').write_bytes(original)
            with self.assertRaises(ValueError):
                detect_game(folder)
            self.assertEqual(detect_game(folder, 'two.exe')['executable'], 'two.exe')

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
            config=prepare_payload(source,None,profile,"jump3-test",payload,input_mode='joypad')
            self.assertEqual(config['input_mode'],'joypad')
            self.assertEqual(config["preserve"],["SaveData"])
            with tarfile.open(payload) as tf:
                self.assertEqual(digest(tf.extractfile("game/JUMP3.EXE").read()),profile["patched_sha256"])
                self.assertEqual(digest(tf.extractfile("game/JUMP3.original.exe").read()),before)
                self.assertEqual(tf.extractfile("port/assets/fonts/msgothic.ttc").read(4),b"ttcf")
                self.assertEqual(tf.extractfile('port/input-mode').read(),b'joypad\n')
            self.assertEqual(digest(exe.read_bytes()),before)

    @unittest.skipUnless((root()/"bld/runtime.tar.gz").exists(),"build the runtime first")
    def test_runtime_bundle_contains_no_game_or_windows_font(self):
        path=root()/"bld/runtime.tar.gz"
        _,metadata=validate_bundle(path)
        forbidden={"jump3.exe","jump3.original.exe","float.exe","float.original.exe","msgothic.ttc"}
        self.assertFalse(any(Path(name).name.casefold() in forbidden for name in metadata["files"]))
        self.assertIn("native/bin/sb16-synth",metadata["files"])


if __name__=="__main__":unittest.main()

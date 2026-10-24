import importlib.util
import io
import json
import os
import struct
from pathlib import Path
import tarfile
import tempfile
import unittest
from ds2port.installer import prepare_payload, render_template, validate_bundle, required_ext4_bytes
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


class RuntimeReuse(unittest.TestCase):
    def test_identical_runtime_tree_can_be_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            source, destination = Path(temp)/'source', Path(temp)/'destination'
            source.mkdir(); destination.mkdir()
            (source/'wine').write_bytes(b'unchanged runtime')
            (destination/'wine').write_bytes(b'unchanged runtime')
            self.assertTrue(remote.same_tree(source, destination))
            (destination/'wine').write_bytes(b'old runtime')
            self.assertFalse(remote.same_tree(source, destination))


class RuntimeSharing(unittest.TestCase):
    def test_identical_wine_files_share_but_atomic_upgrade_is_private(self):
        with tempfile.TemporaryDirectory() as temp:
            old,new=Path(temp)/'old',Path(temp)/'new'
            old.mkdir();new.mkdir()
            (old/'wine').write_bytes(b'same binary')
            (new/'wine').write_bytes(b'same binary')
            self.assertEqual(remote.share_wine_files(new,[old]),1)
            self.assertTrue(os.path.samefile(old/'wine',new/'wine'))
            (new/'update').write_bytes(b'new binary')
            (new/'update').replace(new/'wine')
            self.assertEqual((old/'wine').read_bytes(),b'same binary')
            self.assertEqual((new/'wine').read_bytes(),b'new binary')

    def test_different_contents_or_modes_are_not_shared(self):
        with tempfile.TemporaryDirectory() as temp:
            old,new=Path(temp)/'old',Path(temp)/'new'
            old.mkdir();new.mkdir()
            for root in (old,new):
                (root/'contents').write_bytes(b'old' if root==old else b'new')
                (root/'mode').write_bytes(b'same')
            (old/'mode').chmod(0o444)
            try:
                self.assertEqual(remote.share_wine_files(new,[old]),0)
                self.assertFalse(os.path.samefile(old/'mode',new/'mode'))
                self.assertEqual((new/'contents').read_bytes(),b'new')
            finally:(old/'mode').chmod(0o666)

    @unittest.skipIf(os.name=='nt','symlink creation requires Windows privilege')
    def test_candidate_link_cannot_escape_its_root(self):
        with tempfile.TemporaryDirectory() as temp:
            old,new,outside=(Path(temp)/n for n in ('old','new','outside'))
            for root in (old,new,outside):root.mkdir()
            (new/'sub').mkdir();(new/'sub/file').write_bytes(b'same')
            (outside/'file').write_bytes(b'same')
            (old/'sub').symlink_to(outside,target_is_directory=True)
            self.assertEqual(remote.share_wine_files(new,[old]),0)
            self.assertFalse(os.path.samefile(outside/'file',new/'sub/file'))

    def test_first_run_and_partial_prefix_growth_are_reserved(self):
        mib=1024**2
        base=required_ext4_bytes(700*mib,170*mib,10*mib,640*mib)
        self.assertEqual(required_ext4_bytes(700*mib,170*mib,10*mib),base+640*mib)
        self.assertEqual(required_ext4_bytes(700*mib,170*mib,10*mib,400*mib),base+240*mib)


class ArchiveSafety(unittest.TestCase):
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
        struct.pack_into('<II',image,0x98+32,0x1000,0x200)
        struct.pack_into('<II',image,0x98+56,0x2000,0x200)
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

    def font_fixture(self, creator='CreateFontA'):
        image=bytearray(self.common_fixture())
        struct.pack_into('<IIII',image,0x340,0x1190,0x11b0,0x11d0,0)
        name=creator.encode()+b'\0'
        image[0x3b2:0x3b2+len(name)]=name
        image[0x3d2:0x3e2]=b'GetTextMetricsA\0'
        code=b'\xff\x15'+struct.pack('<I',0x601164)
        code+=b'\x68'+struct.pack('<I',0x601300)+b'\x50\xff\x15'+struct.pack('<I',0x601168)
        code+=b'\x8b\x0d'+struct.pack('<I',0x601300)+b'\x8b\x15'+struct.pack('<I',0x601318)+bytes.fromhex('66 89 56 02')
        image[0x280:0x280+len(code)]=code
        return bytes(image)

    def test_shared_font_initializer_patch_is_specific_and_idempotent(self):
        original=self.font_fixture();patched=patch_common(original)
        pe=Win32Image(patched);imports=pe.imports()
        self.assertEqual(len(pe.sections),2)
        self.assertEqual(patched[0x280:0x286],b'\xff\x15'+struct.pack('<I',imports['DS_CreateFontA']))
        self.assertEqual(patched[0x28c:0x292],b'\xff\x15'+struct.pack('<I',imports['DS_GetTextMetricsA']))
        for name,address in Win32Image(original).imports().items():self.assertEqual(imports[name],address)
        self.assertEqual(patch_common(patched),patched)
        # A different destination field is not the legacy packed-font layout.
        image=bytearray(original);image[0x2a1]=4
        ignored=patch_common(bytes(image))
        self.assertEqual(ignored[0x28c:0x292],bytes(image[0x28c:0x292]))

    def test_indirect_font_creation_uses_the_matching_stdcall_export(self):
        original=self.font_fixture('CreateFontIndirectA');patched=patch_common(original)
        imports=Win32Image(patched).imports()
        self.assertIn('DS_CreateFontIndirectA',imports)
        self.assertNotIn('DS_CreateFontA',imports)
        self.assertEqual(patched[0x280:0x286],b'\xff\x15'+struct.pack('<I',imports['DS_CreateFontIndirectA']))

    def test_font_import_operands_keep_their_base_relocations(self):
        original=bytearray(self.font_fixture())
        struct.pack_into('<II',original,0x98+136,0x11f0,16)
        struct.pack_into('<IIHHHH',original,0x3f0,0x1000,16,0x3043,0x3082,0x308e,0)
        patched=patch_common(bytes(original));pe=Win32Image(patched);rebased=bytearray(patched)
        rva,size=struct.unpack_from('<II',patched,pe.optional+136);pos=pe.offset(rva);end=pos+size
        while pos<end:
            page,block=struct.unpack_from('<II',patched,pos)
            for at in range(pos+8,pos+block,2):
                entry=struct.unpack_from('<H',patched,at)[0]
                if entry>>12==3:
                    target=pe.offset(page+(entry&4095));value=struct.unpack_from('<I',rebased,target)[0]
                    struct.pack_into('<I',rebased,target,value+0x100000)
            pos+=block
        struct.pack_into('<I',rebased,pe.optional+28,pe.base+0x100000)
        imports=Win32Image(bytes(rebased)).imports()
        self.assertEqual(struct.unpack_from('<I',rebased,0x282)[0],imports['DS_CreateFontA'])
        self.assertEqual(struct.unpack_from('<I',rebased,0x28e)[0],imports['DS_GetTextMetricsA'])

    def test_common_patch_ignores_callback_outside_code(self):
        original = self.common_fixture(callback=0x9000)
        self.assertEqual(patch_common(original), original)

    def test_common_patch_adds_section_and_preserves_used_padding_and_overlay(self):
        original = bytearray(self.common_fixture())
        original[0x400] = 1
        original.extend(b'original overlay')
        patched=patch_common(bytes(original));pe=Win32Image(patched)
        self.assertEqual(len(pe.sections),2)
        at,size,va,raw_size,raw,flags=pe.sections[-1]
        self.assertEqual(patched[at:at+8],b'.dsport\0')
        self.assertEqual(patched[0x400:len(original)],original[0x400:])
        self.assertEqual(raw%512,0)
        self.assertEqual(va%4096,0)
        self.assertEqual(flags,0x60000020)
        self.assertEqual(patched[raw:raw+9],bytes.fromhex('64a124000000890424'))
        self.assertEqual(patch_common(patched),patched)

    def test_common_patch_refuses_occupied_section_header(self):
        original=bytearray(self.common_fixture());original[0x400]=1;original[0x1a0]=1
        with self.assertRaises(ValueError):
            patch_common(bytes(original))

    def test_added_section_patches_all_hooks(self):
        original=bytearray(self.common_fixture());original[0x400]=1
        original[0x260:0x26f]=original[0x240:0x24f]
        patched=patch_common(bytes(original));pe=Win32Image(patched)
        for source in (0x240,0x260):
            self.assertEqual(patched[source],0xe9)
            self.assertEqual(patched[source+9:source+15],original[source+9:source+15])
        self.assertEqual(patch_common(patched),patched)

    def test_added_section_relocates_callback_and_keeps_jump_valid(self):
        original=bytearray(self.common_fixture());original[0x400]=1
        struct.pack_into('<II',original,0x98+136,0x11d0,12)
        struct.pack_into('<IIHH',original,0x3d0,0x1000,12,0x3043,0x304b)
        patched=patch_common(bytes(original));pe=Win32Image(patched)
        stub=pe.sections[-1][4];stub_rva=pe.sections[-1][2]
        reloc_rva,reloc_size=struct.unpack_from('<II',patched,pe.optional+136)
        table=pe.offset(reloc_rva)
        self.assertEqual(struct.unpack_from('<H',patched,table+8)[0],0)
        rebased=bytearray(patched);pos=table
        while pos<table+reloc_size:
            page,size=struct.unpack_from('<II',patched,pos)
            for at in range(pos+8,pos+size,2):
                entry=struct.unpack_from('<H',patched,at)[0]
                if entry>>12==3:
                    target=pe.offset(page+(entry&4095))
                    value=struct.unpack_from('<I',rebased,target)[0]
                    struct.pack_into('<I',rebased,target,value+0x100000)
            pos+=size
        self.assertEqual(rebased[0x240:0x249],patched[0x240:0x249])
        self.assertEqual(struct.unpack_from('<I',rebased,stub+12)[0],0x700000+0x1020)
        self.assertEqual(struct.unpack_from('<I',rebased,0x24b)[0],0x700000+0x1160)
        self.assertEqual(0x1040+5+struct.unpack_from('<i',patched,0x241)[0],stub_rva)
        self.assertEqual(stub_rva+23+struct.unpack_from('<i',patched,stub+19)[0],0x1049)

    @unittest.skipUnless(os.environ.get('DS2PORT_TEST_DF3'),'set DS2PORT_TEST_DF3 to an owned DF3 folder')
    def test_owned_df3_adds_section_without_changing_original(self):
        folder=Path(os.environ['DS2PORT_TEST_DF3']);profile=detect_game(folder)
        path=folder/profile['executable'];original=path.read_bytes()
        patched=patch_executable(original,profile)
        before,after=Win32Image(original),Win32Image(patched)
        self.assertNotIn('font_width_percent',profile)
        self.assertIn('savedat1.dat',[name.lower() for name in profile['preserve']])
        self.assertEqual(len(after.sections),len(before.sections)+1)
        self.assertTrue(before.imports().items() <= after.imports().items())
        self.assertIn('DS_CreateFontA',after.imports())
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(patch_common(patched),patched)
        # Explicit CLI profiles must preserve every non-EXE file too.
        explicit=next(item for item in profiles() if item['id']=='df3')
        with tempfile.TemporaryDirectory() as temp:
            payload=Path(temp)/'payload.tar.gz'
            config=prepare_payload(folder,None,explicit,'df3-test',payload)
            self.assertIn('savedat1.dat',[name.lower() for name in config['preserve']])
            with tarfile.open(payload) as tf:
                self.assertEqual(tf.extractfile('game/DF3.exe').read(),patched)
                self.assertEqual(tf.extractfile('game/DF3.original.exe').read(),original)
        # A same-named but different version must retain the 100% default.
        changed=bytearray(original);changed[before.optional+64]^=1
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/profile['executable']).write_bytes(changed)
            other=detect_game(temp)
            self.assertEqual(other.get('font_width_percent',100),100)

    @unittest.skipUnless(os.environ.get('DS2PORT_TEST_FLOAT'), 'set DS2PORT_TEST_FLOAT to an owned FLOAT folder')
    def test_generic_float_detection_patch_and_payload(self):
        source = Path(os.environ['DS2PORT_TEST_FLOAT'])
        profile = detect_game(source)
        self.assertEqual(profile['id'], 'float')
        self.assertEqual(profile['patch'], 'discstation-common-v2')
        self.assertEqual(profile.get('font_width_percent',100),100)
        original = (source / profile['executable']).read_bytes()
        patched = patch_executable(original, profile)
        self.assertNotEqual(original, patched)
        self.assertGreater(len(patched), len(original))
        pe = Win32Image(patched)
        self.assertIn('SetWindowsHookExA', pe.imports())
        from ds2port.profiles import _font_metric_calls
        for call in _font_metric_calls(original,Win32Image(original),pe.imports()):
            create_offset=call[4]
            self.assertEqual(patched[create_offset:create_offset+6],b'\xff\x15'+struct.pack('<I',pe.imports()['DS_CreateFontA']))
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
        profile=detect_game(source)
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
        forbidden={"jump3.exe","jump3.original.exe","float.exe","float.original.exe","ac_mon.exe","ac_mon.original.exe","df3.exe","df3.original.exe", "geo3.exe", "geo3.original.exe", "angler.exe", "angler.original.exe","msgothic.ttc"}
        self.assertFalse(any(Path(name).name.casefold() in forbidden for name in metadata["files"]))
        self.assertIn("native/bin/sb16-synth",metadata["files"])


if __name__=="__main__":unittest.main()

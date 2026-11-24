import hashlib
import json
import struct
import re
from pathlib import Path
from .resources import root


def profiles() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root() / "profiles").glob("*.json"))]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Win32Image:
    """Small PE reader used to find imports and unused executable section padding."""
    def __init__(self, data):
        self.data = data
        try:
            self.pe = struct.unpack_from('<I', data, 0x3c)[0]
            if data[:2] != b'MZ' or data[self.pe:self.pe + 4] != b'PE\0\0':
                raise ValueError()
            if struct.unpack_from('<H', data, self.pe + 4)[0] != 0x14c:
                raise ValueError()
            self.optional = self.pe + 24
            if struct.unpack_from('<H', data, self.optional)[0] != 0x10b:
                raise ValueError()
            self.base = struct.unpack_from('<I', data, self.optional + 28)[0]
            start = self.optional + struct.unpack_from('<H', data, self.pe + 20)[0]
            self.sections = []
            for i in range(struct.unpack_from('<H', data, self.pe + 6)[0]):
                at = start + i * 40
                size, va, raw_size, raw = struct.unpack_from('<IIII', data, at + 8)
                flags = struct.unpack_from('<I', data, at + 36)[0]
                if raw + raw_size > len(data):
                    raise ValueError()
                self.sections.append((at, size, va, raw_size, raw, flags))
            if not self.sections:
                raise ValueError()
        except (ValueError, struct.error):
            raise ValueError('32bit WindowsのPE実行ファイルを指定してください。') from None

    def offset(self, rva):
        for _, _, va, size, raw, _ in self.sections:
            if va <= rva < va + size:
                return raw + rva - va
        raise ValueError('PEの参照先がファイル内にありません。')

    def imports(self):
        result = {}
        directory = struct.unpack_from('<I', self.data, self.optional + 104)[0]
        if not directory:
            return result
        at = self.offset(directory)
        while True:
            lookup, _, _, _, thunk = struct.unpack_from('<IIIII', self.data, at)
            if not thunk:
                return result
            pos = self.offset(lookup or thunk)
            index = 0
            while True:
                entry = struct.unpack_from('<I', self.data, pos + index * 4)[0]
                if not entry:
                    break
                if not entry & 0x80000000:
                    name = self.offset(entry) + 2
                    end = self.data.index(b'\0', name)
                    result[self.data[name:end].decode('ascii')] = self.base + thunk + index * 4
                index += 1
            at += 20


def executables(folder):
    candidates = []
    for path in sorted(Path(folder).iterdir()):
        if path.is_file() and path.suffix.lower() == '.exe' and not path.stem.lower().endswith('.original'):
            try:
                Win32Image(path.read_bytes())
            except ValueError:
                continue
            candidates.append(path)
    return candidates


def detect_game(folder, executable=None):
    folder = Path(folder)
    candidates = executables(folder)
    if executable:
        candidates = [p for p in candidates if p.name.casefold() == executable.casefold()]
    if len(candidates) != 1:
        raise ValueError('ゲームの32bit EXEを選択してください。' if candidates else 'ゲームフォルダーに32bit WindowsのEXEがありません。')
    exe = candidates[0]
    original_hash = digest(exe.read_bytes())
    for profile in profiles():
        if profile['executable'].casefold() == exe.name.casefold() and profile['original_sha256'] == original_hash:
            return profile | {'preserve': profile.get('preserve', [p.name for p in folder.iterdir() if p != exe])}
    ident = re.sub('[^a-z0-9-]+', '-', exe.stem.lower()).strip('-')[:30]
    if not ident or not ident[0].isalpha():
        ident = 'ds-' + original_hash[:12]
    return {'id': ident, 'title': exe.stem, 'launcher': exe.stem,
            'executable': exe.name, 'original_sha256': original_hash,
            'patch': 'discstation-common-v2',
            # Unknown engines may store saves alongside data rather than in a
            # dedicated directory. Keep all existing data on subsequent transfers.
            'preserve': [p.name for p in folder.iterdir() if p != exe],
            'status': '共通ランタイム（タイトル固有の動作は実機で確認してください）'}


def _font_metric_calls(data, pe, imports):
    """Recognize the legacy CreateFont/TextMetric-to-packed-font initializer."""
    metrics=imports.get('GetTextMetricsA')
    creators={name:imports[name] for name in ('CreateFontA','CreateFontIndirectA') if name in imports}
    if not creators or not metrics:return []
    calls=[];needle=b'\xff\x15'+struct.pack('<I',metrics)
    for _,size,va,_,raw,flags in pe.sections:
        if not flags&0x20000000:continue
        section=data[raw:raw+size]
        for match in re.finditer(re.escape(needle),section):
            pos=match.start();before=section[max(0,pos-32):pos];after=section[pos+6:pos+86]
            candidates=[(section.rfind(b'\xff\x15'+struct.pack('<I',address),max(0,pos-256),pos),name,address) for name,address in creators.items()]
            create_pos,create_name,create=max(candidates)
            if create_pos<0:continue
            for push in re.finditer(rb'\x68(.{4})',before,re.DOTALL):
                metric=struct.unpack('<I',push.group(1))[0]
                maximum=rb'(?:\xa1|\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d])'+re.escape(struct.pack('<I',metric+24))
                height=rb'(?:\xa1|\x8b[\x05\x0d\x15\x1d\x25\x2d\x35\x3d])'+re.escape(struct.pack('<I',metric))
                if re.search(maximum,after) and re.search(height,after) and re.search(rb'\x66\x89[\x40-\x7f]\x02',after):
                    calls.append((va+pos,raw+pos,metrics,va+create_pos,raw+create_pos,create,create_name));break
    return calls


def _font_imports(image, pe, va, code, functions):
    """Extend imports while retaining every original descriptor and IAT address."""
    original_rva = struct.unpack_from('<I', image, pe.optional + 104)[0]
    at = pe.offset(original_rva)
    descriptors = bytearray()
    while at + 20 <= len(image):
        row = image[at:at+20]
        if not any(row):
            break
        if not struct.unpack_from('<I', row, 16)[0]:
            raise ValueError('PE import descriptor is invalid')
        descriptors.extend(row)
        at += 20
    else:
        raise ValueError('PE import table has no terminator')
    code.extend(b'\0' * (-len(code) % 4))
    table = len(code)
    code.extend(descriptors + b'\0' * 40)
    slots = (len(functions) + 1) * 4
    lookup = len(code); code.extend(b'\0' * slots)
    iat = len(code); code.extend(b'\0' * slots)
    dll = len(code); code.extend(b'dsfont.dll\0')
    for index, name in enumerate(functions):
        symbol = len(code)
        code.extend(b'\0\0' + name.encode('ascii') + b'\0')
        struct.pack_into('<I', code, lookup + index * 4, va + symbol)
        struct.pack_into('<I', code, iat + index * 4, va + symbol)
    struct.pack_into('<IIIII', code, table + len(descriptors), va + lookup, 0, 0, va + dll, va + iat)
    struct.pack_into('<II', image, pe.optional + 104, va + table, len(descriptors) + 40)
    return {name: pe.base + va + iat + index * 4 for index, name in enumerate(functions)}


def _mouse_section(data, pe, hooks, font_calls=()):
    """Append code without moving existing sections or overwriting their data."""
    section_align,file_align=struct.unpack_from('<II',data,pe.optional+32)
    header_size=struct.unpack_from('<I',data,pe.optional+60)[0]
    header=pe.sections[-1][0]+40
    first_raw=min(s[4] for s in pe.sections if s[3])
    if (not 512<=file_align<=65536 or file_align&(file_align-1)
            or section_align<max(file_align,4096) or section_align&(section_align-1)
            or len(pe.sections)>=96 or header+40>min(first_raw,header_size)
            or any(data[header:header+40])):
        raise ValueError('マウス互換修正用のセクションを安全に追加できません。対象EXEを確認してください。')
    align=lambda n,a:(n+a-1)&~(a-1)
    old_image_size=struct.unpack_from('<I',data,pe.optional+56)[0]
    va=align(max(old_image_size,max(s[2]+max(s[1],s[3]) for s in pe.sections)),section_align)
    raw=align(len(data),file_align)
    image=bytearray(data);code=bytearray();moves={};ranges=[]
    for source,start,original in hooks:
        target=va+len(code)
        stub=bytes.fromhex('64 a1 24 00 00 00 89 04 24')+original
        stub+=b'\xe9'+struct.pack('<i',source+9-(target+len(stub)+5))
        moves[source+3]=target+12  # callback VA moved into the trampoline
        code.extend(stub)
        image[start:start+9]=b'\xe9'+struct.pack('<i',target-source-5)+b'\x90'*4
        ranges.append((source,source+9))
    if font_calls:
        names=tuple(sorted({'DS_'+call[6] for call in font_calls}))+('DS_GetTextMetricsA',)
        shim = _font_imports(image, pe, va, code, names)
        for source,start,metrics,create_source,create_start,create,create_name in font_calls:
            # Keep the six-byte indirect CALL and its original base relocation.
            # Only its IAT operand changes; the DLL preserves stdcall arguments.
            image[create_start:create_start+6] = b'\xff\x15'+struct.pack('<I',shim['DS_'+create_name])
            image[start:start+6] = b'\xff\x15'+struct.pack('<I',shim['DS_GetTextMetricsA'])

    # Preserve every existing relocation, moving only callback operands that
    # used to occupy the instructions replaced by JMP. This also supports rebase.
    reloc_rva,reloc_size=struct.unpack_from('<II',data,pe.optional+136)
    if reloc_rva and reloc_size:
        offset=pe.offset(reloc_rva)
        table=bytearray(data[offset:offset+reloc_size]);pos=0;added={}
        if len(table)!=reloc_size:raise ValueError('PE再配置テーブルがファイル外を参照しています。')
        while pos<len(table):
            if len(table)-pos<8:raise ValueError('PE再配置テーブルが不正です。')
            page,size=struct.unpack_from('<II',table,pos)
            if size<8 or size%4 or pos+size>len(table):raise ValueError('PE再配置ブロックが不正です。')
            at=pos+8
            while at<pos+size:
                entry=struct.unpack_from('<H',table,at)[0];kind=entry>>12;location=page+(entry&4095)
                if kind and any(begin<=location<end for begin,end in ranges):
                    if kind!=3 or location not in moves:raise ValueError('マウス修正箇所に未対応の再配置があります。')
                    target=moves[location];added.setdefault(target&~4095,[]).append(0x3000|(target&4095))
                    struct.pack_into('<H',table,at,0)
                at+=4 if kind==4 else 2  # HIGHADJ owns the next word as data
                if at>pos+size:raise ValueError('PE再配置エントリーが不正です。')
            pos+=size
        if added:
            for page,entries in sorted(added.items()):
                if len(entries)%2:entries.append(0)
                table.extend(struct.pack('<II',page,8+len(entries)*2)+struct.pack('<'+'H'*len(entries),*entries))
            code.extend(b'\0'*(align(len(code),4)-len(code)))
            struct.pack_into('<II',image,pe.optional+136,va+len(code),len(table))
            code.extend(table)
    virtual_size=len(code);raw_size=align(virtual_size,file_align)
    image.extend(b'\0'*(raw-len(image)));image.extend(code);image.extend(b'\0'*(raw_size-virtual_size))
    struct.pack_into('<8sIIIIIIHHI',image,header,b'.dsport\0',virtual_size,va,raw_size,raw,0,0,0,0,0xe0000020 if font_calls else 0x60000020)
    struct.pack_into('<H',image,pe.pe+6,len(pe.sections)+1)
    struct.pack_into('<I',image,pe.optional+4,struct.unpack_from('<I',data,pe.optional+4)[0]+raw_size)
    struct.pack_into('<I',image,pe.optional+56,align(va+virtual_size,section_align))
    struct.pack_into('<I',image,pe.optional+64,0)
    return bytes(image)


def patch_common(data):
    pe = Win32Image(data)
    imports=pe.imports();font_calls=_font_metric_calls(data,pe,imports)
    hook_import = imports.get('SetWindowsHookExA')
    if not hook_import:
        return _mouse_section(data,pe,[],font_calls) if font_calls else data
    image = bytearray(data)
    # Match the complete hMod=NULL, callback, WH_MOUSE, imported call sequence.
    # Keep the caller's existing thread-ID stack slot and replace its value.
    signature = rb'\x6a\x00\x68(.{4})\x6a\x07\xff\x15' + re.escape(struct.pack('<I', hook_import))
    hooks=[]
    for _,size,va,_,raw,flags in pe.sections:
        if not flags&0x20000000:continue
        for match in re.finditer(signature,data[raw:raw+size],re.DOTALL):
            callback=struct.unpack('<I',match.group(1))[0]
            if any(pe.base+s[2]<=callback<pe.base+s[2]+s[1] and s[5]&0x20000000 for s in pe.sections):
                hooks.append((va+match.start(),raw+match.start(),match.group(0)[:9]))
    if font_calls:return _mouse_section(data,pe,hooks,font_calls)
    if not hooks:return data
    for at, size, va, raw_size, raw, flags in pe.sections:
        if not flags & 0x20000000:
            continue
        matches = list(re.finditer(signature, data[raw:raw + size], re.DOTALL))
        if not matches:
            continue
        cursor = (size + 15) & ~15
        applied = False
        for match in matches:
            callback = struct.unpack('<I', match.group(1))[0]
            if not any(pe.base + s[2] <= callback < pe.base + s[2] + s[1] and s[5] & 0x20000000 for s in pe.sections):
                continue
            source = pe.base + va + match.start()
            target = pe.base + va + cursor
            code = bytes.fromhex('64 a1 24 00 00 00 89 04 24') + match.group(0)[:9]
            code += b'\xe9' + struct.pack('<i', source + 9 - (target + len(code) + 5))
            if cursor + len(code) > raw_size or any(image[raw + cursor:raw + cursor + len(code)]):
                return _mouse_section(data,pe,hooks)
            image[raw + cursor:raw + cursor + len(code)] = code
            start = raw + match.start()
            image[start:start + 9] = b'\xe9' + struct.pack('<i', target - source - 5) + b'\x90' * 4
            cursor += len(code)
            applied = True
        if applied:
            struct.pack_into('<I', image, at + 8, max(size, cursor))
    return bytes(image)


def game_executable(folder: Path, profile: dict) -> Path:
    for path in folder.iterdir():
        if path.is_file() and path.name.casefold() == profile["executable"].casefold():
            return path
    raise ValueError(f"{profile['executable']} がありません。ゲームのフォルダーを指定してください。")


def _patch_checked(data, changes):
    image = bytearray(data)
    for offset, before, after in changes:
        if data[offset:offset + len(before)] != before:
            raise ValueError(f'互換修正箇所が一致しません（0x{offset:x}）。')
        image[offset:offset + len(before)] = after
    return bytes(image)


def _cj16_borderless(data):
    # cnc-ddraw supplies the original 16-bit fullscreen surfaces inside a
    # borderless X11 window. Fit the square playfield to its full height.
    changes = [(0x7951c, b'\x6a\x00', b'\xeb\x18')]
    # Rect(95, 15, 545, 465) and Rect(170, 90, 470, 390) in the final blit.
    for offset, opcode, old, new in (
        (0x73737, 0x68, 465, 480), (0x73741, 0xb9, 545, 560),
        (0x73746, 0xba, 15, 0), (0x7374b, 0xb8, 95, 80),
        (0x73770, 0x68, 390, 480), (0x7377d, 0xb9, 470, 560),
        (0x73782, 0xba, 90, 0), (0x73787, 0xb8, 170, 80),
    ):
        changes.append((offset, struct.pack('<BI', opcode, old), struct.pack('<BI', opcode, new)))
    return _patch_checked(data, changes)


def _latest_timer(data):
    # The DirectDraw sync setter must report success at startup even though
    # the GDI wrapper cannot provide the vblank the game expects.
    return _patch_checked(data, (
        (0xc077, bytes.fromhex('81 e1 ff 00 00 00'), bytes.fromhex('31 c9 90 90 90 90')),
        # Keep the 18.125 ms deadline, but prevent a late frame from being
        # followed by a catch-up frame after only 9.0625 ms.
        (0x4700e, bytes.fromhex('8d b0 91 00 00 00'), bytes.fromhex('8d b0 20 01 00 00')),
    ))


def display_profile(profile, mode):
    if mode == 'auto':
        return profile
    if mode not in ('16bit', 'windowed'):
        raise ValueError('描画モードはauto、16bit、windowedを指定してください。')
    if not profile.get('windowed_sha256'):
        raise ValueError('16ビットと標準ウィンドウの切り替えは対応版のCJ16で使用できます。')
    if mode == '16bit':
        return profile
    return profile | {
        'patch': 'cj16-windowed', 'patched_sha256': profile['windowed_sha256'],
        'cnc_ddraw': False, 'builtin_ddraw': True, 'status': '標準ウィンドウ描画を適用',
    }


def patch_executable(data: bytes, profile: dict) -> bytes:
    if digest(data) != profile["original_sha256"]:
        raise ValueError("対応する原本EXEとSHA-256が一致しません。未変更のゲームフォルダーを指定してください。")
    patch = profile['patch']
    if patch == 'cj16-borderless':
        data = _cj16_borderless(data)
    elif patch == 'cj16-windowed':
        data = _patch_checked(data, ((0x7951c, b'\x6a\x00', b'\xeb\x61'),))
    elif patch == 'latest-timer':
        data = _latest_timer(data)
    elif patch not in ('discstation-common-v1', 'discstation-common-v2'):
        raise ValueError("未対応の互換修正です。")
    result = patch_common(data)
    if profile.get('patched_sha256') and digest(result) != profile['patched_sha256']:
        raise ValueError('修正後EXEの検証に失敗しました。')
    return result


X68SOUND_ORIGINAL = 'fc5744e4f21ee6e050418bc3dae8594953ae23eadea812675b0dd668092b0f48'


def patch_x68sound(data: bytes) -> bytes:
    if digest(data) != X68SOUND_ORIGINAL:
        return data
    # X68Sound_GetPcm writes the destination into a shared variable and
    # clears it before returning. A concurrent call can leave the synthesis
    # loop writing to NULL. Use that same variable to acquire ownership.
    entry = 0x348f
    stub = 0x13910
    # mov edx,[esp+4]; test edx,edx; jz done; call next; pop ecx; xor eax,eax
    code = bytes.fromhex('8b 54 24 04 85 d2 74 17 e8 00 00 00 00 59 31 c0')
    # lock cmpxchg [ecx + (pcm_destination - next)],edx; jne done
    code += bytes.fromhex('f0 0f b1 91') + struct.pack('<i', 0x57fb8 - (stub + 13))
    # Jump to the original renderer. Both original return paths clear ownership.
    code += bytes.fromhex('75 05 e9') + struct.pack('<i', 0x3498 - (stub + 31))
    code += bytes.fromhex('31 c0 c3')  # done: xor eax,eax; ret
    if data[entry:entry + 5] != bytes.fromhex('8b 44 24 04 a3') or any(data[stub:stub + len(code)]):
        raise ValueError('X68Sound.dllのPCM互換修正箇所が一致しません。')
    image = bytearray(data)
    image[entry:entry + 5] = b'\xe9' + struct.pack('<i', stub - (entry + 5))
    image[stub:stub + len(code)] = code
    return bytes(image)

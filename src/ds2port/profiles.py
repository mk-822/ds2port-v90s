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
            return profile
    ident = re.sub('[^a-z0-9-]+', '-', exe.stem.lower()).strip('-')[:30]
    if not ident or not ident[0].isalpha():
        ident = 'ds-' + original_hash[:12]
    return {'id': ident, 'title': exe.stem, 'launcher': exe.stem,
            'executable': exe.name, 'original_sha256': original_hash,
            'patch': 'discstation-common-v1',
            # Unknown engines may store saves alongside data rather than in a
            # dedicated directory. Keep all existing data on subsequent transfers.
            'preserve': [p.name for p in folder.iterdir() if p != exe],
            'status': '共通ランタイム（タイトル固有の動作は実機で確認してください）'}


def patch_common(data):
    pe = Win32Image(data)
    hook_import = pe.imports().get('SetWindowsHookExA')
    if not hook_import:
        return data
    image = bytearray(data)
    # Match the complete hMod=NULL, callback, WH_MOUSE, imported call sequence.
    # Keep the caller's existing thread-ID stack slot and replace its value.
    signature = rb'\x6a\x00\x68(.{4})\x6a\x07\xff\x15' + re.escape(struct.pack('<I', hook_import))
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
                raise ValueError('マウス互換修正用の空き領域がありません。')
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


def patch_executable(data: bytes, profile: dict) -> bytes:
    if digest(data) != profile["original_sha256"]:
        raise ValueError("対応する原本EXEとSHA-256が一致しません。未変更のゲームフォルダーを指定してください。")
    if profile['patch'] == 'discstation-common-v1':
        return patch_common(data)
    if profile["patch"] != "jump3-ms-gothic-thread-mouse-v1":
        raise ValueError("未対応の互換修正です。")
    image = bytearray(data)
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    section_base = pe + 24 + struct.unpack_from("<H", image, pe + 20)[0]
    sections = [section_base + i * 40 for i in range(struct.unpack_from("<H", image, pe + 6)[0])]

    def offset(va):
        for section in sections:
            _, start, raw_size, raw = struct.unpack_from("<IIII", image, section + 8)
            if start <= va - 0x400000 < start + raw_size:
                return raw + va - 0x400000 - start
        raise ValueError("EXEのセクションが想定と異なります。")

    def replace(va, before, after):
        at = offset(va)
        if len(before) != len(after) or image[at:at + len(before)] != before:
            raise ValueError("互換修正箇所が想定と異なります。")
        image[at:at + len(before)] = after

    def jump(source, target):
        return b"\xe9" + struct.pack("<i", target - source - 5)

    text = sections[0]
    old_size = struct.unpack_from("<I", image, text + 8)[0]
    cave = 0x401000 + ((old_size + 15) & ~15)
    metrics = bytes.fromhex("a1 34 03 5d 00 01 c0")
    metrics += jump(cave + len(metrics), 0x4079D6)
    hook_at = cave + 32
    hook = bytes.fromhex("64 a1 24 00 00 00 50 6a 00 68 89 dc 40 00 6a 07")
    hook += jump(hook_at + len(hook), 0x40CB19)
    replace(0x4079D1, bytes.fromhex("a138035d00"), jump(0x4079D1, cave))
    replace(0x561878, bytes.fromhex("eafff8ff"), struct.pack("<hh", -22, 7))
    replace(0x40CB0E, bytes.fromhex("6a006a006889dc40006a07"), jump(0x40CB0E, hook_at) + b"\x90" * 6)
    for va, code in ((cave, metrics), (hook_at, hook)):
        at = offset(va)
        if any(image[at:at + len(code)]):
            raise ValueError("コード追加領域が使用されています。")
        image[at:at + len(code)] = code
    struct.pack_into("<I", image, text + 8, hook_at - 0x401000 + len(hook))
    result = bytes(image)
    if digest(result) != profile["patched_sha256"]:
        raise ValueError("修正後EXEの検証に失敗しました。")
    return result

import hashlib
import json
import struct
from pathlib import Path
from .resources import root


def profiles() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root() / "profiles").glob("*.json"))]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def game_executable(folder: Path, profile: dict) -> Path:
    for path in folder.iterdir():
        if path.is_file() and path.name.casefold() == profile["executable"].casefold():
            return path
    raise ValueError(f"{profile['executable']} がありません。ゲームのフォルダーを指定してください。")


def patch_executable(data: bytes, profile: dict) -> bytes:
    if digest(data) != profile["original_sha256"]:
        raise ValueError("対応する原本EXEとSHA-256が一致しません。未変更のゲームフォルダーを指定してください。")
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

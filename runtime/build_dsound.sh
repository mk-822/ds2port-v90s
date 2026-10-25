#!/bin/sh
set -eu
cd /work
build=$(mktemp -d /tmp/ds2port-dsound.XXXXXX)
trap 'rm -rf "$build"' EXIT
tar xf bld/cache/wine-10.0-source.tar.gz -C "$build"
source="$build/wine-wine-10.0"
(cd "$source" && patch --batch -p1 < /work/runtime/patches/wine10-dsound-optimized.patch)
mkdir "$build/build"
cd "$build/build"
# These are the PE compiler's flags, not the Unix build-tool CFLAGS.
i386_CFLAGS='-O3 -msse2 -mfpmath=sse' "$source/configure" \
 --enable-win64 --enable-archs=i386,x86_64 --disable-tests \
 --without-x --without-wayland --without-freetype
make -j4 dlls/dsound/i386-windows/dsound.dll
i686-w64-mingw32-strip --strip-debug dlls/dsound/i386-windows/dsound.dll
mkdir -p /work/bld/win32/dsound-licenses
cp dlls/dsound/i386-windows/dsound.dll /work/bld/win32/dsound.dll.building
cp "$source/COPYING.LIB" /work/bld/win32/dsound-licenses/COPYING.LIB
# The builtin marker makes Wine silently substitute its original DLL even with
# a native override. Identify this standalone PE module as an external module.
python3 - <<'PY'
from pathlib import Path
p=Path('/work/bld/win32/dsound.dll.building')
data=bytearray(p.read_bytes())
assert data[64:80]==b'Wine builtin DLL'
data[64:80]=b'DS2Port Wine DLL'
p.write_bytes(data)
p.replace(p.with_name('dsound.dll'))
PY

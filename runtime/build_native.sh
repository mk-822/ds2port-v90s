#!/bin/sh
set -eu
cd /work
python3 scripts/fetch_dependencies.py
test -f bld/cache/wine10.tar || { echo 'Run scripts/prepare_cache.py on the host first'; exit 1; }
build=$(mktemp -d /tmp/ds2port-build.XXXXXX)
trap 'rm -rf "$build"' EXIT
tree="$build/tree"
native="$tree/native"
adlsrc=/work/bld/vendor/libADLMIDI-1.5.1
adllib=/work/bld/adl-build/libADLMIDI.a
mkdir -p "$native/bin" "$native/lib" "$native/tests" "$native/share/X11" "$tree/shared/runtime/x64lib" "$tree/shared/assets" "$tree/licenses/sources" "$adlsrc"
tar xzf bld/cache/adlmidi-source.tar.gz -C "$adlsrc" --strip-components=1
cmake -S "$adlsrc" -B /work/bld/adl-build -DCMAKE_BUILD_TYPE=Release -DWITH_MIDI_SEQUENCER=OFF -DUSE_NUKED_EMULATOR=OFF -DUSE_OPAL_EMULATOR=OFF -DUSE_JAVA_EMULATOR=OFF -DUSE_DOSBOX_EMULATOR=ON -DlibADLMIDI_STATIC=ON -DlibADLMIDI_SHARED=OFF
cmake --build /work/bld/adl-build -j4
gcc -O2 runtime/native/fbbridge.c -o "$native/bin/fbbridge" -lX11 -lXext -ldl
gcc -O2 -Iruntime/native tests/input-mode.c -o "$build/input-mode-test"
"$build/input-mode-test"
gcc -O2 runtime/native/xctl.c -o "$native/bin/xctl" -lX11 -ldl
gcc -O2 runtime/native/midisynth.c -o "$native/bin/midisynth" -ldl
gcc -shared -fPIC -DPIC -O2 runtime/native/pcm_jump3_volume.c -o "$native/lib/libasound_module_pcm_jump3_volume.so" -lasound
gcc -shared -fPIC -DPIC -O3 runtime/native/pcm_ds2port_mix.c -o "$native/lib/libasound_module_pcm_ds2port_mix.so" -lasound
gcc -O3 runtime/native/audio-mixer.c -o "$native/bin/audio-mixer" -lasound -lpthread
gcc -O2 tests/audio-mixer-client.c -o "$build/audio-mixer-client" -lasound -lpthread
DS2PORT_MIXER_TEST_BIN="$native/bin/audio-mixer" DS2PORT_MIXER_TEST_PLUGIN="$native/lib/libasound_module_pcm_ds2port_mix.so" DS2PORT_MIXER_TEST_CLIENT="$build/audio-mixer-client" python3 -m unittest discover -s tests -p test_audio_mixer.py
g++ -O2 -static-libstdc++ -static-libgcc -I"$adlsrc/include" runtime/native/sb16-synth.cpp "$adllib" -o "$native/bin/sb16-synth" -lasound -lm -lpthread
g++ -O2 -static-libstdc++ -static-libgcc -Iruntime/native -I"$adlsrc/include" tests/midi-reset-test.cpp "$adllib" -o "$build/midi-reset-test" -lasound -lm -lpthread
"$build/midi-reset-test"
"$native/bin/sb16-synth" --selftest "$build/opl3.s16"
i686-w64-mingw32-gcc -Os -static tests/probes/probe.c -o "$native/tests/console32.exe"
i686-w64-mingw32-gcc -Os -static -DGUI tests/probes/probe.c -o "$native/tests/gdi32.exe" -lgdi32 -luser32
i686-w64-mingw32-gcc -Os -static tests/probes/ddraw32.c -o "$native/tests/ddraw32.exe" -lddraw -ldxguid -luser32
i686-w64-mingw32-gcc -Os -static tests/probes/midi32.c -o "$native/tests/midi32.exe" -lwinmm
x86_64-linux-gnu-gcc -Os tests/probes/linux_probe.c -o "$native/tests/linux-probe"
strip "$native/bin/fbbridge" "$native/bin/xctl" "$native/bin/midisynth" "$native/bin/sb16-synth" "$native/lib/libasound_module_pcm_jump3_volume.so"
strip "$native/bin/audio-mixer" "$native/lib/libasound_module_pcm_ds2port_mix.so"
cp /usr/bin/Xvfb /usr/bin/xkbcomp /usr/bin/xwininfo "$native/bin/"
cp -L /usr/lib/aarch64-linux-gnu/libXtst.so.6 "$native/lib/"
cp -L /usr/lib/aarch64-linux-gnu/libX*.so.* "$native/lib/"
cp -r /usr/share/X11/xkb "$native/share/X11/"
python3 - "$tree" <<'PY'
from pathlib import Path
import subprocess,shutil,sys
root=Path(sys.argv[1]);native=root/'native'
p=native/'bin/Xvfb';p.write_bytes(p.read_bytes().replace(b'/usr/bin',b'/tmp/j3b'))
queue=list((native/'bin').iterdir())+list((native/'lib').iterdir());seen=set()
while queue:
 p=queue.pop()
 for line in subprocess.check_output(['ldd',str(p)],text=True).splitlines():
  if '=> /' not in line:continue
  src=line.split('=> ')[1].split()[0];name=Path(src).name
  if name in seen or name in ('libc.so.6','libm.so.6','libpthread.so.0','libdl.so.2','librt.so.1'):continue
  seen.add(name);dest=native/'lib'/name;shutil.copyfile(src,dest);queue.append(dest)
PY
dpkg-deb -x bld/cache/box64.deb "$build/box64"
cp "$build/box64/usr/local/bin/box64" "$tree/shared/runtime/box64"
cp "$build/box64/usr/doc/box64-generic-arm/LICENSE" "$tree/licenses/Box64-LICENSE"
cp -L /usr/x86_64-linux-gnu/lib/libgcc_s.so.1 "$tree/shared/runtime/x64lib/"
cp /usr/share/sounds/sf2/TimGM6mb.sf2 "$tree/shared/assets/"
tar xf bld/cache/wine10.tar -C "$tree"
cp bld/cache/adlmidi-source.tar.gz "$tree/licenses/sources/"
cp "$adlsrc/"LICENSE* "$tree/licenses/"
cp /usr/share/common-licenses/GPL-3 "$tree/licenses/GPL-3.txt"
cp /usr/share/common-licenses/LGPL-2.1 "$tree/licenses/LGPL-2.1.txt"
cp /usr/share/common-licenses/LGPL-3 "$tree/licenses/LGPL-3.txt"
mkdir -p "$tree/licenses/debian"
for package in $(dpkg-query -W -f='${binary:Package}\n'); do
 if [ -f "/usr/share/doc/$package/copyright" ]; then cp -L "/usr/share/doc/$package/copyright" "$tree/licenses/debian/$package.txt"; fi
done
dpkg-query -W -f='${binary:Package}\t${Version}\n' > "$tree/licenses/debian-packages.tsv"
cp runtime/dependencies.json "$tree/licenses/dependencies.json"
tar cf /work/bld/runtime-tree.tar -C "$tree" .
echo NATIVE_TREE_READY

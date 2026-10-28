"""Generate private client/output configurations without changing system ALSA."""
import os
from pathlib import Path
import re
import sys
import tempfile


def render_route(runtime, hotplug):
    if not hotplug:
        return '''# Legacy firmware without the PlumOS hotplug plugin.
pcm.jump3_dmix {
 type dmix ipc_key 486931 ipc_perm 0600
 slave { pcm "hw:0,0" rate 48000 format S16_LE channels 2 period_size 1024 buffer_size 4096 }
}
pcm_type.jump3_volume { lib "%s/native/lib/libasound_module_pcm_jump3_volume.so" }
pcm.jump3_volume { type jump3_volume slave.pcm "jump3_dmix" }
''' % runtime
    text = '''# PCM and FM share one output process; only that process opens the DAC.
pcm_type.ds2port_mix { lib "%s/native/lib/libasound_module_pcm_ds2port_mix.so" }
pcm.ds2port_client { type ds2port_mix socket "%s/audio.sock" }
pcm.jump3_volume { type plug slave.pcm "ds2port_client" }
''' % (runtime, runtime)
    # Wine can retain a physical endpoint instead of opening ALSA default.
    # The mixer's separate config keeps its own hw opens outside these aliases.
    for name in ('hw', 'plughw'):
        text += '''pcm.!%s {
 @args [ CARD DEV SUBDEV ]
 @args.CARD { type integer default 0 }
 @args.DEV { type integer default 0 }
 @args.SUBDEV { type integer default -1 }
 type asym
 playback.pcm "jump3_pcm_playback"
 capture.pcm { type plug slave.pcm { type hw card $CARD device $DEV subdevice $SUBDEV } }
}
''' % name
    return text


def write_changed(target, content):
    if target.is_symlink():
        raise ValueError('Audio configuration must not be a symbolic link')
    if target.exists() and target.read_text() == content:
        return
    with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, prefix='.audio-', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        temporary.chmod(0o644)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def configure(runtime, hotplug=None):
    directory = runtime / 'port'
    if runtime.is_symlink() or directory.is_symlink():
        raise ValueError('Audio configuration must not be a symbolic link')
    if hotplug is None:
        plugins = Path(os.environ.get('ALSA_PLUGIN_DIR', '/mnt/plumos/lib/alsa-lib'))
        hotplug = (plugins / 'libasound_module_pcm_plumos_hotplug.so').is_file()
    target = directory / 'audio-route.conf'
    write_changed(target, render_route(runtime, hotplug))
    if hotplug:
        write_changed(directory / 'asound-output.conf', '''</usr/share/alsa/alsa.conf>
pcm.ds2port_output { type plumos_hotplug }
''')
    write_changed(directory / 'audio-output-mode', 'shared-mixer\n' if hotplug else 'legacy\n')
    print('AUDIO_OUTPUT=' + ('plumos-shared-mixer' if hotplug else 'legacy-internal'), flush=True)
    return target


if __name__ == '__main__':
    runtime = Path(sys.argv[1])
    if runtime.parent != Path('/mnt/plumos/ports-runtime') or not re.fullmatch('[a-z][a-z0-9-]{0,39}', runtime.name):
        raise ValueError('Invalid game runtime')
    configure(runtime)

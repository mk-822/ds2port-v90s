import os
import importlib.util
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from ds2port.installer import render_template
from ds2port.resources import root

spec = importlib.util.spec_from_file_location('audio_router', root() / 'runtime/templates/configure_audio.py')
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class AudioRouter(unittest.TestCase):
    def test_hotplug_shares_each_card_and_uses_system_volume_once(self):
        text = router.render_route('/mnt/plumos/ports-runtime/example', True)
        self.assertIn('type ds2port_mix socket "/mnt/plumos/ports-runtime/example/audio.sock"', text)
        self.assertIn('/native/lib/libasound_module_pcm_ds2port_mix.so', text)
        self.assertIn('type hw card $CARD device $DEV subdevice $SUBDEV', text)
        self.assertNotIn('type dmix', text)
        self.assertNotIn('type plumos_hotplug', text)
        self.assertNotIn('type jump3_volume', text)
        self.assertNotIn('slave { pcm "ds2port_router"', text)
        self.assertIn('pcm.!plughw', text)
        self.assertIn('playback.pcm "jump3_pcm_playback"', text)
        self.assertIn('pcm.!hw', text)
        self.assertNotIn('timer.!hw', text)

    def test_legacy_firmware_keeps_internal_mixer_and_volume_filter(self):
        text = router.render_route('/mnt/plumos/ports-runtime/example', False)
        self.assertIn('pcm "hw:0,0" rate 48000', text)
        self.assertIn('/example/native/lib/libasound_module_pcm_jump3_volume.so', text)
        self.assertIn('type jump3_volume', text)
        self.assertNotIn('pcm.!hw', text)
        self.assertNotIn('timer.!hw', text)

    def test_unchanged_configuration_does_not_rewrite_the_file(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            (runtime / 'port').mkdir()
            target = router.configure(runtime, hotplug=True)
            output = runtime / 'port/asound-output.conf'
            self.assertIn('type plumos_hotplug', output.read_text())
            self.assertNotIn('pcm.!hw', output.read_text())
            self.assertEqual((runtime / 'port/audio-output-mode').read_text(), 'shared-mixer\n')
            before = target.stat().st_mtime_ns
            router.configure(runtime, hotplug=True)
            self.assertEqual(target.stat().st_mtime_ns, before)
            router.configure(runtime, hotplug=False)
            self.assertIn('Legacy firmware', target.read_text())
            self.assertEqual((runtime / 'port/audio-output-mode').read_text(), 'legacy\n')


@unittest.skipUnless(os.name == 'posix', 'shell environment test requires POSIX')
class SharedAudioBackend(unittest.TestCase):
    def test_common_switch_selects_optimized_or_builtin_for_any_title(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            runtime = base / 'any-game'
            module = runtime / 'port/runtime/dsound.dll'
            module.parent.mkdir(parents=True)
            common = base / 'common'
            common.mkdir()
            env = base / 'env.sh'
            text = render_template('env.sh.in', {'PORT': '/unused', 'RUNTIME': str(runtime)}).decode()
            text = text.replace('S=/mnt/plumos/ports-runtime/.shared/wine10', 'S=' + shlex.quote(str(common)))
            env.write_text(text)

            def backend():
                return subprocess.check_output(['sh', '-c', '. "$1"; printf "%s" "$WINEDLLOVERRIDES"',
                                                'audio-test', str(env)], text=True)

            self.assertTrue(backend().startswith('dsound=b;'))
            module.write_bytes(b'test module')
            self.assertTrue(backend().startswith('dsound=n,b;'))
            (common / 'audio-backend').write_text('builtin\n')
            self.assertTrue(backend().startswith('dsound=b;'))
            (common / 'audio-backend').write_text('optimized\n')
            self.assertTrue(backend().startswith('dsound=n,b;'))

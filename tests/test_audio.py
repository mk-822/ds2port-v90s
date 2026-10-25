import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from ds2port.installer import render_template


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

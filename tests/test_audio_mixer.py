"""Native integration checks, enabled by runtime/build_native.sh."""
import array
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless(os.name == 'posix' and os.environ.get('DS2PORT_MIXER_TEST_BIN'), 'requires native mixer build')
class AudioMixerIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.socket = self.base / 'audio.sock'
        self.wave = self.base / 'output.s16'
        output = self.base / 'output.conf'
        output.write_text('</usr/share/alsa/alsa.conf>\npcm.testoutput { type file slave.pcm "null" file "%s" format "raw" }\n' % self.wave)
        client = self.base / 'client.conf'
        client.write_text('</usr/share/alsa/alsa.conf>\npcm_type.ds2port_mix { lib "%s" }\npcm.testmix { type ds2port_mix socket "%s" }\npcm.testclient { type plug slave.pcm "testmix" }\n' % (os.environ['DS2PORT_MIXER_TEST_PLUGIN'], self.socket))
        self.client_env = dict(os.environ, ALSA_CONFIG_PATH=str(client))
        self.log = (self.base / 'server.log').open('w')
        self.addCleanup(self.log.close)
        self.server = subprocess.Popen([os.environ['DS2PORT_MIXER_TEST_BIN'], str(self.socket), 'testoutput'],
                                       env=dict(os.environ, ALSA_CONFIG_PATH=str(output)), stdout=self.log, stderr=self.log)
        self.addCleanup(self.stop_server)
        for _ in range(200):
            if self.socket.exists():
                break
            self.assertIsNone(self.server.poll(), (self.base / 'server.log').read_text())
            time.sleep(.01)
        self.assertTrue(self.socket.exists())

    def stop_server(self):
        if self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.wait(timeout=2)
                self.fail('Mixer did not stop')

    def test_rw_and_mmap_mix_clip_and_close(self):
        result = subprocess.run([os.environ['DS2PORT_MIXER_TEST_CLIENT']], env=self.client_env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('MIXED_RW_MMAP_CLIENTS_OK', result.stdout)
        self.stop_server()
        self.assertEqual(self.server.returncode, 0, (self.base / 'server.log').read_text())
        samples = array.array('h')
        samples.frombytes(self.wave.read_bytes())
        self.assertIn(32767, samples, 'Two 20000-amplitude streams must mix and saturate')
        self.assertNotIn(-25536, samples, 'Mixing must not wrap signed 16-bit samples')
        self.assertFalse(self.socket.exists())

    def test_server_loss_does_not_leave_clients_waiting(self):
        client = subprocess.Popen([os.environ['DS2PORT_MIXER_TEST_CLIENT'], '1000'], env=self.client_env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(lambda: client.kill() if client.poll() is None else None)
        time.sleep(.3)
        self.server.kill()
        self.server.wait(timeout=3)
        output, _ = client.communicate(timeout=5)
        self.assertNotEqual(client.returncode, 0, output)
        self.assertIn('CLIENT_WRITE', output)

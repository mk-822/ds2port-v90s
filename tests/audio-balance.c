#include <alsa/asoundlib.h>
#include <stdint.h>
#include <stdio.h>
int main(void) {
    snd_pcm_t *pcm = NULL;
    int rc = snd_pcm_open(&pcm, "default", SND_PCM_STREAM_PLAYBACK, 0);
    if (rc < 0) { fprintf(stderr, "%s\n", snd_strerror(rc)); return 1; }
    rc = snd_pcm_set_params(pcm, SND_PCM_FORMAT_S16_LE, SND_PCM_ACCESS_RW_INTERLEAVED,
                            2, 48000, 1, 20000);
    if (rc < 0) return 2;
    int16_t data[2048];
    for (unsigned i = 0; i < 1024; i++) { data[i*2] = 10000; data[i*2+1] = -10000; }
    snd_pcm_sframes_t count = snd_pcm_writei(pcm, data, 1024);
    if (count != 1024) return 3;
    snd_pcm_drain(pcm); snd_pcm_close(pcm);
    return 0;
}

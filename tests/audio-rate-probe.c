#define _POSIX_C_SOURCE 200809L
#include <alsa/asoundlib.h>
#include <stdio.h>
#include <time.h>
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static int write_block(snd_pcm_t*pcm,short*silence){
 int offset=0;
 while(offset<512){snd_pcm_sframes_t n=snd_pcm_writei(pcm,silence+offset*2,512-offset);if(n<0){fprintf(stderr,"write: %s\n",snd_strerror(n));return -1;}offset+=n;}
 return 0;
}
int main(void){
 snd_pcm_t*pcm;int rc=snd_pcm_open(&pcm,"default",SND_PCM_STREAM_PLAYBACK,0);if(rc<0)return 1;
 rc=snd_pcm_set_params(pcm,SND_PCM_FORMAT_S16_LE,SND_PCM_ACCESS_RW_INTERLEAVED,2,44100,1,40000);if(rc<0){fprintf(stderr,"setup: %s\n",snd_strerror(rc));return 2;}
 snd_pcm_hw_params_t*params;snd_pcm_hw_params_alloca(&params);snd_pcm_hw_params_current(pcm,params);
 unsigned rate=0;int direction=0;snd_pcm_hw_params_get_rate(params,&rate,&direction);
 snd_output_t*out;snd_output_stdio_attach(&out,stdout,0);snd_pcm_dump(pcm,out);
 short silence[1024]={0};for(int i=0;i<173;i++)if(write_block(pcm,silence))return 3;
 snd_pcm_sframes_t before=0,after=0;snd_pcm_delay(pcm,&before);double start=now();
 for(int i=0;i<900;i++)if(write_block(pcm,silence))return 4;
 snd_pcm_delay(pcm,&after);double elapsed=now()-start;
 long frames=900*512-(after-before);
 printf("AUDIO_RATE_PROBE negotiated_rate=%u consumed_frames=%ld elapsed=%.6f measured_rate=%.3f delay_start=%ld delay_end=%ld\n",rate,frames,elapsed,frames/elapsed,(long)before,(long)after);
 snd_pcm_drop(pcm);snd_pcm_close(pcm);snd_output_close(out);return 0;
}

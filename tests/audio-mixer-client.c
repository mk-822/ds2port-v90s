#define _POSIX_C_SOURCE 200809L
#include <alsa/asoundlib.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static int loops=256;
static void*produce(void*argument){
 long mode=(long)argument;int result=0;snd_pcm_t*pcm=NULL;
 int rc=snd_pcm_open(&pcm,"testclient",SND_PCM_STREAM_PLAYBACK,0);
 if(rc>=0)rc=snd_pcm_set_params(pcm,SND_PCM_FORMAT_S16_LE,mode?SND_PCM_ACCESS_MMAP_INTERLEAVED:SND_PCM_ACCESS_RW_INTERLEAVED,2,mode?44100:48000,1,40000);
 if(rc<0){fprintf(stderr,"CLIENT_SETUP %s\n",snd_strerror(rc));if(pcm)snd_pcm_close(pcm);return (void*)1;}
 short block[960];for(int i=0;i<960;i++)block[i]=20000;
 for(int i=0;i<loops;i++){
  int offset=0;while(offset<480){
   snd_pcm_sframes_t n=mode?snd_pcm_mmap_writei(pcm,block+offset*2,480-offset):snd_pcm_writei(pcm,block+offset*2,480-offset);
   if(n==-EPIPE&&snd_pcm_recover(pcm,n,1)>=0)continue;
   if(n<=0){fprintf(stderr,"CLIENT_WRITE mode=%ld %s\n",mode,snd_strerror(n));result=1;goto done;}offset+=n;
  }
 }
 rc=snd_pcm_drain(pcm);if(rc<0){fprintf(stderr,"CLIENT_DRAIN %s\n",snd_strerror(rc));result=1;}
done:snd_pcm_drop(pcm);snd_pcm_close(pcm);return (void*)(long)result;
}
int main(int argc,char**argv){
 if(argc>1)loops=atoi(argv[1]);pthread_t a,b;void*ra,*rb;
 if(pthread_create(&a,NULL,produce,(void*)0)||pthread_create(&b,NULL,produce,(void*)1))return 2;
 pthread_join(a,&ra);pthread_join(b,&rb);if(ra||rb)return 1;puts("MIXED_RW_MMAP_CLIENTS_OK");return 0;
}

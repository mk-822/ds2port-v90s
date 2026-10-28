#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/mman.h>
#include <sys/eventfd.h>
#include <sys/timerfd.h>
#include <sys/stat.h>
#include <sys/prctl.h>
#include <pthread.h>
#include <signal.h>
#include <poll.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "audio_mix.h"
static _Atomic int running=1;
static int debug;
static void stop(int sig){(void)sig;atomic_store(&running,0);}
typedef struct {int fd,event;mix_shared*s;} client;
static client clients[MIX_CLIENTS];
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cond=PTHREAD_COND_INITIALIZER;
#define OUTPUT_BLOCKS 8
static int16_t output[OUTPUT_BLOCKS][MIX_PERIOD][2];static unsigned head,tail;static const char*device;
static void notify(client*c){uint64_t one=1;int rc=write(c->event,&one,8);(void)rc;}
static void remove_client(client*c){
 if(c->fd<0)return;atomic_store(&c->s->alive,0);notify(c);munmap(c->s,sizeof(*c->s));close(c->event);close(c->fd);c->fd=-1;
}
static void accept_client(int listener){
 int fd=accept4(listener,NULL,NULL,SOCK_CLOEXEC|SOCK_NONBLOCK);if(fd<0)return;
 client*c=NULL;for(int i=0;i<MIX_CLIENTS;i++)if(clients[i].fd<0){c=&clients[i];break;}if(!c){close(fd);return;}
 int memory=memfd_create("ds2port-audio",MFD_CLOEXEC),event=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);
 if(memory<0||event<0||ftruncate(memory,sizeof(mix_shared))<0){if(memory>=0)close(memory);if(event>=0)close(event);close(fd);return;}
 mix_shared*s=mmap(NULL,sizeof(*s),PROT_READ|PROT_WRITE,MAP_SHARED,memory,0);if(s==MAP_FAILED){close(memory);close(event);close(fd);return;}
 memset(s,0,sizeof(*s));s->magic=MIX_MAGIC;atomic_store(&s->alive,1);
 char byte=1,control[CMSG_SPACE(2*sizeof(int))]={0};struct iovec v={&byte,1};struct msghdr msg={.msg_iov=&v,.msg_iovlen=1,.msg_control=control,.msg_controllen=sizeof(control)};
 struct cmsghdr*h=CMSG_FIRSTHDR(&msg);h->cmsg_level=SOL_SOCKET;h->cmsg_type=SCM_RIGHTS;h->cmsg_len=CMSG_LEN(2*sizeof(int));int handles[]={memory,event};memcpy(CMSG_DATA(h),handles,sizeof(handles));
 int rc=sendmsg(fd,&msg,MSG_NOSIGNAL);close(memory);if(rc!=1){munmap(s,sizeof(*s));close(event);close(fd);return;}
 c->fd=fd;c->event=event;c->s=s;fprintf(stderr,"MIX_CLIENT_CONNECTED fd=%d\n",fd);
}
static void mix_block(void){
 int32_t sum[MIX_PERIOD][2]={0};
 for(int k=0;k<MIX_CLIENTS;k++){
  client*c=&clients[k];if(c->fd<0)continue;mix_shared*s=c->s;uint32_t reset=atomic_load(&s->reset);
  if(reset!=atomic_load(&s->ack)){atomic_store(&s->read,atomic_load(&s->write));atomic_store(&s->ack,reset);notify(c);continue;}
  if(atomic_load(&s->active)){
   uint64_t r=atomic_load(&s->read),w=atomic_load(&s->write);unsigned frames=w-r>MIX_PERIOD?MIX_PERIOD:w-r;
   // Contiguous spans let the compiler widen/add with AArch64 NEON.
   unsigned done=0;
   while(done<frames){unsigned at=(r+done)%MIX_CAPACITY,n=frames-done;if(n>MIX_CAPACITY-at)n=MIX_CAPACITY-at;
    int32_t*dst=&sum[done][0];const int16_t*src=&s->samples[at][0];
    for(unsigned i=0;i<n*2;i++)dst[i]+=src[i];done+=n;
   }
   atomic_store(&s->read,r+frames);
  }notify(c);
 }
 pthread_mutex_lock(&mutex);if(head-tail==OUTPUT_BLOCKS)tail++;
 for(int i=0;i<MIX_PERIOD;i++)for(int ch=0;ch<2;ch++){int v=sum[i][ch];output[head%OUTPUT_BLOCKS][i][ch]=v>32767?32767:v<-32768?-32768:v;}
 head++;pthread_cond_signal(&cond);pthread_mutex_unlock(&mutex);
 static unsigned ticks;if(debug&&++ticks%100==0){
  long peak=0;for(int i=0;i<MIX_PERIOD;i++)for(int ch=0;ch<2;ch++){long v=sum[i][ch];if(v<0)v=-v;if(v>peak)peak=v;}
  fprintf(stderr,"MIX_STATS peak=%ld",peak);for(int k=0;k<MIX_CLIENTS;k++)if(clients[k].fd>=0)fprintf(stderr," client%d=%lu/%lu",k,(unsigned long)atomic_load(&clients[k].s->read),(unsigned long)atomic_load(&clients[k].s->write));fputc('\n',stderr);
 }
}
static void*playback(void*unused){
 (void)unused;
 snd_pcm_t*pcm=NULL;unsigned long frames=0;int16_t block[MIX_PERIOD][2];
 while(running){
  pthread_mutex_lock(&mutex);while(running&&head==tail)pthread_cond_wait(&cond,&mutex);
  if(!running){pthread_mutex_unlock(&mutex);break;}memcpy(block,output[tail++%OUTPUT_BLOCKS],sizeof(block));pthread_mutex_unlock(&mutex);
  if(!pcm){int rc=snd_pcm_open(&pcm,device,SND_PCM_STREAM_PLAYBACK,0);
   if(rc>=0)rc=snd_pcm_set_params(pcm,SND_PCM_FORMAT_S16_LE,SND_PCM_ACCESS_RW_INTERLEAVED,2,48000,1,40000);
   if(rc<0){fprintf(stderr,"MIX_OUTPUT_OPEN %s\n",snd_strerror(rc));if(pcm)snd_pcm_close(pcm);pcm=NULL;usleep(20000);continue;}
   fprintf(stderr,"MIX_OUTPUT_READY rate=48000\n");
  }
  int offset=0;while(running&&offset<MIX_PERIOD){
   snd_pcm_sframes_t n=snd_pcm_writei(pcm,block[offset],MIX_PERIOD-offset);
   if(n==-EPIPE||n==-ESTRPIPE){int rc=snd_pcm_recover(pcm,n,1);if(rc>=0)continue;}
   if(n<=0){fprintf(stderr,"MIX_OUTPUT_REOPEN %ld\n",(long)n);snd_pcm_drop(pcm);snd_pcm_close(pcm);pcm=NULL;usleep(10000);break;}
   offset+=n;frames+=n;
  }
 }
 if(pcm){snd_pcm_drop(pcm);snd_pcm_close(pcm);}fprintf(stderr,"MIX_OUTPUT_FRAMES=%lu\n",frames);return NULL;
}
int main(int argc,char**argv){
 if(argc!=3||strlen(argv[1])>=sizeof(((struct sockaddr_un*)0)->sun_path))return 1;device=argv[2];
 for(int i=0;i<MIX_CLIENTS;i++)clients[i].fd=-1;
 struct sigaction sa={0};sa.sa_handler=stop;sigaction(SIGTERM,&sa,NULL);sigaction(SIGINT,&sa,NULL);signal(SIGPIPE,SIG_IGN);
 prctl(PR_SET_PDEATHSIG,SIGTERM);
 debug=getenv("DS2PORT_AUDIO_DEBUG")&&!strcmp(getenv("DS2PORT_AUDIO_DEBUG"),"1");
 int listener=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK,0);if(listener<0)return 2;
 struct sockaddr_un address={.sun_family=AF_UNIX};strcpy(address.sun_path,argv[1]);
 // The launcher owns this socket under its display lock; never unlink an
 // existing socket here or replace another running mixer.
 mode_t mask=umask(0077);int rc=bind(listener,(void*)&address,sizeof(address));umask(mask);if(rc<0){perror("audio socket bind");close(listener);return 3;}
 if(listen(listener,MIX_CLIENTS)<0)return 4;
 int timer=timerfd_create(CLOCK_MONOTONIC,TFD_CLOEXEC);struct itimerspec interval={{0,10000000},{0,10000000}};timerfd_settime(timer,0,&interval,NULL);
 pthread_t thread;if(pthread_create(&thread,NULL,playback,NULL))return 5;
 puts("AUDIO_MIXER_READY");fflush(stdout);
 while(running){
  struct pollfd f[MIX_CLIENTS+2];f[0]=(struct pollfd){listener,POLLIN,0};f[1]=(struct pollfd){timer,POLLIN,0};for(int i=0;i<MIX_CLIENTS;i++)f[i+2]=(struct pollfd){clients[i].fd,POLLIN,0};
  if(poll(f,MIX_CLIENTS+2,100)<0){if(errno==EINTR)continue;break;}
  for(int i=0;i<MIX_CLIENTS;i++)if(f[i+2].revents&(POLLHUP|POLLERR|POLLNVAL)){fprintf(stderr,"MIX_CLIENT_CLOSED fd=%d\n",clients[i].fd);remove_client(&clients[i]);}
  if(f[0].revents&POLLIN)accept_client(listener);
  if(f[1].revents&POLLIN){uint64_t ticks;if(read(timer,&ticks,8)==8){if(ticks>4)ticks=4;while(ticks--)mix_block();}}
 }
 for(int i=0;i<MIX_CLIENTS;i++)remove_client(&clients[i]);
 pthread_mutex_lock(&mutex);running=0;pthread_cond_signal(&cond);pthread_mutex_unlock(&mutex);
 struct timespec until;clock_gettime(CLOCK_REALTIME,&until);until.tv_sec+=2;
 if(pthread_timedjoin_np(thread,NULL,&until)){fprintf(stderr,"MIX_OUTPUT_EXIT_TIMEOUT\n");unlink(argv[1]);_exit(6);}
 close(timer);close(listener);unlink(argv[1]);return 0;
}

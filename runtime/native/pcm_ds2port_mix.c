#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <alsa/pcm_external.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/mman.h>
#include <poll.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "audio_mix.h"
typedef struct {snd_pcm_ioplug_t io;int socket,event;mix_shared*s;uint64_t base; snd_pcm_uframes_t boundary;} mix_pcm;
static int alive(mix_pcm*p){return atomic_load(&p->s->alive)?0:-ENODEV;}
static void events(mix_pcm*p){uint64_t n;while(read(p->event,&n,sizeof(n))>0){}}
static int start(snd_pcm_ioplug_t*io){mix_pcm*p=io->private_data;atomic_store(&p->s->active,1);return alive(p);}
static int stop(snd_pcm_ioplug_t*io){mix_pcm*p=io->private_data;atomic_store(&p->s->active,0);return 0;}
static int prepare(snd_pcm_ioplug_t*io){
 mix_pcm*p=io->private_data;atomic_store(&p->s->active,0);uint32_t epoch=atomic_fetch_add(&p->s->reset,1)+1;
 for(int i=0;i<100;i++){
  if(alive(p)<0)return -ENODEV;
  if(atomic_load(&p->s->ack)==epoch){p->base=atomic_load(&p->s->read);events(p);return 0;}
  struct pollfd f={p->event,POLLIN,0};poll(&f,1,10);events(p);
 }
 return -ETIMEDOUT;
}
static snd_pcm_sframes_t pointer(snd_pcm_ioplug_t*io){mix_pcm*p=io->private_data;if(alive(p)<0)return -ENODEV;return (atomic_load(&p->s->read)-p->base)%(p->boundary?p->boundary:io->buffer_size);}
static int sw_params(snd_pcm_ioplug_t*io,snd_pcm_sw_params_t*params){mix_pcm*p=io->private_data;return snd_pcm_sw_params_get_boundary(params,&p->boundary);}
static snd_pcm_sframes_t transfer(snd_pcm_ioplug_t*io,const snd_pcm_channel_area_t*areas,snd_pcm_uframes_t offset,snd_pcm_uframes_t size){
 mix_pcm*p=io->private_data;if(alive(p)<0)return -ENODEV;
 uint64_t w=atomic_load(&p->s->write),r=atomic_load(&p->s->read);uint64_t space=MIX_CAPACITY-(w-r);if(size>space)size=space;
 for(snd_pcm_uframes_t i=0;i<size;i++)for(int ch=0;ch<2;ch++){
  const char*src=(const char*)areas[ch].addr+(areas[ch].first+(offset+i)*areas[ch].step)/8;
  memcpy(&p->s->samples[(w+i)%MIX_CAPACITY][ch],src,2);
 }
 atomic_store(&p->s->write,w+size);return size;
}
static int delay(snd_pcm_ioplug_t*io,snd_pcm_sframes_t*d){mix_pcm*p=io->private_data;*d=atomic_load(&p->s->write)-atomic_load(&p->s->read);return alive(p);}
static int revents(snd_pcm_ioplug_t*io,struct pollfd*f,unsigned nfds,unsigned short*out){
 mix_pcm*p=io->private_data;*out=0;if(alive(p)<0){*out=POLLERR;return 0;}
 if(nfds>1&&(f[1].revents&(POLLHUP|POLLERR|POLLNVAL))){atomic_store(&p->s->alive,0);*out=POLLERR;return -ENODEV;}
 if(nfds&&f[0].revents&POLLIN){events(p);*out=POLLOUT;}
 return 0;
}
static int descriptors_count(snd_pcm_ioplug_t*io){(void)io;return 2;}
static int descriptors(snd_pcm_ioplug_t*io,struct pollfd*f,unsigned space){
 mix_pcm*p=io->private_data;if(space<2)return -ENOMEM;f[0]=(struct pollfd){p->event,POLLIN,0};f[1]=(struct pollfd){p->socket,POLLIN,0};return 2;
}
static int drain(snd_pcm_ioplug_t*io){
 mix_pcm*p=io->private_data;atomic_store(&p->s->active,1);
 for(int i=0;i<200;i++){
  if(alive(p)<0)return -ENODEV;
  if(atomic_load(&p->s->read)==atomic_load(&p->s->write))return 0;
  struct pollfd f={p->event,POLLIN,0};poll(&f,1,10);events(p);
 }return -ETIMEDOUT;
}
static int close_pcm(snd_pcm_ioplug_t*io){mix_pcm*p=io->private_data;atomic_store(&p->s->active,0);munmap(p->s,sizeof(*p->s));close(p->event);close(p->socket);free(p);return 0;}
static const snd_pcm_ioplug_callback_t callbacks={.start=start,.stop=stop,.pointer=pointer,.transfer=transfer,.prepare=prepare,.delay=delay,.poll_revents=revents,.poll_descriptors_count=descriptors_count,.poll_descriptors=descriptors,.drain=drain,.close=close_pcm,.sw_params=sw_params};
SND_PCM_PLUGIN_DEFINE_FUNC(ds2port_mix){
 if(stream!=SND_PCM_STREAM_PLAYBACK)return -EINVAL;
 const char*path=NULL;snd_config_iterator_t i,next;
 snd_config_for_each(i,next,conf){snd_config_t*n=snd_config_iterator_entry(i);const char*id;snd_config_get_id(n,&id);
  if(!strcmp(id,"type")||!strcmp(id,"comment")||!strcmp(id,"hint"))continue;
  if(!strcmp(id,"socket")){if(snd_config_get_string(n,&path)<0)return -EINVAL;}else return -EINVAL;
 }
 if(!path||strlen(path)>=sizeof(((struct sockaddr_un*)0)->sun_path))return -EINVAL;
 mix_pcm*p=calloc(1,sizeof(*p));if(!p)return -ENOMEM;p->event=-1;
 p->socket=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);if(p->socket<0){free(p);return -errno;}
 struct sockaddr_un addr={.sun_family=AF_UNIX};strcpy(addr.sun_path,path);
 if(connect(p->socket,(void*)&addr,sizeof(addr))<0){int rc=-errno;close(p->socket);free(p);return rc;}
 struct timeval timeout={2,0};setsockopt(p->socket,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
 char byte;char control[CMSG_SPACE(2*sizeof(int))];struct iovec v={&byte,1};struct msghdr msg={.msg_iov=&v,.msg_iovlen=1,.msg_control=control,.msg_controllen=sizeof(control)};
 int rc=-EIO,fd=-1;
 if(recvmsg(p->socket,&msg,MSG_CMSG_CLOEXEC)!=1)goto fail;
 struct cmsghdr*h=CMSG_FIRSTHDR(&msg);if(!h||h->cmsg_level!=SOL_SOCKET||h->cmsg_type!=SCM_RIGHTS||h->cmsg_len!=CMSG_LEN(2*sizeof(int)))goto fail;
 int handles[2];memcpy(handles,CMSG_DATA(h),sizeof(handles));fd=handles[0];p->event=handles[1];
 p->s=mmap(NULL,sizeof(*p->s),PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);close(fd);
 if(p->s==MAP_FAILED){p->s=NULL;goto fail;}
 if(p->s->magic!=MIX_MAGIC)goto fail;
 p->io.version=SND_PCM_IOPLUG_VERSION;p->io.name="DS2Port shared audio";p->io.flags=SND_PCM_IOPLUG_FLAG_MONOTONIC|SND_PCM_IOPLUG_FLAG_BOUNDARY_WA;
 p->io.poll_fd=p->event;p->io.poll_events=POLLIN;p->io.mmap_rw=0;p->io.callback=&callbacks;p->io.private_data=p;
 rc=snd_pcm_ioplug_create(&p->io,name,stream,mode);if(rc<0)goto fail;
 unsigned access[]={SND_PCM_ACCESS_RW_INTERLEAVED,SND_PCM_ACCESS_MMAP_INTERLEAVED};unsigned format[]={SND_PCM_FORMAT_S16_LE};
 if((rc=snd_pcm_ioplug_set_param_list(&p->io,SND_PCM_IOPLUG_HW_ACCESS,2,access))<0||
 (rc=snd_pcm_ioplug_set_param_list(&p->io,SND_PCM_IOPLUG_HW_FORMAT,1,format))<0||
 (rc=snd_pcm_ioplug_set_param_minmax(&p->io,SND_PCM_IOPLUG_HW_CHANNELS,2,2))<0||
 (rc=snd_pcm_ioplug_set_param_minmax(&p->io,SND_PCM_IOPLUG_HW_RATE,48000,48000))<0||
 (rc=snd_pcm_ioplug_set_param_minmax(&p->io,SND_PCM_IOPLUG_HW_PERIOD_BYTES,128,8192))<0||
 (rc=snd_pcm_ioplug_set_param_minmax(&p->io,SND_PCM_IOPLUG_HW_BUFFER_BYTES,512,32768))<0||
 (rc=snd_pcm_ioplug_set_param_minmax(&p->io,SND_PCM_IOPLUG_HW_PERIODS,2,64))<0){snd_pcm_ioplug_delete(&p->io);return rc;}
 *pcmp=p->io.pcm;return 0;
fail:if(p->s)munmap(p->s,sizeof(*p->s));if(p->event>=0)close(p->event);close(p->socket);free(p);return rc;
}
SND_PCM_PLUGIN_SYMBOL(ds2port_mix);


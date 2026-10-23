#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <alsa/pcm_external.h>
#include <alsa/pcm_extplug.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {snd_pcm_extplug_t ext;unsigned probe;int level;} volume_t;
static int read_level(void){const char*path=getenv("JUMP3_VOLUME_STATE");FILE*f=fopen(path?path:"/run/plumos/volume/current","r");int n=8;if(f){if(fscanf(f,"%d",&n)!=1)n=8;fclose(f);}if(n<0)n=0;if(n>12)n=12;return n;}
static snd_pcm_sframes_t transfer(snd_pcm_extplug_t*ext,const snd_pcm_channel_area_t*dst,snd_pcm_uframes_t doff,const snd_pcm_channel_area_t*src,snd_pcm_uframes_t soff,snd_pcm_uframes_t size){
 volume_t*v=ext->private_data;
 if(v->probe==0){int n=read_level();if(n!=v->level){fprintf(stderr,"JUMP3_AUDIO_VOLUME=%d/12\n",n);v->level=n;}v->probe=4410;}
 if(size>=v->probe)v->probe=0;else v->probe-=size;
 int gain=v->level*v->level;
 for(unsigned ch=0;ch<ext->channels;ch++)for(snd_pcm_uframes_t i=0;i<size;i++){
  const int16_t*in=(const int16_t*)((const unsigned char*)src[ch].addr+(src[ch].first+(soff+i)*src[ch].step)/8);
  int16_t*out=(int16_t*)((unsigned char*)dst[ch].addr+(dst[ch].first+(doff+i)*dst[ch].step)/8);
  *out=(int16_t)((int32_t)*in*gain/144);
 }
 return size;
}
static int close_plugin(snd_pcm_extplug_t*ext){free(ext->private_data);return 0;}
static const snd_pcm_extplug_callback_t callbacks={.transfer=transfer,.close=close_plugin};
SND_PCM_PLUGIN_DEFINE_FUNC(jump3_volume){
 snd_config_iterator_t i,next;snd_config_t*slave=0;
 snd_config_for_each(i,next,conf){snd_config_t*n=snd_config_iterator_entry(i);const char*id;if(snd_config_get_id(n,&id)<0)continue;if(!strcmp(id,"type")||!strcmp(id,"comment")||!strcmp(id,"hint"))continue;if(!strcmp(id,"slave")){slave=n;continue;}return -EINVAL;}
 if(!slave)return -EINVAL;volume_t*v=calloc(1,sizeof(*v));if(!v)return -ENOMEM;
 v->level=-1;v->ext.version=SND_PCM_EXTPLUG_VERSION;v->ext.name="JUMP3 OS volume";v->ext.callback=&callbacks;v->ext.private_data=v;
 int err=snd_pcm_extplug_create(&v->ext,name,root,slave,stream,mode);if(err<0){free(v);return err;}
 snd_pcm_extplug_set_param(&v->ext,SND_PCM_EXTPLUG_HW_FORMAT,SND_PCM_FORMAT_S16_LE);
 snd_pcm_extplug_set_slave_param(&v->ext,SND_PCM_EXTPLUG_HW_FORMAT,SND_PCM_FORMAT_S16_LE);
 snd_pcm_extplug_set_param(&v->ext,SND_PCM_EXTPLUG_HW_CHANNELS,2);
 snd_pcm_extplug_set_slave_param(&v->ext,SND_PCM_EXTPLUG_HW_CHANNELS,2);
 *pcmp=v->ext.pcm;return 0;
}
SND_PCM_PLUGIN_SYMBOL(jump3_volume);

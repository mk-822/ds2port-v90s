#include <alsa/asoundlib.h>
#include "adlmidi.h"
#include <cstdio>
#include <cstring>
#include <csignal>
#include <cstdint>
static volatile sig_atomic_t running=1;
static void stop(int){running=0;}
static void event(ADL_MIDIPlayer*d,const snd_seq_event_t*e){
 int ch=e->data.control.channel;
 switch(e->type){
 case SND_SEQ_EVENT_NOTEON: if(e->data.note.velocity)adl_rt_noteOn(d,e->data.note.channel,e->data.note.note,e->data.note.velocity);else adl_rt_noteOff(d,e->data.note.channel,e->data.note.note);break;
 case SND_SEQ_EVENT_NOTEOFF:adl_rt_noteOff(d,e->data.note.channel,e->data.note.note);break;
 case SND_SEQ_EVENT_KEYPRESS:adl_rt_noteAfterTouch(d,e->data.note.channel,e->data.note.note,e->data.note.velocity);break;
 case SND_SEQ_EVENT_CONTROLLER:
  if(e->data.control.param==120||e->data.control.param==123){
   adl_rt_controllerChange(d,ch,64,0);
   adl_rt_controllerChange(d,ch,120,0);
   for(int note=0;note<128;note++)adl_rt_noteOff(d,ch,note);
  }
  adl_rt_controllerChange(d,ch,e->data.control.param,e->data.control.value);break;
 case SND_SEQ_EVENT_PGMCHANGE:adl_rt_patchChange(d,ch,e->data.control.value);break;
 case SND_SEQ_EVENT_CHANPRESS:adl_rt_channelAfterTouch(d,ch,e->data.control.value);break;
 case SND_SEQ_EVENT_PITCHBEND:adl_rt_pitchBend(d,ch,e->data.control.value+8192);break;
 case SND_SEQ_EVENT_SYSEX:{
  const ADL_UInt8*s=(const ADL_UInt8*)e->data.ext.ptr;unsigned n=e->data.ext.len;
  bool gm=n>=6&&s[0]==0xf0&&(s[1]==0x7e||s[1]==0x7f)&&s[3]==9;
  bool gs=n>=11&&s[0]==0xf0&&s[1]==0x41&&s[3]==0x42&&s[4]==0x12&&s[5]==0x40&&s[6]==0&&s[7]==0x7f&&s[8]==0;
  if(gm||gs){adl_panic(d);adl_rt_resetState(d);}
  adl_rt_systemExclusive(d,s,n);break;
 }
 case SND_SEQ_EVENT_RESET:adl_panic(d);adl_rt_resetState(d);break;
 }
}
int main(int argc,char**argv){
 // Match the shared output mixer so hotplug/XRUN recovery does not pass
 // through a second ALSA rate converter. Synthesis and playback must agree.
 constexpr unsigned sample_rate=48000;
 ADL_MIDIPlayer*d=adl_init(sample_rate);if(!d){fprintf(stderr,"%s\n",adl_errorString());return 1;}
 adl_switchEmulator(d,ADLMIDI_EMU_DOSBOX);adl_setNumChips(d,1);
 int bank=58;const char*const*names=adl_getBankNames();for(int i=0;i<adl_getBanksCount();i++)if(strstr(names[i],"Win9x")){bank=i;break;}
 if(adl_setBank(d,bank)<0)return 2;adl_setNumFourOpsChn(d,0);adl_setVolumeRangeModel(d,ADLMIDI_VolumeModel_9X);
 printf("OPL3 DOSBox emulator, one YMF262 chip, bank=%d %s\n",bank,names[bank]);fflush(stdout);
 short samples[1024];
 if(argc==3&&!strcmp(argv[1],"--selftest")){
  FILE*f=fopen(argv[2],"wb");if(!f)return 3;adl_rt_patchChange(d,0,0);adl_rt_noteOn(d,0,60,100);long long energy=0;
  for(int i=0;i<86;i++){if(i==60)adl_rt_noteOff(d,0,60);int n=adl_generate(d,1024,samples);fwrite(samples,sizeof(short),n,f);for(int j=0;j<n;j++)energy+=(int64_t)samples[j]*samples[j];}
  fclose(f);printf("OPL3_SELFTEST_ENERGY=%lld\n",energy);adl_close(d);return energy>0?0:4;
 }
 snd_pcm_t*pcm=0;snd_seq_t*seq=0;int rc=snd_pcm_open(&pcm,"default",SND_PCM_STREAM_PLAYBACK,0);if(rc<0){fprintf(stderr,"PCM open: %s\n",snd_strerror(rc));return 5;}
 rc=snd_pcm_set_params(pcm,SND_PCM_FORMAT_S16_LE,SND_PCM_ACCESS_RW_INTERLEAVED,2,sample_rate,1,40000);if(rc<0){fprintf(stderr,"PCM setup: %s\n",snd_strerror(rc));return 6;}
 rc=snd_seq_open(&seq,"default",SND_SEQ_OPEN_INPUT,SND_SEQ_NONBLOCK);if(rc<0)return 7;
 snd_seq_set_client_name(seq,"JUMP3 SB16 OPL3");int port=snd_seq_create_simple_port(seq,"SB16 OPL3 MIDI",SND_SEQ_PORT_CAP_WRITE|SND_SEQ_PORT_CAP_SUBS_WRITE,SND_SEQ_PORT_TYPE_MIDI_GENERIC|SND_SEQ_PORT_TYPE_SYNTHESIZER|SND_SEQ_PORT_TYPE_APPLICATION);if(port<0)return 8;
 // This device's kernel silently clamps requests above 2000 to the old size.
 snd_seq_set_client_pool_input(seq,2000);snd_seq_set_input_buffer_size(seq,262144);
 snd_seq_client_pool_t*pool;snd_seq_client_pool_alloca(&pool);
 if(snd_seq_get_client_pool(seq,pool)<0||snd_seq_client_pool_get_input_pool(pool)<2000){fprintf(stderr,"MIDI input pool setup failed\n");return 9;}
 printf("MIDI_INPUT_POOL=%zu\n",snd_seq_client_pool_get_input_pool(pool));
 signal(SIGTERM,stop);signal(SIGINT,stop);printf("MIDI_SYNTH_READY client=%d port=%d\n",snd_seq_client_id(seq),port);fflush(stdout);
 unsigned long count=0;
 while(running){
  snd_seq_event_t*e=0;int input_rc;
  while((input_rc=snd_seq_event_input(seq,&e))>=0){event(d,e);if(count++<12){printf("MIDI_EVENT type=%d\n",e->type);fflush(stdout);}snd_seq_free_event(e);}
  if(input_rc==-ENOSPC){adl_panic(d);adl_rt_resetState(d);fprintf(stderr,"MIDI_INPUT_OVERRUN: voices reset\n");}
  int n=adl_generate(d,1024,samples);int offset=0;
  while(running&&offset<n/2){snd_pcm_sframes_t w=snd_pcm_writei(pcm,samples+offset*2,n/2-offset);if(w<0){if(snd_pcm_recover(pcm,w,1)<0){running=0;break;}}else offset+=w;}
 }
 printf("MIDI_EVENTS_TOTAL=%lu\n",count);snd_seq_close(seq);snd_pcm_drop(pcm);snd_pcm_close(pcm);adl_close(d);return 0;
}

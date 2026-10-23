#include "adlmidi.h"
#include <cstdio>
#include <ctime>
#include <cstdint>
#include <initializer_list>
static double cpu_time(){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(){
 for(int emulator: {ADLMIDI_EMU_DOSBOX,ADLMIDI_EMU_NUKED}){
  ADL_MIDIPlayer *player=adl_init(44100);if(!player)return 1;
  if(adl_switchEmulator(player,emulator)<0)return 2;
  adl_setNumChips(player,1);adl_setBank(player,58);adl_setNumFourOpsChn(player,0);
  adl_setVolumeRangeModel(player,ADLMIDI_VolumeModel_9X);
  for(int channel=0;channel<6;channel++){
   adl_rt_patchChange(player,channel,channel*8);
   adl_rt_noteOn(player,channel,48+channel*2,100);
   adl_rt_noteOn(player,channel,60+channel*2,100);
  }
  short output[1024];
  for(int n=0;n<173;n++)adl_generate(player,1024,output);
  int frames=0;int64_t energy=0;double start=cpu_time();
  while(frames<44100*20){
   int samples=adl_generate(player,1024,output);if(samples<=0)return 3;
   frames+=samples/2;
   for(int j=0;j<samples;j++)energy+=(int64_t)output[j]*output[j];
  }
  double cpu=cpu_time()-start,seconds=frames/44100.0;
  printf("emulator=%s chips=1 voices=12 rate=44100 audio_s=%.3f cpu_s=%.3f percent_one_core=%.2f energy=%lld\n",emulator==ADLMIDI_EMU_DOSBOX?"DOSBox":"Nuked",seconds,cpu,100*cpu/seconds,(long long)energy);fflush(stdout);
  adl_close(player);
 }
}

#include "adlmidi.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
int main(int argc,char**argv){
 if(argc<2||argc>3)return 1;
 unsigned rate=argc==3?(unsigned)strtoul(argv[2],nullptr,10):44100;
 for(int program:{0,73,80}){
  ADL_MIDIPlayer*d=adl_init(rate);if(!d)return 2;
  adl_switchEmulator(d,ADLMIDI_EMU_DOSBOX);adl_setNumChips(d,1);adl_setBank(d,58);
  adl_setNumFourOpsChn(d,0);adl_setVolumeRangeModel(d,ADLMIDI_VolumeModel_9X);
  adl_rt_patchChange(d,0,program);adl_rt_noteOn(d,0,69,100);
  char name[1024];snprintf(name,sizeof(name),"%s-%d.s16",argv[1],program);
  FILE*f=fopen(name,"wb");if(!f)return 3;
  short samples[1024];int frames=0;
  while(frames<rate*2){int n=adl_generate(d,1024,samples);if(n<=0)return 4;fwrite(samples,sizeof(short),n,f);frames+=n/2;}
  fclose(f);adl_close(d);printf("OPL_PITCH_PROBE program=%d note=69 rate=%u frames=%d\n",program,rate,frames);
 }
}

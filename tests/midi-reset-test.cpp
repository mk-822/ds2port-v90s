#define main jump3_synth_main
#include "sb16-synth.cpp"
#undef main
static long long energy(ADL_MIDIPlayer*d,int blocks){short b[1024];long long e=0;for(int i=0;i<blocks;i++){e=0;int n=adl_generate(d,1024,b);for(int j=0;j<n;j++)e+=(int64_t)b[j]*b[j];}return e;}
int main(){for(int mode=0;mode<3;mode++){
 ADL_MIDIPlayer*d=adl_init(44100);adl_switchEmulator(d,ADLMIDI_EMU_DOSBOX);adl_setNumChips(d,1);adl_setBank(d,58);adl_setNumFourOpsChn(d,0);
 adl_rt_patchChange(d,0,16);adl_rt_controllerChange(d,0,64,127);adl_rt_noteOn(d,0,60,100);energy(d,20);adl_rt_noteOff(d,0,60);long long before=energy(d,80);
 snd_seq_event_t e={};unsigned char gm[]={0xf0,0x7e,0x7f,9,1,0xf7};
 if(mode<2){e.type=SND_SEQ_EVENT_CONTROLLER;e.data.control.channel=0;e.data.control.param=mode?120:123;}
 else {e.type=SND_SEQ_EVENT_SYSEX;e.data.ext.ptr=gm;e.data.ext.len=sizeof(gm);}
 event(d,&e);long long after=energy(d,200);printf("RESET_TEST mode=%d sustained=%lld after=%lld\n",mode,before,after);adl_close(d);if(before<=0||after>before/1000)return 1;
 }return 0;}

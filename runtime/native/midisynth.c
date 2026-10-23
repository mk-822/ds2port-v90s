#include <dlfcn.h>
#include <stdio.h>
#include <unistd.h>
#include <signal.h>
static volatile int run=1;static void stop(int s){run=0;}
#define FN(name,ret,args) ret(*name)args=dlsym(lib,#name);if(!name){fprintf(stderr,"Missing %s\n",#name);return 2;}
int main(int argc,char**argv){
 if(argc<2)return 1;void*lib=dlopen("/mnt/plumos/lib/libfluidsynth.so.3.1.4",RTLD_NOW);if(!lib){fprintf(stderr,"%s\n",dlerror());return 2;}
 FN(new_fluid_settings,void*,(void));FN(fluid_settings_setstr,int,(void*,const char*,const char*));FN(fluid_settings_setnum,int,(void*,const char*,double));FN(fluid_settings_setint,int,(void*,const char*,int));
 FN(new_fluid_synth,void*,(void*));FN(fluid_synth_sfload,int,(void*,const char*,int));FN(new_fluid_audio_driver,void*,(void*,void*));FN(new_fluid_midi_driver,void*,(void*,void*,void*));
 FN(delete_fluid_midi_driver,void,(void*));FN(delete_fluid_audio_driver,void,(void*));FN(delete_fluid_synth,void,(void*));FN(delete_fluid_settings,void,(void*));
 void*s=new_fluid_settings();fluid_settings_setstr(s,"audio.driver","alsa");fluid_settings_setstr(s,"audio.alsa.device","default");fluid_settings_setstr(s,"midi.driver","alsa_seq");fluid_settings_setstr(s,"midi.alsa_seq.id","JUMP3");fluid_settings_setnum(s,"synth.sample-rate",44100);fluid_settings_setnum(s,"synth.gain",0.5);fluid_settings_setint(s,"synth.reverb.active",0);fluid_settings_setint(s,"synth.chorus.active",0);fluid_settings_setint(s,"synth.polyphony",64);
 void*synth=new_fluid_synth(s);if(!synth||fluid_synth_sfload(synth,argv[1],1)<0)return 3;
 void*audio=new_fluid_audio_driver(s,synth);if(!audio)return 4;
 void*midi=new_fluid_midi_driver(s,dlsym(lib,"fluid_synth_handle_midi_event"),synth);if(!midi)return 5;
 puts("MIDI_SYNTH_READY");fflush(stdout);signal(SIGTERM,stop);signal(SIGINT,stop);while(run)sleep(1);
 delete_fluid_midi_driver(midi);delete_fluid_audio_driver(audio);delete_fluid_synth(synth);delete_fluid_settings(s);return 0;
}

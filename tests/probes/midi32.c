#include <windows.h>
#include <mmsystem.h>
#include <stdio.h>
int main(void){unsigned n=midiOutGetNumDevs();printf("MIDI_DEVICES=%u\n",n);for(unsigned i=0;i<n;i++){MIDIOUTCAPSA c={0};MMRESULT r=midiOutGetDevCapsA(i,&c,sizeof(c));printf("MIDI_DEVICE_%u result=%u name=%s type=%u\n",i,r,c.szPname,c.wTechnology);}HMIDIOUT m;MMRESULT r=midiOutOpen(&m,MIDI_MAPPER,0,0,0);printf("MIDI_OPEN=%u\n",r);fflush(stdout);if(r)return 2;midiOutShortMsg(m,0x00643c90);Sleep(500);midiOutShortMsg(m,0x00003c80);midiOutClose(m);puts("MIDI_NOTE_OK");fflush(stdout);return 0;}

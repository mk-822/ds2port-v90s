#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#include <mmreg.h>
#include <dsound.h>
#include <stdio.h>
#include <stdint.h>
static int check(HRESULT hr,const char*what){if(FAILED(hr)){printf("FAIL %s %08lx\n",what,hr);return 0;}return 1;}
int main(void){LPDIRECTSOUND ds=0;if(!check(DirectSoundCreate(0,&ds,0),"create"))return 1;if(!check(IDirectSound_SetCooperativeLevel(ds,GetDesktopWindow(),DSSCL_NORMAL),"coop"))return 2;
unsigned tests=0;int channels[]={1,2,1,2,2};int bits[]={8,8,16,16,32};int rates[]={11025,22050,44100,48000,96000,12345};
for(int f=0;f<5;f++)for(int r=0;r<6;r++){
 WAVEFORMATEX fmt={0};fmt.wFormatTag=f==4?WAVE_FORMAT_IEEE_FLOAT:WAVE_FORMAT_PCM;fmt.nChannels=channels[f];fmt.nSamplesPerSec=rates[r];fmt.wBitsPerSample=bits[f];fmt.nBlockAlign=fmt.nChannels*fmt.wBitsPerSample/8;fmt.nAvgBytesPerSec=fmt.nSamplesPerSec*fmt.nBlockAlign;
 DWORD size=(fmt.nSamplesPerSec/8)*fmt.nBlockAlign;DSBUFFERDESC desc={0};desc.dwSize=sizeof(desc);desc.dwFlags=DSBCAPS_GLOBALFOCUS|DSBCAPS_CTRLFREQUENCY|DSBCAPS_CTRLVOLUME;desc.dwBufferBytes=size;desc.lpwfxFormat=&fmt;LPDIRECTSOUNDBUFFER a=0,b=0;
 if(!check(IDirectSound_CreateSoundBuffer(ds,&desc,&a,0),"buffer"))return 3;
 void*p,*q;DWORD n,m;if(!check(IDirectSoundBuffer_Lock(a,0,size,&p,&n,&q,&m,0),"lock"))return 4;
 if(f==4)for(unsigned i=0;i<n/4;i++)((float*)p)[i]=(i%2?1.f:-1.f)*.001f;
 else if(bits[f]==8)for(unsigned i=0;i<n;i++)((unsigned char*)p)[i]=128+(i%2?1:-1);
 else for(unsigned i=0;i<n/2;i++)((short*)p)[i]=i%2?32:-32;
 IDirectSoundBuffer_Unlock(a,p,n,q,m);IDirectSoundBuffer_SetVolume(a,-4500);if(!check(IDirectSoundBuffer_Play(a,0,0,DSBPLAY_LOOPING),"play"))return 5;Sleep(80);
 if(!check(IDirectSound_DuplicateSoundBuffer(ds,a,&b),"duplicate"))return 6;
 if(!check(IDirectSoundBuffer_SetFrequency(a,rates[(r+1)%6]),"frequency"))return 7;
 if(!check(IDirectSoundBuffer_SetCurrentPosition(b,size/2/ fmt.nBlockAlign*fmt.nBlockAlign),"seek"))return 8;
 if(!check(IDirectSoundBuffer_Play(b,0,0,DSBPLAY_LOOPING),"duplicate play"))return 9;Sleep(60);
 IDirectSoundBuffer_Stop(a);IDirectSoundBuffer_Release(a);Sleep(40);
 DWORD pos,write;if(!check(IDirectSoundBuffer_GetCurrentPosition(b,&pos,&write),"position")||pos>=size)return 10;
 IDirectSoundBuffer_Stop(b);IDirectSoundBuffer_SetFrequency(b,rates[r]);IDirectSoundBuffer_SetCurrentPosition(b,0);
 if(!check(IDirectSoundBuffer_Play(b,0,0,0),"nonloop"))return 11;
 DWORD status=0;for(int i=0;i<100;i++){Sleep(10);IDirectSoundBuffer_GetStatus(b,&status);if(!(status&DSBSTATUS_PLAYING))break;}if(status&DSBSTATUS_PLAYING){printf("FAIL nonloop-end\n");return 12;}
 IDirectSoundBuffer_Release(b);tests++;printf("CASE_OK format=%d channels=%d bits=%d rate=%d\n",f,channels[f],bits[f],rates[r]);fflush(stdout);
}printf("FUNCTIONAL_ALL_OK %u\nALL_CASES_DONE\n",tests);fflush(stdout);TerminateProcess(GetCurrentProcess(),0);return 0;}

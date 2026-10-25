#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#include <dsound.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
static double ms(void){LARGE_INTEGER n,f;QueryPerformanceCounter(&n);QueryPerformanceFrequency(&f);return 1000.*n.QuadPart/f.QuadPart;}
static double cpu(void){FILETIME a,b,k,u;GetProcessTimes(GetCurrentProcess(),&a,&b,&k,&u);ULARGE_INTEGER x,y;x.LowPart=k.dwLowDateTime;x.HighPart=k.dwHighDateTime;y.LowPart=u.dwLowDateTime;y.HighPart=u.dwHighDateTime;return (x.QuadPart+y.QuadPart)/10000.;}
static LPDIRECTSOUND ds;
static int duration_ms=6000;
static int run_case(int count,int rate){
 HRESULT hr;
 WAVEFORMATEX fmt={WAVE_FORMAT_PCM,1,rate,rate,1,8,0};DSBUFFERDESC desc={0};desc.dwSize=sizeof(desc);desc.dwFlags=DSBCAPS_GLOBALFOCUS|DSBCAPS_CTRLVOLUME|DSBCAPS_GETCURRENTPOSITION2;desc.dwBufferBytes=rate;desc.lpwfxFormat=&fmt;
 LPDIRECTSOUNDBUFFER bufs[64]={0};
 for(int i=0;i<count;i++){
  hr=IDirectSound_CreateSoundBuffer(ds,&desc,&bufs[i],0);if(FAILED(hr)){printf("BUFFER_FAIL %d %lx\n",i,hr);return 3;}
  void*p,*q;DWORD n,m;IDirectSoundBuffer_Lock(bufs[i],0,rate,&p,&n,&q,&m,0);for(DWORD j=0;j<n;j++)((unsigned char*)p)[j]=128+((j/24)%2?4:-4);IDirectSoundBuffer_Unlock(bufs[i],p,n,q,m);IDirectSoundBuffer_SetVolume(bufs[i],-3000);IDirectSoundBuffer_Play(bufs[i],0,0,DSBPLAY_LOOPING);
 }
 printf("CASE_READY voices=%d rate=%d\n",count,rate);fflush(stdout);Sleep(1000);double t=ms(),c=cpu(),sum=0,max=0;unsigned calls=0,over5=0,over20=0;unsigned cycles=0;
 while(ms()-t<duration_ms){double a=ms();DWORD play,write;
  IDirectSoundBuffer_GetCurrentPosition(bufs[cycles%count],&play,&write);
  IDirectSoundBuffer_SetCurrentPosition(bufs[cycles%count],0);IDirectSoundBuffer_Play(bufs[cycles%count],0,0,DSBPLAY_LOOPING);
  double elapsed=ms()-a;sum+=elapsed;if(elapsed>max)max=elapsed;if(elapsed>5)over5++;if(elapsed>20)over20++;calls++;cycles++;Sleep(20);
 }
 double duration=ms()-t;printf("DSOUND_STRESS voices=%d rate=%d wall_ms=%.1f cpu_ms=%.1f cpu_pct=%.1f calls=%u api_mean_ms=%.3f api_max_ms=%.3f over5=%u over20=%u\n",count,rate,duration,cpu()-c,100*(cpu()-c)/duration,calls,sum/calls,max,over5,over20);fflush(stdout);
 for(int i=0;i<count;i++){IDirectSoundBuffer_Stop(bufs[i]);IDirectSoundBuffer_Release(bufs[i]);}printf("CASE_RELEASED voices=%d rate=%d\n",count,rate);fflush(stdout);return 0;
}

int main(int argc,char**argv){HRESULT hr=DirectSoundCreate(0,&ds,0);if(FAILED(hr))return 1;hr=IDirectSound_SetCooperativeLevel(ds,GetDesktopWindow(),DSSCL_NORMAL);if(FAILED(hr)){printf("COOP_FAIL %lx\n",hr);return 4;}if(argc>=3){if(argc>3)duration_ms=atoi(argv[3]);int rc=run_case(atoi(argv[1]),atoi(argv[2]));printf("ALL_CASES_DONE\n");fflush(stdout);TerminateProcess(GetCurrentProcess(),rc);return rc;}int counts[]={1,8,16,32,32};for(int i=0;i<5;i++){int rc=run_case(counts[i],i==4?48000:11025);if(rc)return rc;}printf("ALL_CASES_DONE\n");fflush(stdout);ExitProcess(0);}

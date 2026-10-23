#include <windows.h>
#include <mmsystem.h>
#include <stdio.h>
int main(int argc,char**argv){
 int seconds=argc>1?atoi(argv[1]):1;
 printf("JOY_NUM_DEVS=%u\n",joyGetNumDevs());
 for(UINT id=0;id<16;id++){
  JOYCAPSA caps;MMRESULT rc=joyGetDevCapsA(id,&caps,sizeof(caps));
  if(!rc)printf("JOY_CAPS id=%u name=%s buttons=%u axes=%u mid=%x pid=%x\n",id,caps.szPname,caps.wNumButtons,caps.wNumAxes,caps.wMid,caps.wPid);
 }
 DWORD end=GetTickCount()+seconds*1000;
 while(GetTickCount()<end){
  for(UINT id=0;id<4;id++){
   JOYINFOEX state={0};state.dwSize=sizeof(state);state.dwFlags=JOY_RETURNALL;
   MMRESULT rc=joyGetPosEx(id,&state);
   if(!rc)printf("JOY_STATE id=%u x=%lu y=%lu buttons=%lu\n",id,state.dwXpos,state.dwYpos,state.dwButtons);
  }
  fflush(stdout);Sleep(100);
 }
 return 0;
}

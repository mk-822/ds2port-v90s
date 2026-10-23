#include <windows.h>
#include <stdio.h>
int main(void){int previous=-1;DWORD start=GetTickCount();puts("MOUSE_PROBE_READY");fflush(stdout);while(GetTickCount()-start<45000){int state=(GetAsyncKeyState(VK_LBUTTON)&0x8000)!=0;if(state!=previous){POINT p;GetCursorPos(&p);printf("WIN32_LEFT=%d ms=%lu x=%ld y=%ld\n",state,GetTickCount()-start,p.x,p.y);fflush(stdout);previous=state;}Sleep(5);}return 0;}

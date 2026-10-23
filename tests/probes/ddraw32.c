#define COBJMACROS
#include <windows.h>
#include <ddraw.h>
#include <stdio.h>
#define CHECK(call) do{HRESULT h=(call);printf(#call " = %08lx\n",h);fflush(stdout);if(FAILED(h))return 2;}while(0)
int main(void){
 HWND w=CreateWindowA("STATIC","DirectDraw 8bit probe",WS_POPUP|WS_VISIBLE,0,0,640,480,0,0,GetModuleHandle(0),0);
 LPDIRECTDRAW dd;CHECK(DirectDrawCreate(0,&dd,0));
 CHECK(IDirectDraw_SetCooperativeLevel(dd,w,DDSCL_EXCLUSIVE|DDSCL_FULLSCREEN));
 CHECK(IDirectDraw_SetDisplayMode(dd,640,480,8));
 DDSURFACEDESC sd={0};sd.dwSize=sizeof(sd);sd.dwFlags=DDSD_CAPS;sd.ddsCaps.dwCaps=DDSCAPS_PRIMARYSURFACE;
 LPDIRECTDRAWSURFACE s;CHECK(IDirectDraw_CreateSurface(dd,&sd,&s,0));
 PALETTEENTRY p[256]={0};p[1].peRed=220;p[1].peGreen=64;p[1].peBlue=64;p[2].peGreen=220;p[3].peBlue=220;
 LPDIRECTDRAWPALETTE pal;CHECK(IDirectDraw_CreatePalette(dd,DDPCAPS_8BIT|DDPCAPS_ALLOW256,p,&pal,0));CHECK(IDirectDrawSurface_SetPalette(s,pal));
 DDBLTFX fx={0};fx.dwSize=sizeof(fx);fx.dwFillColor=1;CHECK(IDirectDrawSurface_Blt(s,0,0,0,DDBLT_COLORFILL|DDBLT_WAIT,&fx));
 puts("DIRECTDRAW_8BIT_OK");fflush(stdout);
 DWORD end=GetTickCount()+12000;MSG m;while(GetTickCount()<end){while(PeekMessage(&m,0,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessage(&m);}Sleep(10);}
 IDirectDrawSurface_Release(s);IDirectDrawPalette_Release(pal);IDirectDraw_RestoreDisplayMode(dd);IDirectDraw_Release(dd);DestroyWindow(w);return 0;
}

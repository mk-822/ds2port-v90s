#include <windows.h>
#include <stdio.h>
#ifdef GUI
LRESULT CALLBACK proc(HWND w,UINT m,WPARAM a,LPARAM b) {
 if(m==WM_PAINT) { PAINTSTRUCT ps; HDC dc=BeginPaint(w,&ps); RECT r;GetClientRect(w,&r);HBRUSH br=CreateSolidBrush(RGB(16,48,80));FillRect(dc,&r,br);DeleteObject(br);SetTextColor(dc,RGB(255,255,255));SetBkMode(dc,TRANSPARENT);TextOutA(dc,30,50,"WIN32 GDI OK - JUMP3",20);EndPaint(w,&ps);puts("GDI_PAINT_OK");fflush(stdout);return 0;}
 if(m==WM_TIMER) {DestroyWindow(w);return 0;} if(m==WM_DESTROY){PostQuitMessage(0);return 0;}return DefWindowProc(w,m,a,b);
}
int main(void) {WNDCLASSA wc={0};wc.lpfnWndProc=proc;wc.hInstance=GetModuleHandle(0);wc.lpszClassName="Jump3Probe";RegisterClassA(&wc);HWND w=CreateWindowA(wc.lpszClassName,"Win32 GDI probe",WS_OVERLAPPEDWINDOW|WS_VISIBLE,0,0,640,480,0,0,wc.hInstance,0);if(!w)return 2;SetTimer(w,1,15000,0);MSG m;while(GetMessage(&m,0,0,0)>0){TranslateMessage(&m);DispatchMessage(&m);}return 0;}
#else
int main(void) {printf("WIN32_CONSOLE_OK pointer_bits=%u\n",(unsigned)(sizeof(void*)*8));return sizeof(void*)==4?0:1;}
#endif

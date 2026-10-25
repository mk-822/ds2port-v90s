#include <windows.h>
#include <stdio.h>
static const int keys[]={VK_LEFT,VK_RIGHT,VK_UP,VK_DOWN,'Z','X','C',VK_ESCAPE,VK_RETURN};
static const char*names[]={"LEFT","RIGHT","UP","DOWN","Z","X","C","ESC","ENTER"};
static LRESULT CALLBACK window_proc(HWND window,UINT message,WPARAM w,LPARAM l){
 if(message==WM_PAINT){const char*text="KEYBOARD INPUT TEST - arrows / Z X C Esc / Enter";PAINTSTRUCT p;HDC dc=BeginPaint(window,&p);TextOutA(dc,20,30,text,lstrlenA(text));EndPaint(window,&p);return 0;}
 if(message==WM_CLOSE){DestroyWindow(window);return 0;}
 return DefWindowProcA(window,message,w,l);
}
int main(void){
 WNDCLASSA wc={0};wc.lpfnWndProc=window_proc;wc.hInstance=GetModuleHandleA(NULL);wc.lpszClassName="DS2PortKeyboardTest";
 RegisterClassA(&wc);HWND window=CreateWindowA(wc.lpszClassName,"Keyboard input test",WS_VISIBLE|WS_POPUP,0,0,640,480,NULL,NULL,wc.hInstance,NULL);
 if(!window)return 2;SetForegroundWindow(window);SetFocus(window);
 int previous[9]={0};DWORD begin=GetTickCount();puts("KEYBOARD_TEST_READY");fflush(stdout);
 while(IsWindow(window)&&GetTickCount()-begin<120000){
  MSG message;while(PeekMessageA(&message,NULL,0,0,PM_REMOVE)){TranslateMessage(&message);DispatchMessageA(&message);}
  for(unsigned i=0;i<sizeof(keys)/sizeof(keys[0]);i++){
   int down=!!(GetAsyncKeyState(keys[i])&0x8000);
   if(down!=previous[i]){printf("WIN32_KEY %s=%d\n",names[i],down);fflush(stdout);previous[i]=down;}
  }
  Sleep(2);
 }
 puts("KEYBOARD_TEST_DONE");fflush(stdout);return 0;
}

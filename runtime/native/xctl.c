#include <X11/Xlib.h>
#include <dlfcn.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc,char**argv){Display*d=XOpenDisplay(0);if(!d||argc<3)return 1;void*lib=dlopen("libXtst.so.6",RTLD_NOW);if(!lib)return 2;
int(*motion)(Display*,int,int,int,unsigned long)=dlsym(lib,"XTestFakeMotionEvent");int(*button)(Display*,unsigned int,int,unsigned long)=dlsym(lib,"XTestFakeButtonEvent");int(*key)(Display*,unsigned int,int,unsigned long)=dlsym(lib,"XTestFakeKeyEvent");
if(!strcmp(argv[1],"move")&&argc==4)motion(d,-1,atoi(argv[2]),atoi(argv[3]),0);
if(!strcmp(argv[1],"focus")){Window w=strtoul(argv[2],0,0);XSetInputFocus(d,w,RevertToParent,CurrentTime);}
if(!strcmp(argv[1],"click")){button(d,atoi(argv[2]),1,0);XFlush(d);usleep(500000);button(d,atoi(argv[2]),0,0);}
if(!strcmp(argv[1],"key")){int k=XKeysymToKeycode(d,XStringToKeysym(argv[2]));key(d,k,1,0);XFlush(d);usleep(500000);key(d,k,0,0);}
XSync(d,0);XCloseDisplay(d);return 0;}

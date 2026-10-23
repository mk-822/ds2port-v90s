#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <signal.h>
#include <string.h>
#include <dlfcn.h>
#include <alsa/asoundlib.h>
#include <math.h>
static int update_volume(int previous){
 FILE*f=fopen("/run/plumos/volume/current","r");int level;
 if(!f)return previous;int ok=fscanf(f,"%d",&level);fclose(f);if(ok!=1)return previous;
 if(level<0)level=0;if(level>12)level=12;if(level==previous)return previous;
 fprintf(stderr,"OS_VOLUME=%d (shared PCM volume filter)\n",level);return level;
}
static volatile int running=1;
static void stop(int x){running=0;}
int main(int argc,char**argv){
 signal(SIGTERM,stop);signal(SIGINT,stop);
 Display*d=XOpenDisplay(0);if(!d){perror("XOpenDisplay");return 1;}
 if(argc>1){XImage*i=XGetImage(d,DefaultRootWindow(d),0,0,640,480,AllPlanes,ZPixmap);if(!i)return 4;FILE*out=fopen(argv[1],"wb");if(!out)return 5;fprintf(out,"P6\n640 480\n255\n");for(int y=0;y<480;y++)for(int x=0;x<640;x++){unsigned long p=XGetPixel(i,x,y);unsigned char rgb[3]={p>>16,p>>8,p};fwrite(rgb,1,3,out);}fclose(out);XDestroyImage(i);XCloseDisplay(d);return 0;}
 int f=open("/dev/fb0",O_RDWR);struct fb_var_screeninfo v;struct fb_fix_screeninfo fi;
 if(f<0||ioctl(f,FBIOGET_VSCREENINFO,&v)||ioctl(f,FBIOGET_FSCREENINFO,&fi))return 2;
 unsigned char*fb=mmap(0,fi.smem_len,PROT_READ|PROT_WRITE,MAP_SHARED,f,0);if(fb==MAP_FAILED)return 3;
 fprintf(stderr,"FB %ux%u bpp=%u stride=%u offset=%u,%u RGB=%u,%u,%u\n",v.xres,v.yres,v.bits_per_pixel,fi.line_length,v.xoffset,v.yoffset,v.red.offset,v.green.offset,v.blue.offset);
 uint32_t alpha=v.transp.length?((1u<<v.transp.length)-1)<<v.transp.offset:0;
 Window root=DefaultRootWindow(d);
 void*xt=dlopen("libXtst.so.6",RTLD_NOW);
 int(*motion)(Display*,int,int,int,unsigned long)=xt?dlsym(xt,"XTestFakeMotionEvent"):0;
 int(*button)(Display*,unsigned int,int,unsigned long)=xt?dlsym(xt,"XTestFakeButtonEvent"):0;
 int(*key)(Display*,unsigned int,int,unsigned long)=xt?dlsym(xt,"XTestFakeKeyEvent"):0;
 int input=open("/dev/input/event4",O_RDONLY|O_NONBLOCK),mx=320,my=240,dx=0,dy=0,start=0,select=0,fast=0;
 int volume=-1,ticks=0;
 fprintf(stderr,"Controls: A=BTN_SOUTH left click, B=BTN_EAST right click, R2=BTN_TR2 x2; game cursor only\n");
 if(input>=0)ioctl(input,EVIOCGRAB,1);
 if(motion)motion(d,-1,mx,my,0);
 while(running){
 if(ticks++%5==0)volume=update_volume(volume);
 struct input_event ev;
 while(input>=0&&read(input,&ev,sizeof(ev))==sizeof(ev)){
 if(ev.type==EV_ABS){if(ev.code==ABS_HAT0X)dx=ev.value;if(ev.code==ABS_HAT0Y)dy=ev.value;}
 if(ev.type==EV_KEY&&ev.value!=2){
 int down=ev.value!=0;unsigned long sym=0;
 fprintf(stderr,"PAD_KEY=%u DOWN=%d\n",ev.code,down);
 if(ev.code==BTN_TR2)fast=down;
 if((ev.code==BTN_SOUTH||ev.code==BTN_EAST)&&button){
  int which=ev.code==BTN_SOUTH?0:1;
  int rc=button(d,which?3:1,down,0);XFlush(d);
  fprintf(stderr,"MOUSE_BUTTON button=%d code=%u down=%d xtest=%d\n",which?3:1,ev.code,down,rc);
 }
 if(ev.code==BTN_START){start=down;sym=0xff0d;}
 if(ev.code==BTN_SELECT){select=down;sym=0xff1b;}
 if(sym&&key)key(d,XKeysymToKeycode(d,sym),down,0);
 if(start&&select)running=0;
 }
 }
 if(dx||dy){int speed=fast?14:7;mx+=dx*speed;my+=dy*speed;if(mx<0)mx=0;if(mx>639)mx=639;if(my<0)my=0;if(my>479)my=479;if(motion)motion(d,-1,mx,my,0);}
 XFlush(d);
 XImage*i=XGetImage(d,root,0,0,640,480,AllPlanes,ZPixmap);
 if(i){
 if(i->bits_per_pixel==32&&v.red.offset==16&&v.green.offset==8&&v.blue.offset==0){
 for(unsigned y=0;y<v.yres&&y<480;y++){uint32_t*out=(uint32_t*)(fb+(y+v.yoffset)*fi.line_length+v.xoffset*4);memcpy(out,i->data+y*i->bytes_per_line,640*4);if(alpha)for(int x=0;x<640;x++)out[x]|=alpha;}
 }else for(unsigned y=0;y<v.yres&&y<480;y++)for(unsigned x=0;x<v.xres&&x<640;x++){
 unsigned long p=XGetPixel(i,x,y);uint32_t q=alpha|((p>>16)&255)<<v.red.offset|((p>>8)&255)<<v.green.offset|(p&255)<<v.blue.offset;
 *((uint32_t*)(fb+(y+v.yoffset)*fi.line_length+(x+v.xoffset)*4))=q;
 }
 XDestroyImage(i);
 }
 usleep(33000);
 }
 if(input>=0){ioctl(input,EVIOCGRAB,0);close(input);}munmap(fb,fi.smem_len);close(f);XCloseDisplay(d);return 0;
}

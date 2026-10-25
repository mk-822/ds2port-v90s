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
#include <stdlib.h>
#include <limits.h>
#include <time.h>
#include <errno.h>
#include "frame_capture.h"
#include "virtual_joypad.h"
#include "input_mode.h"
#include "mode_banner.h"
typedef struct {Display*d;int(*send)(Display*,unsigned int,int,unsigned long);} KeyOutput;
static void emit_key(void*context,unsigned long sym,int down){
 KeyOutput*out=context;
 if(out->send)out->send(out->d,XKeysymToKeycode(out->d,sym),down,0);
 fprintf(stderr,"KEYBOARD_KEY keysym=%#lx down=%d\n",sym,down);
}
static int64_t clock_ns(void){
 struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
 return (int64_t)t.tv_sec*1000000000+t.tv_nsec;
}
static double setting(const char*name,double fallback,double low,double high){
 const char*text=getenv(name);char*end;
 if(!text||!*text)return fallback;
 double value=strtod(text,&end);
 return *end||!isfinite(value)||value<low||value>high?fallback:value;
}
static int update_volume(int previous){
 FILE*f=fopen("/run/plumos/volume/current","r");int level;
 if(!f)return previous;int ok=fscanf(f,"%d",&level);fclose(f);if(ok!=1)return previous;
 if(level<0)level=0;if(level>12)level=12;if(level==previous)return previous;
 fprintf(stderr,"OS_VOLUME=%d (shared PCM volume filter)\n",level);return level;
}
static volatile int running=1;
static volatile sig_atomic_t resumed=0;
static void stop(int x){running=0;}
static void continued(int x){resumed=1;}
int main(int argc,char**argv){
 signal(SIGTERM,stop);signal(SIGINT,stop);
 signal(SIGCONT,continued);
 Display*d=XOpenDisplay(0);if(!d){perror("XOpenDisplay");return 1;}
 if(argc>1){XImage*i=XGetImage(d,DefaultRootWindow(d),0,0,640,480,AllPlanes,ZPixmap);if(!i)return 4;FILE*out=fopen(argv[1],"wb");if(!out)return 5;fprintf(out,"P6\n640 480\n255\n");for(int y=0;y<480;y++)for(int x=0;x<640;x++){unsigned long p=XGetPixel(i,x,y);unsigned char rgb[3]={p>>16,p>>8,p};fwrite(rgb,1,3,out);}fclose(out);XDestroyImage(i);XCloseDisplay(d);return 0;}
 int f=open("/dev/fb0",O_RDWR);struct fb_var_screeninfo v;struct fb_fix_screeninfo fi;
 if(f<0||ioctl(f,FBIOGET_VSCREENINFO,&v)||ioctl(f,FBIOGET_FSCREENINFO,&fi))return 2;
 unsigned char*fb=mmap(0,fi.smem_len,PROT_READ|PROT_WRITE,MAP_SHARED,f,0);if(fb==MAP_FAILED)return 3;
 fprintf(stderr,"FB %ux%u bpp=%u stride=%u offset=%u,%u RGB=%u,%u,%u\n",v.xres,v.yres,v.bits_per_pixel,fi.line_length,v.xoffset,v.yoffset,v.red.offset,v.green.offset,v.blue.offset);
 uint32_t alpha=v.transp.length?((1u<<v.transp.length)-1)<<v.transp.offset:0;
 const char*present_mode=getenv("DS2PORT_PRESENT");
 int double_buffer=(!present_mode||strcmp(present_mode,"single"))&&v.yres==480&&
  v.yres_virtual>=v.yres*2&&fi.ypanstep&&v.yoffset%v.yres==0&&v.yoffset<v.yres*2&&
  (uint64_t)fi.line_length*v.yres*2<=fi.smem_len;
 fprintf(stderr,"DISPLAY_PRESENT=%s\n",double_buffer?"pageflip-vblank":"single");
 Window root=DefaultRootWindow(d);
 void*xt=dlopen("libXtst.so.6",RTLD_NOW);
 int(*motion)(Display*,int,int,int,unsigned long)=xt?dlsym(xt,"XTestFakeMotionEvent"):0;
 int(*button)(Display*,unsigned int,int,unsigned long)=xt?dlsym(xt,"XTestFakeButtonEvent"):0;
 int(*key)(Display*,unsigned int,int,unsigned long)=xt?dlsym(xt,"XTestFakeKeyEvent"):0;
 int input=open("/dev/input/event4",O_RDONLY|O_NONBLOCK),mx=320,my=240,dx=0,dy=0,start=0,select=0,fast_r2=0,fast_y=0;
 int volume=-1;
 VirtualJoypad joy;int joy_result=joy_open(&joy);
 InputMode mode=input_mode_parse(getenv("DS2PORT_INPUT_MODE"));
 if(mode==INPUT_JOYPAD&&joy_result<0){fprintf(stderr,"Cannot start Joypad mode: uinput unavailable\n");return 6;}
 unsigned faces=0;BridgeKeys keys={0};KeyOutput key_output={d,key};
 int l2_down=0;
 int64_t banner_started=clock_ns();int banner_slide=0;
 FrameCapture capture;
 const char*capture_mode=getenv("DS2PORT_CAPTURE");
 capture_open(&capture,d,!capture_mode||strcmp(capture_mode,"ximage"));
 double fps=setting("DS2PORT_FPS",60,10,120);
 /* The old copy+33ms loop ran at about 17Hz, moving 7 pixels per frame.
  * Preserve its feel independently of the new display refresh rate. */
 double cursor_speed=setting("DS2PORT_CURSOR_SPEED",120,10,2000);
 double cursor_x=mx,cursor_y=my;
 int64_t period=(int64_t)(1000000000/fps),deadline=clock_ns(),cursor_time=deadline;
 int64_t volume_time=0,report_time=deadline;
 uint64_t frames=0,changed=0,previous_hash=0;
 double read_time=0,copy_time=0,present_time=0;
 fprintf(stderr,"DISPLAY_CAPTURE=%s target_fps=%.1f cursor_px_s=%.1f\n",capture.shared?"shm":"ximage",fps,cursor_speed);
 char overlay[PATH_MAX];
 const char*runtime=getenv("PLUMOS_RUNTIME_ROOT");
 snprintf(overlay,sizeof(overlay),"%s/power-menu-overlay.lock",runtime&&*runtime?runtime:"/run/plumos");
 int was_menu=0;
 fprintf(stderr,"INPUT_MODE=%s\n",input_mode_name(mode));
 const char*ready=getenv("DS2PORT_BRIDGE_READY");
 if(ready){FILE*file=fopen(ready,"w");if(file){fprintf(file,"joypad=%d\n",joy.fd>=0);fclose(file);}}
 fprintf(stderr,"Controls: B=BTN_EAST left click, A=BTN_SOUTH right click, R2=BTN_TR2 or Y=BTN_WEST x2; game cursor only\n");
 /* PlumOS SIGSTOPs fb0 owners while its power menu is open. An evdev
  * exclusive grab survives SIGSTOP and would lock the menu out of the pad.
  * The Ports frontend is already stopped, so this reader need not grab it. */
 if(motion)motion(d,-1,mx,my,0);
 while(running){
 int menu=access(overlay,F_OK)==0;
 if(resumed||menu!=was_menu){
  resumed=0;
  struct input_event pending;
  while(input>=0&&read(input,&pending,sizeof(pending))==sizeof(pending)){}
  dx=dy=start=select=fast_r2=fast_y=0;faces=0;
  l2_down=0;joy_reset(&joy);banner_started=0;
  cursor_time=deadline=report_time=clock_ns();
  frames=changed=0;read_time=copy_time=present_time=0;
  if(button){button(d,1,0,0);button(d,3,0,0);}
  bridge_keys_update(&keys,mode,0,0,0,0,0,emit_key,&key_output);
  XFlush(d);
  if(!menu)ioctl(f,FBIOGET_VSCREENINFO,&v);
  fprintf(stderr,"POWER_MENU=%d input reset after overlay/continue\n",menu);
  was_menu=menu;
 }
 if(menu){
  struct input_event pending;
  while(input>=0&&read(input,&pending,sizeof(pending))==sizeof(pending)){}
  usleep(33000);continue;
 }
 int64_t frame_time=clock_ns();
 if(frame_time-volume_time>=250000000){volume=update_volume(volume);volume_time=frame_time;}
 struct input_event ev;
 while(input>=0&&read(input,&ev,sizeof(ev))==sizeof(ev)){
 if(resumed||access(overlay,F_OK)==0)break;
 if(ev.type==EV_ABS){
  if(ev.code==ABS_HAT0X){dx=ev.value;if(mode==INPUT_JOYPAD){joy_event(&joy,EV_ABS,ABS_X,dx*32767);joy_sync(&joy);}}
  if(ev.code==ABS_HAT0Y){dy=ev.value;if(mode==INPUT_JOYPAD){joy_event(&joy,EV_ABS,ABS_Y,dy*32767);joy_sync(&joy);}}
 }
 if(ev.type==EV_KEY&&ev.value!=2){
 int down=ev.value!=0;
 fprintf(stderr,"PAD_KEY=%u DOWN=%d\n",ev.code,down);
 if(ev.code==BTN_TL2){
  if(down&&!l2_down){
   joy_reset(&joy);dx=dy=start=select=fast_r2=fast_y=0;faces=0;
   if(button){button(d,1,0,0);button(d,3,0,0);}
   bridge_keys_update(&keys,mode,0,0,0,0,0,emit_key,&key_output);
   XFlush(d);mode=input_mode_next(mode,joy.fd>=0);banner_started=clock_ns();banner_slide=0;
   fprintf(stderr,"INPUT_MODE=%s\n",input_mode_name(mode));
  }
  l2_down=down;continue;
 }
 int number=ev.code==BTN_WEST?0:ev.code==BTN_EAST?1:ev.code==BTN_SOUTH?2:ev.code==BTN_NORTH?3:-1;
 if(number>=0){if(down)faces|=1u<<number;else faces&=~(1u<<number);}
 if(mode==INPUT_JOYPAD){
  if(number>=0){joy_event(&joy,EV_KEY,BTN_TRIGGER+number,down);joy_sync(&joy);fprintf(stderr,"JOYPAD_BUTTON=%d DOWN=%d\n",number+1,down);}
 }
 if(ev.code==BTN_TR2)fast_r2=down;
 if(ev.code==BTN_WEST)fast_y=down;
 if(mode==INPUT_MOUSE&&(ev.code==BTN_SOUTH||ev.code==BTN_EAST)&&button){
  int which=ev.code==BTN_EAST?0:1;
  int rc=button(d,which?3:1,down,0);XFlush(d);
  fprintf(stderr,"MOUSE_BUTTON button=%d code=%u down=%d xtest=%d\n",which?3:1,ev.code,down,rc);
 }
 if(ev.code==BTN_START)start=down;
 if(ev.code==BTN_SELECT)select=down;
 if(start&&select)running=0;
 }
 bridge_keys_update(&keys,mode,dx,dy,faces,start,select,emit_key,&key_output);
 }
 if(resumed||access(overlay,F_OK)==0)continue;
 double elapsed=(frame_time-cursor_time)/1e9;cursor_time=frame_time;
 if(elapsed>.1)elapsed=.1;
 if(mode==INPUT_MOUSE&&(dx||dy)){
  double speed=cursor_speed*((fast_r2||fast_y)?2:1);
  cursor_x+=dx*speed*elapsed;cursor_y+=dy*speed*elapsed;
  if(cursor_x<0)cursor_x=0;if(cursor_x>639)cursor_x=639;
  if(cursor_y<0)cursor_y=0;if(cursor_y>479)cursor_y=479;
  mx=(int)cursor_x;my=(int)cursor_y;if(motion)motion(d,-1,mx,my,0);
 }
 XFlush(d);
 int64_t read_start=clock_ns();
 XImage*i=capture_read(&capture);
 int64_t copy_start=clock_ns();
 if(i){
 unsigned render_y=double_buffer?(v.yoffset==0?v.yres:0):v.yoffset;
 if(i->bits_per_pixel==32&&v.red.offset==16&&v.green.offset==8&&v.blue.offset==0){
 for(unsigned y=0;y<v.yres&&y<480;y++){
  uint32_t*out=(uint32_t*)(fb+(y+render_y)*fi.line_length+v.xoffset*4);
  const uint32_t*in=(const uint32_t*)(i->data+y*i->bytes_per_line);
  /* Do not read framebuffer memory: uncached read/modify/write costs far
   * more than ORing alpha into the cached source before each store. */
  if(alpha)for(int x=0;x<640;x++)out[x]=in[x]|alpha;
  else memcpy(out,in,640*4);
 }
 }else for(unsigned y=0;y<v.yres&&y<480;y++)for(unsigned x=0;x<v.xres&&x<640;x++){
 unsigned long p=XGetPixel(i,x,y);uint32_t q=alpha|((p>>16)&255)<<v.red.offset|((p>>8)&255)<<v.green.offset|(p&255)<<v.blue.offset;
 *((uint32_t*)(fb+(y+render_y)*fi.line_length+(x+v.xoffset)*4))=q;
 }
 if(banner_started){
  if(clock_ns()-banner_started>=2000000000LL)banner_slide++;
  mode_banner(fb,&fi,&v,render_y,mode,-banner_slide);
  if(banner_slide>=34)banner_started=0;
 }
 int64_t copy_end=clock_ns();
 if(double_buffer){
  struct fb_var_screeninfo pan=v;pan.yoffset=render_y;pan.activate=FB_ACTIVATE_VBL;
  if(ioctl(f,FBIOPAN_DISPLAY,&pan)==0)v.yoffset=render_y;
  else{
   fprintf(stderr,"DISPLAY_PAGEFLIP_FAILED errno=%d; switching to single buffer\n",errno);
   double_buffer=0;ioctl(f,FBIOGET_VSCREENINFO,&v);
  }
 }
 present_time+=(clock_ns()-copy_end)/1e6;
 uint64_t hash=1469598103934665603ULL;
 for(int y=0;y<480;y+=8)for(int x=0;x<640;x+=8){hash^=XGetPixel(i,x,y);hash*=1099511628211ULL;}
 if(hash!=previous_hash)changed++;previous_hash=hash;
 read_time+=(copy_start-read_start)/1e6;copy_time+=(copy_end-copy_start)/1e6;frames++;
 capture_release(&capture);
 }
 int64_t current=clock_ns();
 if(current-report_time>=10000000000LL&&frames){
  double seconds=(current-report_time)/1e9;
  fprintf(stderr,"DISPLAY_STATS capture=%s present=%s fps=%.2f sampled_changes_s=%.2f read_ms=%.3f copy_ms=%.3f present_ms=%.3f\n",capture.shared?"shm":"ximage",double_buffer?"pageflip-vblank":"single",frames/seconds,changed/seconds,read_time/frames,copy_time/frames,present_time/frames);
  report_time=current;frames=changed=0;read_time=copy_time=present_time=0;
 }
 deadline+=period;
 if(deadline<current)deadline=current;
 struct timespec target={deadline/1000000000,deadline%1000000000};
 while(running&&clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&target,NULL)==EINTR&&!resumed){}
 }
 capture_close(&capture);
 bridge_keys_update(&keys,mode,0,0,0,0,0,emit_key,&key_output);XFlush(d);
 joy_close(&joy);
 if(ready)unlink(ready);
 if(input>=0)close(input);munmap(fb,fi.smem_len);close(f);XCloseDisplay(d);return 0;
}

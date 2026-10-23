#define _POSIX_C_SOURCE 200809L
#include <linux/fb.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdint.h>
#include <time.h>
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(int argc,char**argv){
 int fd=open("/dev/fb0",O_RDWR);struct fb_var_screeninfo v;struct fb_fix_screeninfo f;
 if(fd<0||ioctl(fd,FBIOGET_VSCREENINFO,&v)||ioctl(fd,FBIOGET_FSCREENINFO,&f))return 1;
 printf("FB width=%u height=%u virtual_height=%u offset=%u stride=%u ypanstep=%u memory=%u\n",v.xres,v.yres,v.yres_virtual,v.yoffset,f.line_length,f.ypanstep,f.smem_len);fflush(stdout);
 uint32_t crtc=0;
 for(int i=0;i<5;i++){
  double t=now();errno=0;int rc=ioctl(fd,FBIO_WAITFORVSYNC,&crtc);int error=errno;
  printf("VSYNC rc=%d errno=%d elapsed_ms=%.3f\n",rc,error,(now()-t)*1000);fflush(stdout);
  if(rc)break;
 }
 if(argc>1&&!strcmp(argv[1],"pan")&&v.yres_virtual>=v.yres*2&&v.bits_per_pixel==32){
  unsigned char*fb=mmap(NULL,f.smem_len,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);if(fb==MAP_FAILED)return 2;
  unsigned other=v.yoffset==0?v.yres:0;
  if((uint64_t)(other+v.yres)*f.line_length>f.smem_len)return 3;
  memcpy(fb+other*f.line_length,fb+v.yoffset*f.line_length,v.yres*f.line_length);
  struct fb_var_screeninfo pan=v;pan.yoffset=other;pan.activate=FB_ACTIVATE_VBL;
  int rc=0;
  for(int n=0;n<20;n++){
   pan.yoffset=n%2?v.yoffset:other;
   double t=now();errno=0;rc=ioctl(fd,FBIOPAN_DISPLAY,&pan);int error=errno;
   printf("PAN index=%d rc=%d errno=%d elapsed_ms=%.3f target=%u\n",n,rc,error,(now()-t)*1000,pan.yoffset);fflush(stdout);
   if(rc)break;
  }
  {
   v.activate=FB_ACTIVATE_VBL;
   int restored=ioctl(fd,FBIOPAN_DISPLAY,&v);
   ioctl(fd,FBIO_WAITFORVSYNC,&crtc);
   printf("PAN_RESTORE rc=%d offset=%u\n",restored,v.yoffset);
  }
  munmap(fb,f.smem_len);
 }
 close(fd);return 0;
}

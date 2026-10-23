#ifndef DS2PORT_VIRTUAL_JOYPAD_H
#define DS2PORT_VIRTUAL_JOYPAD_H
#include <linux/uinput.h>
#include <linux/input.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <dirent.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef struct {int fd;char database[128];} VirtualJoypad;
static void joy_event(VirtualJoypad*joy,unsigned type,unsigned code,int value){
 if(joy->fd<0)return;
 struct input_event event;memset(&event,0,sizeof(event));event.type=type;event.code=code;event.value=value;
 if(write(joy->fd,&event,sizeof(event))!=(ssize_t)sizeof(event))fprintf(stderr,"JOYPAD_WRITE_ERROR errno=%d\n",errno);
}
static void joy_sync(VirtualJoypad*joy){joy_event(joy,EV_SYN,SYN_REPORT,0);}
static void joy_reset(VirtualJoypad*joy){
 joy_event(joy,EV_ABS,ABS_X,0);joy_event(joy,EV_ABS,ABS_Y,0);
 for(int i=0;i<4;i++)joy_event(joy,EV_KEY,BTN_TRIGGER+i,0);
 joy_sync(joy);
}
static int joy_open(VirtualJoypad*joy){
 memset(joy,0,sizeof(*joy));joy->fd=open("/dev/uinput",O_WRONLY|O_NONBLOCK);
 if(joy->fd<0)return -1;
 int fd=joy->fd;
 if(ioctl(fd,UI_SET_EVBIT,EV_KEY)<0||ioctl(fd,UI_SET_EVBIT,EV_ABS)<0)goto fail;
 for(int i=0;i<4;i++)if(ioctl(fd,UI_SET_KEYBIT,BTN_TRIGGER+i)<0)goto fail;
 if(ioctl(fd,UI_SET_ABSBIT,ABS_X)<0||ioctl(fd,UI_SET_ABSBIT,ABS_Y)<0)goto fail;
 struct uinput_user_dev device;memset(&device,0,sizeof(device));
 snprintf(device.name,sizeof(device.name),"DS2Port 4 Button Joypad");
 device.id.bustype=BUS_USB;device.id.vendor=0x1209;device.id.product=0xd590;device.id.version=1;
 device.absmin[ABS_X]=device.absmin[ABS_Y]=-32767;
 device.absmax[ABS_X]=device.absmax[ABS_Y]=32767;
 if(write(fd,&device,sizeof(device))!=(ssize_t)sizeof(device)||ioctl(fd,UI_DEV_CREATE)<0)goto fail;
 /* PlumOS has no udev daemon. Give this process-owned virtual device its
  * classification record without modifying physical input device records. */
 char sysname[128]={0};
 if(ioctl(fd,UI_GET_SYSNAME(sizeof(sysname)),sysname)>=0){
  char path[256];snprintf(path,sizeof(path),"/sys/devices/virtual/input/%s",sysname);
  DIR*directory=opendir(path);struct dirent*entry;
  if(directory){
   while((entry=readdir(directory))){
    if(strncmp(entry->d_name,"event",5))continue;
    char node[256];snprintf(node,sizeof(node),"/dev/input/%s",entry->d_name);
    struct stat status;
    for(int attempt=0;attempt<20&&stat(node,&status)<0;attempt++)usleep(10000);
    if(stat(node,&status)<0)continue;
    mkdir("/run/udev",0755);mkdir("/run/udev/data",0755);
    snprintf(joy->database,sizeof(joy->database),"/run/udev/data/c%u:%u",major(status.st_rdev),minor(status.st_rdev));
    FILE*file=fopen(joy->database,"w");
    if(file){fputs("I:1\nE:ID_INPUT=1\nE:ID_INPUT_JOYSTICK=1\nE:ID_VENDOR_ID=1209\nE:ID_MODEL_ID=d590\nE:ID_SERIAL=DS2Port_Virtual_Joypad\n",file);fclose(file);}
    break;
   }
   closedir(directory);
  }
 }
 joy_reset(joy);fprintf(stderr,"JOYPAD_READY name=DS2Port 4 Button Joypad\n");return 0;
fail:
 close(fd);joy->fd=-1;return -1;
}
static void joy_close(VirtualJoypad*joy){
 if(joy->fd<0)return;
 joy_reset(joy);ioctl(joy->fd,UI_DEV_DESTROY);close(joy->fd);joy->fd=-1;
 if(joy->database[0])unlink(joy->database);
}
#endif

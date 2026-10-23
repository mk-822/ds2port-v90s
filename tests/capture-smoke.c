#include "frame_capture.h"
#include <stdio.h>
int main(int argc,char **argv) {
    if(argc!=2) return 1;
    Display *display=XOpenDisplay(NULL);if(!display)return 2;
    FrameCapture capture;
    capture_open(&capture,display,strcmp(argv[1],"ximage")!=0);
    int expected=strcmp(argv[1],"shm")==0;
    if(capture.shared!=expected){fprintf(stderr,"Unexpected capture backend\n");return 3;}
    for(int i=0;i<64;i++){
        XImage *image=capture_read(&capture);
        if(!image||image->width!=640||image->height!=480)return 4;
        capture_release(&capture);
    }
    capture_close(&capture);capture_close(&capture);
    XCloseDisplay(display);
    printf("CAPTURE_OK mode=%s frames=64\n",argv[1]);
    return 0;
}

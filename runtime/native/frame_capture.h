#ifndef DS2PORT_FRAME_CAPTURE_H
#define DS2PORT_FRAME_CAPTURE_H
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XShm.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    Display *display;
    XImage *image;
    XShmSegmentInfo segment;
    int attached;
    int shared;
} FrameCapture;

static int capture_error;
static int capture_x_error(Display *display, XErrorEvent *event) {
    (void)display; (void)event;
    capture_error = 1;
    return 0;
}

static void capture_close(FrameCapture *capture) {
    if (capture->attached) {
        XShmDetach(capture->display, &capture->segment);
        XSync(capture->display, False);
    }
    if (capture->image) {
        if (capture->shared) capture->image->data = NULL;
        XDestroyImage(capture->image);
    }
    if (capture->segment.shmaddr && capture->segment.shmaddr != (char *)-1)
        shmdt(capture->segment.shmaddr);
    capture->segment.shmaddr = NULL;
    capture->image = NULL;
    capture->attached = capture->shared = 0;
}

static void capture_open(FrameCapture *capture, Display *display, int allow_shared) {
    memset(capture, 0, sizeof(*capture));
    capture->display = display;
    capture->segment.shmid = -1;
    if (!allow_shared || !XShmQueryExtension(display)) return;
    capture->image = XShmCreateImage(display, DefaultVisual(display, DefaultScreen(display)),
        DefaultDepth(display, DefaultScreen(display)), ZPixmap, NULL, &capture->segment, 640, 480);
    if (!capture->image) return;
    capture->shared = 1;
    capture->segment.shmid = shmget(IPC_PRIVATE,
        capture->image->bytes_per_line * capture->image->height, IPC_CREAT | 0600);
    if (capture->segment.shmid < 0) { capture_close(capture); return; }
    capture->segment.shmaddr = shmat(capture->segment.shmid, NULL, 0);
    if (capture->segment.shmaddr == (char *)-1) {
        shmctl(capture->segment.shmid, IPC_RMID, NULL);
        capture_close(capture); return;
    }
    capture->image->data = capture->segment.shmaddr;
    capture->segment.readOnly = False;
    XSync(display, False);
    capture_error = 0;
    int (*previous)(Display *, XErrorEvent *) = XSetErrorHandler(capture_x_error);
    int attached = XShmAttach(display, &capture->segment);
    XSync(display, False);
    capture->attached = attached && !capture_error;
    if (capture->attached) {
        if (!XShmGetImage(display, DefaultRootWindow(display), capture->image, 0, 0, AllPlanes))
            capture_error = 1;
        XSync(display, False);
    }
    XSetErrorHandler(previous);
    shmctl(capture->segment.shmid, IPC_RMID, NULL);
    if (!capture->attached || capture_error) capture_close(capture);
}

static XImage *capture_read(FrameCapture *capture) {
    if (capture->shared) {
        if (XShmGetImage(capture->display, DefaultRootWindow(capture->display),
                        capture->image, 0, 0, AllPlanes)) return capture->image;
        capture_close(capture);
    }
    capture->image = XGetImage(capture->display, DefaultRootWindow(capture->display),
                              0, 0, 640, 480, AllPlanes, ZPixmap);
    return capture->image;
}

static void capture_release(FrameCapture *capture) {
    if (!capture->shared && capture->image) {
        XDestroyImage(capture->image);
        capture->image = NULL;
    }
}
#endif

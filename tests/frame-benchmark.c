#define _POSIX_C_SOURCE 200809L
#include "frame_capture.h"
#include <linux/fb.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdint.h>
#include <time.h>

static double now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}
static void delay(double seconds) {
    if (seconds <= 0) return;
    struct timespec t = {(time_t)seconds, (long)((seconds - (time_t)seconds) * 1e9)};
    nanosleep(&t, NULL);
}
int main(int argc, char **argv) {
    int shared = argc > 1 && !strcmp(argv[1], "shm");
    int legacy = argc > 2 && !strcmp(argv[2], "legacy");
    Display *d = XOpenDisplay(NULL); if (!d) return 1;
    int f = open("/dev/fb0", O_RDWR);
    struct fb_var_screeninfo v; struct fb_fix_screeninfo fi;
    if (f < 0 || ioctl(f, FBIOGET_VSCREENINFO, &v) || ioctl(f, FBIOGET_FSCREENINFO, &fi)) return 2;
    unsigned char *fb = mmap(NULL, fi.smem_len, PROT_READ|PROT_WRITE, MAP_SHARED, f, 0);
    if (fb == MAP_FAILED || v.bits_per_pixel != 32) return 3;
    FrameCapture capture; capture_open(&capture, d, shared);
    double start = now(), read_ms = 0, copy_ms = 0;
    unsigned frames = 0;
    while (now() - start < 8.0) {
        double begin = now();
        XImage *i = capture_read(&capture);
        double got = now(); if (!i || i->bits_per_pixel != 32) return 4;
        uint32_t alpha = v.transp.length ? ((1u << v.transp.length) - 1) << v.transp.offset : 0;
        for (int y = 0; y < 480; y++) {
            uint32_t *out = (uint32_t *)(fb + (y + v.yoffset) * fi.line_length + v.xoffset * 4);
            uint32_t *in = (uint32_t *)(i->data + y * i->bytes_per_line);
            if (legacy) {
                memcpy(out, in, 640 * 4);
                if (alpha) for (int x = 0; x < 640; x++) out[x] |= alpha;
            } else {
                for (int x = 0; x < 640; x++) out[x] = in[x] | alpha;
            }
        }
        double copied = now();
        read_ms += (got - begin) * 1000; copy_ms += (copied - got) * 1000;
        capture_release(&capture); frames++;
        if (legacy) delay(.033);
        else delay(1.0 / 60 - (now() - begin));
    }
    double duration = now() - start;
    printf("mode=%s pacing=%s fps=%.2f read_ms=%.3f copy_ms=%.3f frames=%u seconds=%.3f\n",
           capture.shared ? "shm" : "ximage", legacy ? "legacy" : "60hz",
           frames / duration, read_ms / frames, copy_ms / frames, frames, duration);
    capture_close(&capture); munmap(fb, fi.smem_len); close(f); XCloseDisplay(d);
}

#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdio.h>
int main(void) {
    EGLDisplay d = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major, minor;
    if (!eglInitialize(d, &major, &minor)) { printf("EGL_INIT_ERROR=0x%x\n",eglGetError()); return 1; }
    printf("EGL=%d.%d VENDOR=%s\n",major,minor,eglQueryString(d,EGL_VENDOR));
    printf("EGL_EXTENSIONS=%s\n",eglQueryString(d,EGL_EXTENSIONS));
    EGLint attributes[] = {EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_NONE};
    EGLConfig config; EGLint count;
    if (!eglChooseConfig(d,attributes,&config,1,&count) || !count) return 2;
    EGLint size[] = {EGL_WIDTH,640,EGL_HEIGHT,480,EGL_NONE};
    EGLSurface surface=eglCreatePbufferSurface(d,config,size);
    EGLint version[] = {EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE};
    eglBindAPI(EGL_OPENGL_ES_API);
    EGLContext context=eglCreateContext(d,config,EGL_NO_CONTEXT,version);
    if (!eglMakeCurrent(d,surface,surface,context)) {printf("EGL_CONTEXT_ERROR=0x%x\n",eglGetError());return 3;}
    printf("GL_VENDOR=%s GL_RENDERER=%s GL_VERSION=%s\n",glGetString(GL_VENDOR),glGetString(GL_RENDERER),glGetString(GL_VERSION));
    glClearColor(.25,.5,.75,1);glClear(GL_COLOR_BUFFER_BIT);
    unsigned char pixel[4];glReadPixels(0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
    printf("PIXEL=%u,%u,%u,%u GL_ERROR=0x%x\n",pixel[0],pixel[1],pixel[2],pixel[3],glGetError());
    eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(d,context);eglDestroySurface(d,surface);eglTerminate(d);
    return 0;
}

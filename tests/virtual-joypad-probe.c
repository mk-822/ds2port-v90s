#include "virtual_joypad.h"
#include <stdlib.h>
int main(int argc,char**argv){
 VirtualJoypad joy;if(joy_open(&joy)<0){perror("joy_open");return 1;}
 fflush(stderr);
 for(int i=0;i<(argc>1?atoi(argv[1]):60);i++)sleep(1);
 joy_close(&joy);return 0;
}

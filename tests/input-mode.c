#include <assert.h>
#include <stdio.h>
#include "input_mode.h"
static unsigned long event_sym[128];static int event_down[128],count;
static void record(void*context,unsigned long sym,int down){
 assert(context==event_sym);assert(count<128);
 event_sym[count]=sym;event_down[count++]=down;
}
static void update(BridgeKeys*k,InputMode mode,int x,int y,unsigned faces,int start,int select){
 bridge_keys_update(k,mode,x,y,faces,start,select,record,event_sym);
}
int main(void){
 assert(input_mode_parse("keyboard")==INPUT_KEYBOARD);
 assert(input_mode_parse("joypad")==INPUT_JOYPAD);
 assert(input_mode_parse(NULL)==INPUT_MOUSE);
 assert(input_mode_next(INPUT_MOUSE,1)==INPUT_JOYPAD);
 assert(input_mode_next(INPUT_JOYPAD,1)==INPUT_KEYBOARD);
 assert(input_mode_next(INPUT_KEYBOARD,1)==INPUT_MOUSE);
 assert(input_mode_next(INPUT_MOUSE,0)==INPUT_KEYBOARD);
 BridgeKeys keys={0};
 update(&keys,INPUT_KEYBOARD,-1,-1,15,1,1);
 assert(count==7);
 assert(event_sym[0]==XK_Left&&event_sym[1]==XK_Up);
 assert(event_sym[2]==XK_z&&event_sym[3]==XK_x&&event_sym[4]==XK_c);
 assert(event_sym[5]==XK_Escape&&event_sym[6]==XK_Return);
 for(int i=0;i<count;i++)assert(event_down[i]==1);
 update(&keys,INPUT_KEYBOARD,-1,-1,15,1,1);assert(count==7);
 update(&keys,INPUT_KEYBOARD,1,1,15,1,1);assert(count==11);
 assert(event_sym[7]==XK_Left&&event_down[7]==0);
 assert(event_sym[8]==XK_Up&&event_down[8]==0);
 assert(event_sym[9]==XK_Right&&event_down[9]==1);
 assert(event_sym[10]==XK_Down&&event_down[10]==1);
 /* SELECT keeps Escape held after X is released, and vice versa. */
 update(&keys,INPUT_KEYBOARD,1,1,7,1,1);assert(count==11);
 update(&keys,INPUT_KEYBOARD,1,1,15,1,0);assert(count==11);
 update(&keys,INPUT_KEYBOARD,1,1,7,1,0);assert(count==12);
 assert(event_sym[11]==XK_Escape&&event_down[11]==0);
 /* Switching mode releases keyboard-only keys, while START is still Enter. */
 update(&keys,INPUT_JOYPAD,1,1,15,1,0);assert(count==17);
 assert(keys.held==(1u<<8));
 update(&keys,INPUT_MOUSE,1,1,15,1,1);assert(count==18);
 assert(event_sym[17]==XK_Escape&&event_down[17]==1);
 /* The same reset is used for power-menu resume and bridge shutdown. */
 update(&keys,INPUT_MOUSE,0,0,0,0,0);assert(count==20&&keys.held==0);
 update(&keys,INPUT_KEYBOARD,0,0,0,0,0);assert(count==20);
 puts("INPUT_MODES_AND_RELEASES_OK");return 0;
}

#ifndef DS2PORT_INPUT_MODE_H
#define DS2PORT_INPUT_MODE_H
#include <string.h>
#include <X11/keysym.h>

typedef enum {INPUT_MOUSE,INPUT_JOYPAD,INPUT_KEYBOARD} InputMode;
static InputMode input_mode_parse(const char*text){
 return text&&!strcmp(text,"keyboard")?INPUT_KEYBOARD:
        text&&!strcmp(text,"joypad")?INPUT_JOYPAD:INPUT_MOUSE;
}
static const char*input_mode_name(InputMode mode){
 return mode==INPUT_KEYBOARD?"keyboard":mode==INPUT_JOYPAD?"joypad":"mouse";
}
static InputMode input_mode_next(InputMode mode,int joy_available){
 if(mode==INPUT_KEYBOARD)return INPUT_MOUSE;
 if(mode==INPUT_JOYPAD||!joy_available)return INPUT_KEYBOARD;
 return INPUT_JOYPAD;
}

typedef struct {unsigned held;} BridgeKeys;
typedef void (*BridgeKeySink)(void*context,unsigned long sym,int down);
static void bridge_keys_update(BridgeKeys*keys,InputMode mode,int dx,int dy,
 unsigned faces,int start,int select,BridgeKeySink sink,void*context){
 static const unsigned long symbols[]={XK_Left,XK_Right,XK_Up,XK_Down,
  XK_z,XK_x,XK_c,XK_Escape,XK_Return};
 unsigned wanted=(select?1u<<7:0)|(start?1u<<8:0);
 if(mode==INPUT_KEYBOARD){
  if(dx<0)wanted|=1u<<0;if(dx>0)wanted|=1u<<1;
  if(dy<0)wanted|=1u<<2;if(dy>0)wanted|=1u<<3;
  wanted|=(faces&7)<<4;
  if(faces&8)wanted|=1u<<7;
 }
 /* X and SELECT both send Escape: releasing either source must not release
  * the key while the other is still held. Release old directions first. */
 for(unsigned i=0;i<sizeof(symbols)/sizeof(symbols[0]);i++)
  if((keys->held&~wanted)&(1u<<i))sink(context,symbols[i],0);
 for(unsigned i=0;i<sizeof(symbols)/sizeof(symbols[0]);i++)
  if((wanted&~keys->held)&(1u<<i))sink(context,symbols[i],1);
 keys->held=wanted;
}
#endif

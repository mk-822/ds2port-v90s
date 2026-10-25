#ifndef DS2PORT_MODE_BANNER_H
#define DS2PORT_MODE_BANNER_H
#include <stdint.h>
#include <linux/fb.h>
#include <string.h>
#include "input_mode.h"
static const unsigned char*banner_glyph(char c){
 static const struct {char c;unsigned char rows[7];} font[]={
  {'A',{14,17,17,31,17,17,17}},{'D',{30,17,17,17,17,17,30}},
  {'E',{31,16,16,30,16,16,31}},{'J',{7,2,2,2,18,18,12}},
  {'M',{17,27,21,21,17,17,17}},{'O',{14,17,17,17,17,17,14}},
  {'P',{30,17,17,30,16,16,16}},{'S',{15,16,16,14,1,1,30}},
  {'U',{17,17,17,17,17,17,14}},{'Y',{17,17,10,4,4,4,4}},
  {'B',{30,17,17,30,17,17,30}},{'K',{17,18,20,24,20,18,17}},
  {'R',{30,17,17,30,20,18,17}},
  {' ',{0,0,0,0,0,0,0}}
 };
 for(unsigned i=0;i<sizeof(font)/sizeof(font[0]);i++)if(font[i].c==c)return font[i].rows;
 return font[sizeof(font)/sizeof(font[0])-1].rows;
}
static void mode_banner(unsigned char*fb,const struct fb_fix_screeninfo*fi,
 const struct fb_var_screeninfo*v,unsigned page,InputMode mode,int y){
 if(v->bits_per_pixel!=32||y<=-34)return;
 const char*text=mode==INPUT_KEYBOARD?"KEYBOARD MODE":mode==INPUT_JOYPAD?"JOYPAD MODE":"MOUSE MODE";
 int width=(int)strlen(text)*11+11;
 uint32_t alpha=v->transp.length?((1u<<v->transp.length)-1)<<v->transp.offset:0;
 uint32_t background=alpha|(0xAAu<<v->green.offset)|(0xF0u<<v->blue.offset),ink=alpha;
 for(int row=0;row<34;row++){
  int screen_y=y+row;if(screen_y<0||screen_y>=(int)v->yres)continue;
  uint32_t*out=(uint32_t*)(fb+(screen_y+page)*fi->line_length+v->xoffset*4);
  for(int x=0;x<width&&x<(int)v->xres;x++)out[x]=background;
 }
 for(int n=0;text[n];n++){
  const unsigned char*glyph=banner_glyph(text[n]);
  for(int row=0;row<7;row++)for(int col=0;col<5;col++)if(glyph[row]&(1<<(4-col))){
   for(int sy=0;sy<2;sy++){
    int screen_y=y+10+row*2+sy;if(screen_y<0||screen_y>=(int)v->yres)continue;
    uint32_t*out=(uint32_t*)(fb+(screen_y+page)*fi->line_length+v->xoffset*4);
    int x=6+n*11+col*2;if(x+1<(int)v->xres){out[x]=ink;out[x+1]=ink;}
   }
  }
 }
}
#endif

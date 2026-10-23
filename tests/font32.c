#include <windows.h>
#include <stdio.h>
#include <string.h>
int main(void){
 const int widths[]={-8,-6,6,8,0};
 HDC dc=CreateCompatibleDC(NULL);BITMAPINFO bi={0};void*pixels;
 bi.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);bi.bmiHeader.biWidth=256;bi.bmiHeader.biHeight=-64;
 bi.bmiHeader.biPlanes=1;bi.bmiHeader.biBitCount=32;bi.bmiHeader.biCompression=BI_RGB;
 HBITMAP bitmap=CreateDIBSection(dc,&bi,DIB_RGB_COLORS,&pixels,NULL,0);SelectObject(dc,bitmap);
 SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(0,0,0));
 for(int face=0;face<2;face++)for(int i=0;i<5;i++){
  HFONT font=CreateFontA(-16,widths[i],0,0,600,0,0,0,SHIFTJIS_CHARSET,0,0,0,1,face?"MS Gothic":NULL);
  HGDIOBJ old=SelectObject(dc,font);TEXTMETRICA tm={0};SIZE extent={0};char name[128]={0};
  GetTextMetricsA(dc,&tm);GetTextFaceA(dc,sizeof(name),name);
  const char digits[]="\x82\x4f\x82\x50\x82\x51\x82\x52";
  GetTextExtentPoint32A(dc,digits,8,&extent);memset(pixels,255,256*64*4);
  int ok=TextOutA(dc,0,0,digits,8);GdiFlush();int count=0;
  for(int p=0;p<256*64;p++)if((((DWORD*)pixels)[p]&0xffffff)!=0xffffff)count++;
  printf("FONT face=%s request=%d actual=%s height=%ld avg=%ld max=%ld extent=%ld pixels=%d textout=%d\n",face?"MS Gothic":"default",widths[i],name,tm.tmHeight,tm.tmAveCharWidth,tm.tmMaxCharWidth,extent.cx,count,ok);
  SelectObject(dc,old);DeleteObject(font);
 }
 fflush(stdout);DeleteDC(dc);DeleteObject(bitmap);return 0;
}

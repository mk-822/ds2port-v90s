#include <windows.h>
#include <stdio.h>
#include <stdint.h>
static uint32_t data[65536];
int main(void){
 LARGE_INTEGER start,end,freq;QueryPerformanceFrequency(&freq);
 uint32_t state=0x12345678;for(unsigned i=0;i<65536;i++){state=state*1664525u+1013904223u;data[i]=state;}
 QueryPerformanceCounter(&start);
 for(unsigned i=0;i<30000000;i++){
  unsigned index=state&65535;uint32_t x=data[index];
  state=(state*1664525u+1013904223u)^((x<<7)|(x>>25));
  data[index]=state+x+(i^(i>>9));
 }
 QueryPerformanceCounter(&end);
 uint32_t sum=state;for(unsigned i=0;i<65536;i++)sum^=data[i];
 printf("DYNAREC_BENCH milliseconds=%.3f checksum=%08x\n",1000.0*(end.QuadPart-start.QuadPart)/freq.QuadPart,sum);
 return 0;
}

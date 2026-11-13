#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "ar_engine.h"
static unsigned char ram[0x400000];
static int rd(void*u,uint32_t a,void*o,size_t n){a&=0x3FFFFF;memcpy(o,ram+a,n);return 1;}
static int wr(void*u,uint32_t a,const void*i,size_t n){a&=0x3FFFFF;memcpy(ram+a,i,n);return 1;}
static uint32_t r32(uint32_t a){uint32_t v;memcpy(&v,ram+(a&0x3FFFFF),4);return v;}
static uint16_t r16(uint32_t a){uint16_t v;memcpy(&v,ram+(a&0x3FFFFF),2);return v;}
int main(){ArMem m={0,rd,wr};
 ArOp gold[]={{0x020F6D48,0x0098967F}}; ar_run(&m,gold,1,0); assert(r32(0x020F6D48)==9999999);
 // hp: max 0 -> nothing; max 123 -> hp=123
 ArOp hp[]={{0xA20F5510,0},{0xDA000000,0x020F5510},{0xD7000000,0x020F550C},{0xD2000000,0}};
 ar_run(&m,hp,4,0); assert(r16(0x020F550C)==0);
 uint16_t mx=123; memcpy(ram+0xF5510,&mx,2); ar_run(&m,hp,4,0); assert(r16(0x020F550C)==123);
 // loop: 4 companions spaced 0x964
 ArOp sp[]={{0xC0000000,3},{0x120F3DB0,0x1F4},{0xDC000000,0x964},{0xD2000000,0}};
 ar_run(&m,sp,4,AR_KEYS_ALL); for(int i=0;i<4;i++) assert(r16(0x020F3DB0+i*0x964)==500); assert(r16(0x020F3DB0+4*0x964)==0);
 // alchemy loop: 0x1D7 entries, data 5,9,...
 ArOp al[]={{0xD5000000,5},{0xC0000000,0x1D6},{0xD7000000,0x020FAE9C},{0xD4000000,4},{0xD2000000,0}};
 ar_run(&m,al,5,AR_KEYS_ALL); assert(r16(0x020FAE9C)==5); assert(r16(0x020FAE9E)==9); assert(r16(0x020FAE9C+2*0x1D6)==(uint16_t)(5+4*0x1D6)); assert(r16(0x020FAE9C+2*0x1D7)==0);
memset(ram+0xF59DC,0,2);
 // key condition: off when not pressed, on when fired
 ArOp k[]={{0x94000130,0xFFFB0000},{0x120F59DC,0x1F4},{0xD2000000,0}};
 ar_run(&m,k,3,0); assert(r16(0x020F59DC)==0); ar_run(&m,k,3,1<<3); assert(r16(0x020F59DC)==0);
 ar_run(&m,k,3,1<<2); assert(r16(0x020F59DC)==500); memset(ram+0xF59DC,0,2); ar_run(&m,k,3,AR_KEYS_ALL); assert(r16(0x020F59DC)==500);
 // X / Y through the copy of the key register in RAM: Y is bit 11
 ArOp y[]={{0x927FFFA8,0xF7FF0000},{0x220F59E0,0x7},{0xD2000000,0}};
 ar_run(&m,y,3,1<<10); assert(ram[0xF59E0]==0); ar_run(&m,y,3,1<<11); assert(ram[0xF59E0]==7);
 // a loop count gone wrong stops instead of freezing the frame
 ArOp inf[]={{0xC0000000,0xFFFFFFFF},{0x020F0020,1},{0xD2000000,0},{0x020F0024,2}};
 ar_run(&m,inf,4,0); assert(r32(0x020F0020)==1);
 // nested failing cond then D0 then unconditional write
 ArOp n[]={{0x520F0000,1},{0x020F0010,7},{0xD0000000,0},{0x020F0014,8}};
 ar_run(&m,n,4,0); assert(r32(0x020F0010)==0 && r32(0x020F0014)==8);
 // E code: bulk write little-endian words
 ArOp e[]={{0xE20F5FB0,6},{0x4A6B4A6A,0x00004A6C}};
 ar_run(&m,e,2,0); assert(r16(0x020F5FB0)==0x4A6A&&r16(0x020F5FB2)==0x4A6B&&r16(0x020F5FB4)==0x4A6C);
 // B pointer + offset write
 uint32_t p=0x02100000; memcpy(ram+0x1000,&p,4);
 ArOp b[]={{0xB2001000,0},{0x00000010,0x55},{0xD2000000,0},{0x02000020,0x66}};
 ar_run(&m,b,4,0); assert(r32(0x02100010)==0x55 && r32(0x02000020)==0x66);
 puts("all engine tests pass");}

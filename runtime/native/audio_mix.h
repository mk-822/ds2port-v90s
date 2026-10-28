#ifndef DS2PORT_MIX_SHARED_H
#define DS2PORT_MIX_SHARED_H
#include <stdint.h>
#include <stdatomic.h>
#define MIX_CAPACITY 16384
#define MIX_PERIOD 480
#define MIX_CLIENTS 8
#define MIX_MAGIC 0x4453324d
typedef struct {
 uint32_t magic;
 // Client owns active/reset/write; mixer owns alive/ack/read. Samples are
 // published before write advances and reused only after read advances.
 // A reset is acknowledged after the mixer discards the old queued frames.
 _Atomic uint32_t alive,active,reset,ack;
 _Atomic uint64_t write,read;
 int16_t samples[MIX_CAPACITY][2];
} mix_shared;
#endif

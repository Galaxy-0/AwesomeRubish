// Native replay -> Metal -> byte-exact shared-memory observation. No assets.
#include <assert.h>
#include "../upstream/dm/gfx/nvn/nvn_mtl.m"
int prog_key(const prog_t *p,unsigned stage,uint8_t key[8]) {(void)p;(void)stage;memset(key,0,8);return 0;}
void *front_metal_layer(void) {return NULL;}
module_t *module_of(const void *p) {(void)p;return NULL;}
module_t g_mod[MAX_MOD];int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) {return bp_now();}
int dm_rl_active(void) {return 0;}
int dm_rl_match_phase(void) {return 0;}
uint64_t dm_nvn_frame_count(void) {return 0;}
uint64_t nvn_new_serial(void) {static uint64_t serial;return ++serial;}
static uint8_t commands[65536] __attribute__((aligned(8)));
static size_t used;
static unsigned checks;
static void emit_update(uint8_t *memory,size_t offset,const uint8_t *bytes,size_t count) {
    size_t size=(24+count+7)&~(size_t)7;assert(used+size<sizeof commands);
    op_hdr h={OP_UPDATE_UB,(uint32_t)size};uint64_t address=(uint64_t)(memory+offset),n=count;
    memcpy(commands+used,&h,8);memcpy(commands+used+8,&address,8);memcpy(commands+used+16,&n,8);
    memcpy(commands+used+24,bytes,count);used+=size;
}
static void emit_copy(uint8_t *memory,size_t src,size_t dst,size_t n) {
    op_hdr h={OP_COPY_B2B,32};uint64_t data[]={(uint64_t)(memory+src),(uint64_t)(memory+dst),n};
    memcpy(commands+used,&h,8);memcpy(commands+used+8,data,24);used+=32;
}
static void execute(uint8_t *memory,uint8_t *expected,size_t length) {
    op_hdr end={OP_END,8};memcpy(commands+used,&end,8);used+=8;
    mtl_sub_begin();mtl_exec(commands);
    // Recycled command memory cannot change delayed GPU data.
    memset(commands,0xee,used);
    if(!mtl_wait(mtl_sub_commit(),5000000000ull) || memcmp(memory,expected,length)) {
        for(size_t n=0;n<length;n++)if(memory[n]!=expected[n]){fprintf(stderr,"byte %zu: got %u expected %u\n",n,memory[n],expected[n]);break;}
        abort();
    }
    checks++;used=0;
}
int main(void) {@autoreleasepool {
    setenv("DM_HEADLESS","1",1);setenv("DM_FPS","0",1);
    const size_t length=131072;uint8_t *memory=aligned_alloc(4096,length),*expected=malloc(length);
    assert(memory && expected);mtl_init();mtl_pool_add(memory,length);
    uint8_t payload[8192];for(size_t n=0;n<sizeof payload;n++)payload[n]=(uint8_t)(n*37+3);
    // Gaps, overlap, reverse order, the batch capacity, and an observer between
    // update groups must preserve bytes and original last-write ordering.
    const size_t offsets[]={0,16,24,32,96,104,108,112,40,8,4096,12288};
    const size_t sizes[]={16,4,8,64,8,4,4,16,32,24,8192,0};
    memset(memory,0xa5,length);memcpy(expected,memory,length);
    for(unsigned n=0;n<sizeof offsets/sizeof(*offsets);n++) {
        emit_update(memory,offsets[n],payload,sizes[n]);memcpy(expected+offsets[n],payload,sizes[n]);
        if(n==7){emit_copy(memory,0,65536,256);memcpy(expected+65536,expected,256);}
    }
    execute(memory,expected,length);
    uint32_t random=0x83751u;
    for(unsigned trial=0;trial<100;trial++) {
        memset(memory,trial,length);memcpy(expected,memory,length);
        for(unsigned n=0;n<40;n++) {
            random=random*1664525u+1013904223u;size_t offset=(random>>8)%8000;
            random=random*1664525u+1013904223u;size_t size=(random>>8)%128;
            if(n%4==0)offset=256+n*32;
            emit_update(memory,offset,payload+n,size);memcpy(expected+offset,payload+n,size);
            if(n==19){emit_copy(memory,0,65536,8192);memcpy(expected+65536,expected,8192);}
        }
        execute(memory,expected,length);
    }
    mtl_pool_del(memory);
    // Adjacent guest addresses may belong to distinct NVN pools/Metal buffers.
    mtl_pool_add(memory,4096);mtl_pool_add(memory+4096,4096);
    memset(memory,0xa5,length);memcpy(expected,memory,length);
    emit_update(memory,4092,payload,4);memcpy(expected+4092,payload,4);
    emit_update(memory,4096,payload+4,4);memcpy(expected+4096,payload+4,4);
    execute(memory,expected,length);
    mtl_pool_del(memory+4096);mtl_pool_del(memory);
    printf("{\"passed\":true,\"submissions\":%u,\"checked_bytes\":%zu}\n",checks,length*checks);
    free(memory);free(expected);return 0;
}}

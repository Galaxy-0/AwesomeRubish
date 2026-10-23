/* Passive actor lifecycle entry gates. No game calls or writes. */
static void truth_lifecycle(const uint64_t *r,int kind){
    if(!demo_capture_enabled() || !getenv("DM_TEST_DEMO_TRUTH") || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    uintptr_t p=r[0],vt=0,params=0;
    if(!d2b_read(p,&vt,8))return;uintptr_t off=vt-d2b_base;
    if(off!=0x5c79398 && off!=0x5c75510 && off!=0x5c76df0 && off!=0x5c74bf8)return;
    float pos[3]={0},vel[3]={0};int linger=0;
    int ok=d2b_read(p+0x110,pos,12)&&d2b_read(p+0x1130,vel,12);
    d2b_read(p+0x1b0,&linger,4);d2b_read(p+0x108,&params,8);
    LOG("DEMO_TRUTH_LIFE frame=%llu event=%d object=%p vtable=%llx valid=%d position=%.9g,%.9g,%.9g velocity=%.9g,%.9g,%.9g linger=%d params=%p readonly=1",dm_guest_frame(),kind,(void*)p,(unsigned long long)off,ok,pos[0],pos[1],pos[2],vel[0],vel[1],vel[2],linger,(void*)params);
    if(kind==0 || kind==3){demo_hex("lifecycle_params",params,0x200,dm_guest_frame());demo_hex("lifecycle_actor",p,0x300,dm_guest_frame());}
}
static void truth_life_reset(const uint64_t *r){truth_lifecycle(r,0);}
static void truth_life_destroy(const uint64_t *r){truth_lifecycle(r,1);}
static void truth_life_tick(const uint64_t *r){truth_lifecycle(r,2);}
static void truth_life_release(const uint64_t *r){truth_lifecycle(r,3);}

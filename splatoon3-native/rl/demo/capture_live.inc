/* Passive held-out confirmation. All names retain candidate/validity tags. */
static void demo_live_update(uintptr_t player,int slot,int health){
    if(!demo_capture_enabled() || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    static uint64_t last=UINT64_MAX;uint64_t f=dm_guest_frame();if(f==last)return;last=f;
    float a[3]={0},b[3]={0};int ok=d2b_read(player+0x170,a,12)&&d2b_read(player+0x1ac,b,12);
    uintptr_t clock=0;uint32_t tick=0;int tv=d2b_read(d2b_base+0x6001130,&clock,8)&&d2b_read(clock,&tick,4);
    for(unsigned j=0;j<demo_object_n;j++){
        uintptr_t vt=0,owner=0;uint32_t state=UINT32_MAX,elapsed=UINT32_MAX,duration=UINT32_MAX;
        if(!d2b_read(demo_objects[j],&vt,8))continue;int type=demo_object_type(vt);
        if(type!=3 && type!=4)continue;
        if(!d2b_read(demo_objects[j]+(type==3?0x198:0x408),&owner,8)||owner!=player)continue;
        d2b_read(demo_objects[j]+0x38,&state,4);d2b_read(demo_objects[j]+0xe4,&elapsed,4);d2b_read(demo_objects[j]+0xe8,&duration,4);
        LOG("DEMO_NATIVE_LIVE frame=%llu slot=%d type=%d object=%p pose_valid=%d p170=%.9g,%.9g,%.9g p1ac=%.9g,%.9g,%.9g hp_native=%d state38=%u countere4=%u duratione8=%u tick_valid=%d tick=%u readonly=1",f,slot,type,(void*)demo_objects[j],ok,a[0],a[1],a[2],b[0],b[1],b[2],health,state,elapsed,duration,tv,tick);
    }
}

/* Native truth candidates. Private controlled fixture, read-only telemetry.
 * A tracked address is NOT an active projectile until lifecycle is qualified. */
static uintptr_t truth_bullets[128];static unsigned truth_bullet_n;
static void truth_projectile(uintptr_t p,uintptr_t off){
    if(!demo_capture_enabled() || !getenv("DM_TEST_DEMO_TRUTH"))return;
    unsigned j;for(j=0;j<truth_bullet_n;j++)if(truth_bullets[j]==p)break;
    if(j==truth_bullet_n && truth_bullet_n<128){truth_bullets[truth_bullet_n++]=p;demo_hex("bullet_birth_candidate",p,0x1000,dm_guest_frame());}
    (void)off;
}
static void truth_update(uintptr_t player,int slot){
    if(!demo_capture_enabled() || !getenv("DM_TEST_DEMO_TRUTH") || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    static uint64_t last=UINT64_MAX;uint64_t f=dm_guest_frame();if(last==f)return;last=f;
    for(unsigned j=0;j<demo_object_n;j++){
        uintptr_t vt=0,owner=0;if(!d2b_read(demo_objects[j],&vt,8))continue;int type=demo_object_type(vt);
        if(type!=3 && type!=4)continue;
        if(!d2b_read(demo_objects[j]+(type==3?0x198:0x408),&owner,8)||owner!=player)continue;
        float cost=0,elapsed=0;uint32_t state=0,duration=0;
        d2b_read(demo_objects[j]+0x38,&state,4);d2b_read(demo_objects[j]+0xe0,&cost,4);d2b_read(demo_objects[j]+0xe4,&elapsed,4);d2b_read(demo_objects[j]+0xe8,&duration,4);
        LOG("DEMO_TRUTH_ACTION frame=%llu slot=%d type=%d object=%p state=%u cost=%.9g elapsed=%.9g duration=%u readonly=1",f,slot,type,(void*)demo_objects[j],state,cost,elapsed,duration);
        if(f%8==0)demo_hex(type==3?"truth_saber":"truth_shooter",demo_objects[j],0x1000,f);
    }
    for(unsigned j=0;j<truth_bullet_n;j++){
        uintptr_t p=truth_bullets[j],vt=0;if(!d2b_read(p,&vt,8))continue;
        float pos[3]={0},vel[3]={0};uint32_t phase=0;
        d2b_read(p+0x110,pos,12);d2b_read(p+0x1130,vel,12);d2b_read(p+0x1238,&phase,4);
        LOG("DEMO_TRUTH_BULLET frame=%llu object=%p vtable=%llx phase=%u position_candidate=%.9g,%.9g,%.9g velocity=%.9g,%.9g,%.9g readonly=1",f,(void*)p,(unsigned long long)(vt-d2b_base),phase,pos[0],pos[1],pos[2],vel[0],vel[1],vel[2]);
        if(f%8==0){demo_hex("bullet_head_candidate",p,0x300,f);demo_hex("bullet_tail_candidate",p+0x1000,0x270,f);}
    }
}

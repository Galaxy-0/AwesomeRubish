/* Demo-only passive scalar/snapshot survey. Unknown fields remain candidates.
 * 11.3.0. No game calls, no register edits, no guest writes. Private logs only. */
static uintptr_t demo_objects[16];
static unsigned demo_object_n;
static uint64_t demo_scan_frame, demo_native_frame=UINT64_MAX, demo_native_base=UINT64_MAX;
static int demo_capture_enabled(void){const char *s=getenv("DM_DEMO_NATIVE_CAPTURE");return s && !strcmp(s,"1") && getenv("DM_TEST_DEMO") && !strcmp(getenv("DM_TEST_DEMO"),"1");}
static void demo_hex(const char *kind,uintptr_t p,size_t count,uint64_t frame){
    unsigned char raw[0x1000];char hex[0x2001];const char *digits="0123456789abcdef";
    if(count>sizeof raw || !d2b_read(p,raw,count))return;
    for(size_t j=0;j<count;j++){hex[2*j]=digits[raw[j]>>4];hex[2*j+1]=digits[raw[j]&15];}hex[2*count]=0;
    LOG("DEMO_NATIVE_RAW frame=%llu kind=%s object=%p size=%zu data=%s readonly=1",frame,kind,(void *)p,count,hex);
}
static int demo_object_type(uintptr_t vt){
    uintptr_t off=vt-d2b_base;
    return off==0x5d7ea88?1:off==0x5d80370?2:off==0x5d34d70?3:off==0x5d35760?4:0;
}
static void demo_native_update(uintptr_t player,int slot,int health){
    if(!demo_capture_enabled() || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    uint64_t f=dm_guest_frame();if(f==demo_native_frame)return;demo_native_frame=f;
    if(demo_native_base==UINT64_MAX)demo_native_base=f;
    uintptr_t engine=0;float position[3]={0};
    d2b_read(player+0x10,&engine,8);int ok=d2b_read(engine+0x25c,position,12);
    if(ok)LOG("DEMO_NATIVE_POSE frame=%llu slot=%d health=%d engine_position_candidate=%.9g,%.9g,%.9g readonly=1",f,slot,health,position[0],position[1],position[2]);
    if(f-demo_native_base<800 && f%8==0){demo_hex("player",player,0x400,f);demo_hex("engine",engine,0x300,f);}
    if((!demo_scan_frame || f>=demo_scan_frame+120) && f-demo_native_base<1200 && demo_object_n<16){
        demo_scan_frame=f;mach_vm_address_t start=player;mach_vm_size_t length=0;
        vm_region_basic_info_data_64_t info;mach_msg_type_number_t count=VM_REGION_BASIC_INFO_COUNT_64;mach_port_t port=0;
        kern_return_t kr=mach_vm_region(mach_task_self(),&start,&length,VM_REGION_BASIC_INFO_64,(vm_region_info_t)&info,&count,&port);
        if(port)mach_port_deallocate(mach_task_self(),port);
        if(kr==KERN_SUCCESS && start<=player && (info.protection&VM_PROT_READ)){
            uintptr_t lo=player>0x4000000?player-0x4000000:0,hi=player+0x4000000;
            if(lo<start)lo=start;if(hi>start+length)hi=start+length;lo=(lo+7)&~(uintptr_t)7;
            for(uintptr_t p=lo;p+8<=hi && demo_object_n<16;p+=8){
                uintptr_t vt;memcpy(&vt,(void *)p,8);int type=demo_object_type(vt);if(!type)continue;
                int known=0;for(unsigned j=0;j<demo_object_n;j++)if(demo_objects[j]==p)known=1;
                if(!known && a6_special_region(p,type<=2?0x720:0x1000,0)){demo_objects[demo_object_n++]=p;LOG("DEMO_NATIVE_OBJECT frame=%llu type=%d object=%p vtable=%llx readonly=1",f,type,(void*)p,(unsigned long long)(vt-d2b_base));}
            }
        }
    }
    if(f%4)return;
    for(unsigned j=0;j<demo_object_n;j++){
        uintptr_t vt=0;if(!d2b_read(demo_objects[j],&vt,8))continue;int type=demo_object_type(vt);if(!type)continue;
        demo_hex(type==1?"weapon_saber":type==2?"weapon_shooter":type==3?"action_saber":"action_shooter",demo_objects[j],type<=2?0x720:0x1000,f);
    }
}
static void demo_native_projectile(uintptr_t object,uintptr_t off){
    if(!demo_capture_enabled())return;
    uint32_t state=UINT32_MAX;d2b_read(object+0x1238,&state,4);
    LOG("DEMO_NATIVE_PROJECTILE frame=%llu object=%p vtable=%llx phase1238_candidate=%u readonly=1",dm_guest_frame(),(void*)object,(unsigned long long)off,state);
}

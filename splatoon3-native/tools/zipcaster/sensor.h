/* D2B test derivative only. Read native memory at registered live calls.
 * No game/guest-register writes, no policy fields, no dynamic code calls.
 * Build identity: Splatoon3 11.3.0, 28c4287aee36f7499da60f3e68b54c70.
 */
static uintptr_t d2b_base;
static unsigned long long d2b_hook_last[8],d2b_damage_last;
static int d2b_enabled;
static uintptr_t d2b_own_hook;
static uint64_t d2b_scan_last;
static int d2b_read(uintptr_t p,void *out,size_t n) {
    if(!p || !a6_special_region(p,n,0))return 0;
    memcpy(out,(const void *)p,n);return 1;
}
static int d2b_slot(uintptr_t player) {
    uintptr_t storage=0,info=0;int slot=-1;
    if(!d2b_read(player+0x108,&storage,8) || !d2b_read(storage+8,&info,8) ||
       !d2b_read(info+0x7e8,&slot,4))return -1;
    return slot>=0 && slot<8?slot:-1;
}
static void d2b_hex(const char *kind,uintptr_t object,int slot,size_t size) {
    uint8_t bytes[0x3b18];char hex[0x3b18*2+1];const char *digits="0123456789abcdef";
    if(size>sizeof bytes || !d2b_read(object,bytes,size))return;
    for(size_t i=0;i<size;i++){hex[2*i]=digits[bytes[i]>>4];hex[2*i+1]=digits[bytes[i]&15];}hex[2*size]=0;
    LOG("D2B_SNAPSHOT frame=%llu kind=%s object=%p slot=%d size=%zu data=%s",
        dm_guest_frame(),kind,(void *)object,slot,size,hex);
}
static uintptr_t d2b_find_hook(uintptr_t player,int slot) {
    uintptr_t vt=0,owner=0;
    if(d2b_read(d2b_own_hook,&vt,8) && vt==d2b_base+0x5d3e588 &&
       d2b_read(d2b_own_hook+0x3af0,&owner,8) && owner==player)return d2b_own_hook;
    uint64_t frame=dm_guest_frame();if(frame<d2b_scan_last+120)return 0;d2b_scan_last=frame;
    mach_vm_address_t start=player;mach_vm_size_t length=0;
    vm_region_basic_info_data_64_t info;mach_msg_type_number_t count=VM_REGION_BASIC_INFO_COUNT_64;mach_port_t object=0;
    kern_return_t status=mach_vm_region(mach_task_self(),&start,&length,VM_REGION_BASIC_INFO_64,(vm_region_info_t)&info,&count,&object);
    if(object)mach_port_deallocate(mach_task_self(),object);
    if(status!=KERN_SUCCESS || start>player || !(info.protection&VM_PROT_READ))return 0;
    uintptr_t lo=player>0x2000000?player-0x2000000:0,hi=player+0x2000000;
    if(lo<start)lo=start;if(hi>start+length)hi=start+length;lo=(lo+7)&~(uintptr_t)7;
    for(uintptr_t p=lo;p+8<=hi;p+=8){
        uint64_t value;memcpy(&value,(const void *)p,8);
        if(value!=d2b_base+0x5d3e588 || !d2b_read(p+0x3af0,&owner,8) || owner!=player ||
           !a6_special_region(p,0x3b18,0))continue;
        d2b_own_hook=p;LOG("D2B_DISCOVERY frame=%llu method=vtable_and_owner slot=%d player=%p object=%p scanned=%llu",
            frame,slot,(void *)player,(void *)p,(unsigned long long)(hi-lo));return p;
    }
    LOG("D2B_DISCOVERY frame=%llu method=vtable_and_owner slot=%d found=0 scanned=%llu",frame,slot,(unsigned long long)(hi-lo));return 0;
}
static void d2b_hook(const uint64_t *r) {
    if(!d2b_enabled || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    uintptr_t object=r[0],vtable=0,player=0;
    if(!d2b_read(object,&vtable,8) || vtable!=d2b_base+0x5d3e588 ||
       !d2b_read(object+0x3af0,&player,8))return;
    int slot=d2b_slot(player);
    if(slot<0 || !rl_self_seen || slot!=rl_self_slot)return;
    uint64_t frame=dm_guest_frame();if(frame<d2b_hook_last[slot]+4)return;
    d2b_hook_last[slot]=frame;d2b_hex("superhook",object,slot,0x3b18);
}
static void d2b_weapon(const uint64_t *r) {
    static uint64_t last[8];static uintptr_t objects[8];
    if(!d2b_enabled || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    uintptr_t object=r[0],vt=0;if(!d2b_read(object,&vt,8) || vt!=d2b_base+0x5d86220)return;
    for(int i=0;i<8;i++)if(!objects[i] || objects[i]==object){
        objects[i]=object;uint64_t frame=dm_guest_frame();if(frame<last[i]+4)return;
        last[i]=frame;d2b_hex("weapon",object,-1,0x5c0);return;
    }
}
static void d2b_damage(uintptr_t object,int slot) {
    if(!d2b_enabled || !dm_rl_active())return;
    uint64_t frame=dm_guest_frame();if(frame<d2b_damage_last+4)return;
    d2b_damage_last=frame;d2b_hex("damage",object,slot,0xf08);
    uintptr_t player=0,storage=0,key_pointer=0;uint32_t key=0,remaining=0;
    if(!d2b_read(object+0xf00,&player,8))return;
    uintptr_t hook=d2b_find_hook(player,slot);
    if(hook && frame>=d2b_hook_last[slot]+4){d2b_hook_last[slot]=frame;d2b_hex("superhook",hook,slot,0x3b18);}
    if(hook){
        uintptr_t actor=0,weapon=0,bullet=0;
        if(d2b_read(hook+0x88,&actor,8) && actor)d2b_hex("surface_matrix",actor+0xd8,slot,0x30);
        if(d2b_read(hook+0x80,&weapon,8) && weapon){
            d2b_hex("hook_weapon",weapon,slot,0x5c0);
            if(d2b_read(weapon+0x5b8,&bullet,8) && bullet)d2b_hex("hook_bullet",bullet,slot,0x600);
        }
        for(unsigned offset=0x3ac0;offset<=0x3ae8;offset+=8){
            uintptr_t component=0;char kind[32];snprintf(kind,sizeof kind,"component_%x",offset);
            if(d2b_read(hook+offset,&component,8) && component)d2b_hex(kind,component,slot,0x400);
        }
    }
    d2b_hex("player",player,slot,0x400);
    if(d2b_read(player+0x108,&storage,8))d2b_hex("storage",storage,slot,0x3000);
    uintptr_t component=0;
    if(d2b_read(storage+0x11cc0,&component,8) && component)d2b_hex("component_11cc0",component,slot,0x300);
    if(d2b_read(d2b_base+0x6001130,&key_pointer,8) && d2b_read(key_pointer,&key,4) &&
       d2b_read(storage+0xd18,&remaining,4))LOG("D2B_CANONICAL frame=%llu slot=%d key=%u remaining=%d",frame,slot,key,(int32_t)(remaining^key));
}
static void d2b_init(void) {
    const char *mode=getenv("DM_D2B_SENSOR");if(!mode || strcmp(mode,"1"))return;
    if(strcmp(dm_main_build(),"28c4287aee36f7499da60f3e68b54c70"))die("D2B unsupported build");
    if(!gate_obs_present(46) || !gate_obs_present(47))die("D2B private observation gates missing");
    for(int i=0;i<g_nmod;i++)if(!strcmp(g_mod[i].name,"main"))d2b_base=(uintptr_t)g_mod[i].base;
    if(!d2b_base)die("D2B no main base");
    d2b_enabled=1;gate_obs_set(46,d2b_hook);gate_obs_set(47,d2b_weapon);
    LOG("D2B_SENSOR readonly=1 main=%p hook_vtable=5d3e588 weapon_vtable=5d86220 sample_stride=4",(void *)d2b_base);
}

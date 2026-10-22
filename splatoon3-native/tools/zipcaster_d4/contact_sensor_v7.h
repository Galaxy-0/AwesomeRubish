/* D4 corrected read-only component/physics capture. No d8-matrix assumption.
 * Build 28c4287aee36f7499da60f3e68b54c70; same unique SaberSlash calc gate51.
 */
static int d4_contact_enabled;
static void d4_contact(const uint64_t *r) {
    if(!d4_contact_enabled || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    uintptr_t object=r[0],vt=0,params=0,component=0,body=0,box=0,cylinder=0;
    if(!d2b_read(object,&vt,8) || vt!=d2b_base+0x5c76738)return;
    float position[3];
    if(!d2b_read(object+0x110,position,sizeof position))return;
    if(!d2b_read(object+0x108,&params,8) || !d2b_read(object+0x138,&component,8) ||
       !d2b_read(object+0x198,&body,8) || !d2b_read(object+0x1a0,&box,8) ||
       !d2b_read(object+0x1a8,&cylinder,8))return;
    LOG("D4_CONTACT2 frame=%llu object=%p p110=%.9g,%.9g,%.9g params=%p component=%p body=%p box=%p cylinder=%p readonly=1",
        dm_guest_frame(),(void *)object,position[0],position[1],position[2],
        (void *)params,(void *)component,(void *)body,(void *)box,(void *)cylinder);
    d2b_hex("d4_slash",object,rl_self_slot,0x1130);
    d2b_hex("d4_params",params,rl_self_slot,0x90);
    uintptr_t engine=0,physics_owner=0;
    if(d2b_read(object+0x10,&engine,8))d2b_hex("d4_engine",engine,rl_self_slot,0x1000);
    if(d2b_read(body+0x20,&physics_owner,8))d2b_hex("d4_physics_owner",physics_owner,rl_self_slot,0x600);
    uintptr_t damage=0;
    if(d2b_read(object+0x158,&damage,8))d2b_hex("d4_damage",damage,rl_self_slot,0x800);
    d2b_hex("d4_component",component,rl_self_slot,0x400);
    d2b_hex("d4_body",body,rl_self_slot,0x400);
    d2b_hex("d4_box",box,rl_self_slot,0x200);
    d2b_hex("d4_cylinder",cylinder,rl_self_slot,0x200);
    uintptr_t entries=0;uint32_t count=0;
    if(d2b_read(body+0xb8,&count,4) && d2b_read(body+0xc0,&entries,8) && count>0 && count<=16){
        char kind[48];size_t n=count<4?count:4;
        d2b_hex("d4_leaf_entries",entries,rl_self_slot,n*0x80);
        for(size_t i=0;i<n;i++){
            uintptr_t leaf=0;
            if(d2b_read(entries+i*0x80,&leaf,8)){
                snprintf(kind,sizeof kind,"d4_leaf_%zu",i);d2b_hex(kind,leaf,rl_self_slot,0x800);
            }
        }
    }
    d2b_hex("d4_calc_argument",r[1],rl_self_slot,0x100);

}
static void d4_contact_transform(const uint64_t *r) {
    if(!d4_contact_enabled || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    float p[3];
    if(!d2b_read(r[1],p,sizeof p))return;
    /* Predeclared bounded diagnostic volume around the blocked contact birth.
     * Read only; no position/rotation/register changes. Other native bodies in
     * this volume are retained, not automatically attributed to SaberSlash. */
    if(p[0]<-12.f || p[0]>-3.f || p[1]<2.f || p[1]>8.f || p[2]<-7.f || p[2]>3.f)return;
    LOG("D4_TRANSFORM frame=%llu destination=%p source=%p rotation=%p lr=%llx p=%.9g,%.9g,%.9g readonly=1",
        dm_guest_frame(),(void *)r[0],(void *)r[1],(void *)r[2],(unsigned long long)r[30],p[0],p[1],p[2]);
    d2b_hex("d4_transform_source",r[1],rl_self_slot,12);
    d2b_hex("d4_transform_rotation",r[2],rl_self_slot,36);
    d2b_hex("d4_transform_destination",r[0],rl_self_slot,0x100);
}
static uintptr_t d4_life_damage(uintptr_t life) {
    uintptr_t vt=0;
    if(life<0x30 || !d2b_read(life-0x30,&vt,8) || vt!=d2b_base+0x5d32218)return 0;
    return life-0x30;
}
static int d4_damage_slot(uintptr_t damage) {
    uintptr_t player=0;
    return d2b_read(damage+0xf00,&player,8)?d2b_slot(player):-1;
}
static int d4_research_active(void) {
    return d4_contact_enabled && dm_rl_active() && atomic_load(&rl_phase)==1;
}
static void d4_candidate_return(const uint64_t *r) {
    if(!d4_research_active())return;
    uintptr_t vt=0;if(!d2b_read(r[20],&vt,8) || vt!=d2b_base+0x5c76738)return;
    uintptr_t candidate_vt=0;d2b_read(r[19],&candidate_vt,8);
    LOG("D4_FILTER_RETURN frame=%llu actor=%p candidate=%p candidate_vtable=%llx candidate_slot=%d result=%llu readonly=1",
        dm_guest_frame(),(void *)r[20],(void *)r[19],(unsigned long long)(candidate_vt-d2b_base),d2b_slot(r[19]),(unsigned long long)r[0]);
    d2b_hex("d4_filter_candidate",r[19],rl_self_slot,0x200);
}
static void d4_register_attack(const uint64_t *r) {
    if(!d4_research_active())return;
    uintptr_t actor=0,vt=0;
    if(!d2b_read(r[0]+0x30,&actor,8) || !d2b_read(actor,&vt,8) || vt!=d2b_base+0x5c76738)return;
    LOG("D4_REGISTER_ATTACK frame=%llu actor=%p component=%p candidate=%p readonly=1",dm_guest_frame(),(void *)actor,(void *)r[0],(void *)r[1]);
    d2b_hex("d4_registration_params",r[3],rl_self_slot,0x40);
}
static void d4_receive_candidate(const uint64_t *r) {
    if(!d4_research_active())return;
    uintptr_t vt=0,life=0;
    if(!d2b_read(r[1],&vt,8) || (vt!=d2b_base+0x5c76738 && vt!=d2b_base+0x5c76df0 && vt!=d2b_base+0x5c75510))return;
    if(!d2b_read(r[0]+0x4f0,&life,8))return;
    uintptr_t damage=d4_life_damage(life);if(!damage)return;
    int slot=d4_damage_slot(damage);if(slot<0)return;
    LOG("D4_RECEIVE_CANDIDATE frame=%llu receiver=%p actor=%p actor_vtable=%llx life=%p slot=%d readonly=1",
        dm_guest_frame(),(void *)r[0],(void *)r[1],(unsigned long long)(vt-d2b_base),(void *)life,slot);
    d2b_hex("d4_receive_actor",r[1],slot,0x200);
    d2b_hex("d4_receive_component",r[0],slot,0x580);
}
static void d4_submit_damage(const uint64_t *r) {
    if(!d4_research_active())return;
    uintptr_t damage=d4_life_damage(r[0]);if(!damage)return;
    int slot=d4_damage_slot(damage);int32_t amount=0,hp=0,pending=0;
    if(slot<0 || !d2b_read(r[1],&amount,4) || !d2b_read(r[0]+0x58,&hp,4) || !d2b_read(r[0]+0x60,&pending,4))return;
    LOG("D4_DAMAGE_SUBMIT frame=%llu life=%p slot=%d amount=%d apply=%llu hp=%d pending=%d readonly=1",
        dm_guest_frame(),(void *)r[0],slot,amount,(unsigned long long)(r[2]&1),hp,pending);
    d2b_hex("d4_damage_submission",r[1],slot,0xc8);
}
static void d4_damage_state(uintptr_t damage) {
    if(!d4_research_active())return;
    int slot=d4_damage_slot(damage);if(slot<0)return;
    static int last_hp[8],last_pending[8],seen[8];int hp=0,pending=0;
    if(!d2b_read(damage+0x88,&hp,4) || !d2b_read(damage+0x90,&pending,4))return;
    if(!seen[slot] || hp!=last_hp[slot] || pending!=last_pending[slot]){
        LOG("D4_LIFE_STATE frame=%llu slot=%d hp=%d pending=%d readonly=1",dm_guest_frame(),slot,hp,pending);
        last_hp[slot]=hp;last_pending[slot]=pending;seen[slot]=1;
    }
}

/* Ordered per-ball query lifetimes, sampled around the game's shared
 * truncation routine. Arrays are named by offset until their native roles
 * are proved. No registers, input, physics state or game memory are changed. */
static void d4_half_state(uintptr_t actor,const char *stage) {
    if(!d4_research_active())return;
    uintptr_t vt=0;if(!d2b_read(actor,&vt,8) || (vt!=d2b_base+0x5c76df0 && vt!=d2b_base+0x5c75510))return;
    float p[3]={0};d2b_read(actor+0x110,p,sizeof p);
    LOG("D4_HALF_ROOT frame=%llu stage=%s actor=%p vtable=%llx p=%.9g,%.9g,%.9g readonly=1",dm_guest_frame(),stage,(void *)actor,(unsigned long long)(vt-d2b_base),p[0],p[1],p[2]);
    for(size_t array=0;array<2;array++)for(size_t j=0;j<7;j++){
        uintptr_t q=0,child=0,qvt=0,cvt=0;uint32_t state=0;uint8_t dead=0,flag=0;
        if(!d2b_read(actor+(array?0x1280:0x1200)+j*8,&q,8))continue;
        if(q){d2b_read(q,&qvt,8);d2b_read(q+0xe4,&state,4);d2b_read(q+0xe8,&dead,1);d2b_read(q+0x90,&child,8);
            if(child){d2b_read(child,&cvt,8);d2b_read(child+0x1218,&flag,1);}}
        LOG("D4_HALF_QUERY frame=%llu stage=%s actor=%p array=%zx index=%zu query=%p qvtable=%llx state=%u dead=%u child=%p cvtable=%llx child_flag=%u readonly=1",dm_guest_frame(),stage,(void *)actor,array?0x1280UL:0x1200UL,j,(void *)q,(unsigned long long)(qvt-d2b_base),state,dead,(void *)child,(unsigned long long)(cvt-d2b_base),flag);
    }
}
static void d4_half_before(const uint64_t *r){d4_half_state(r[0],"before");}
static void d4_half_after(const uint64_t *r){d4_half_state(r[19],"after");}
static void d4_contact_physics_stage(const uint64_t *r) {
    if(!d4_research_active())return;
    uintptr_t vt=0,body=0,interface=0;
    if(!d2b_read(r[0],&vt,8)||vt!=d2b_base+0x5c76738)return;
    LOG("D4_CONTACT_PHYSICS_STAGE frame=%llu actor=%p readonly=1",dm_guest_frame(),(void *)r[0]);
    d2b_hex("d4_physics_stage_actor",r[0],rl_self_slot,0x200);
    if(d2b_read(r[0]+0x198,&body,8)&&d2b_read(body+0x58,&interface,8))d2b_hex("d4_body_interface",interface,rl_self_slot,0x400);
}

static void d4_contact_init(void) {
    const char *flag=getenv("DM_D4_CONTACT_SENSOR");
    if(!flag || !*flag)return;
    if(strcmp(flag,"1") || !d3r_enabled ||
       strcmp(dm_main_build(),"28c4287aee36f7499da60f3e68b54c70") ||
       (!gate_obs_present(51) || !gate_obs_present(52) || !gate_obs_present(53) || !gate_obs_present(54) || !gate_obs_present(55) || !gate_obs_present(56) || !gate_obs_present(57) || !gate_obs_present(58) || !gate_obs_present(59)))die("D4 contact sensor requires isolated direct-aim fixture and private51gate");
    d4_contact_enabled=1;gate_obs_set(51,d4_contact);gate_obs_set(52,d4_contact_transform);gate_obs_set(53,d4_candidate_return);gate_obs_set(54,d4_receive_candidate);gate_obs_set(55,d4_submit_damage);gate_obs_set(56,d4_register_attack);gate_obs_set(57,d4_half_before);gate_obs_set(58,d4_half_after);gate_obs_set(59,d4_contact_physics_stage);
    LOG("D4_CONTACT_SENSOR enabled=1 readonly=1 version=7 actor_vtable=5c76738 slot=51");
}

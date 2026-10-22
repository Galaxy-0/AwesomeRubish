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
}
static void d4_contact_init(void) {
    const char *flag=getenv("DM_D4_CONTACT_SENSOR");
    if(!flag || !*flag)return;
    if(strcmp(flag,"1") || !d3r_enabled ||
       strcmp(dm_main_build(),"28c4287aee36f7499da60f3e68b54c70") ||
       !gate_obs_present(51))die("D4 contact sensor requires isolated direct-aim fixture and private51gate");
    d4_contact_enabled=1;gate_obs_set(51,d4_contact);
    LOG("D4_CONTACT_SENSOR enabled=1 readonly=1 version=4 actor_vtable=5c76738 slot=51");
}

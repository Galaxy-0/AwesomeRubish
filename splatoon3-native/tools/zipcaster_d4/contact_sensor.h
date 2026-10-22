/* D4 isolated measurement derivative. Read live SaberSlash actor only.
 * Build 28c4287aee36f7499da60f3e68b54c70, RTTI and size getter checked offline.
 * Does not alter matrices, shape parameters, HP, lifetime or guest registers.
 */
static int d4_contact_enabled;
static void d4_contact(const uint64_t *r) {
    if(!d4_contact_enabled || !dm_rl_active() || atomic_load(&rl_phase)!=1)return;
    uintptr_t object=r[0],vt=0;
    if(!d2b_read(object,&vt,8) || vt!=d2b_base+0x5c76738)return;
    float matrix[12],position[3];
    if(!d2b_read(object+0xd8,matrix,sizeof matrix) ||
       !d2b_read(object+0x110,position,sizeof position))return;
    for(int i=0;i<12;i++)if(!isfinite(matrix[i]))return;
    LOG("D4_CONTACT frame=%llu object=%p vtable=5c76738 p110=%.9g,%.9g,%.9g matrix=%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g readonly=1",
        dm_guest_frame(),(void *)object,position[0],position[1],position[2],
        matrix[0],matrix[1],matrix[2],matrix[3],matrix[4],matrix[5],matrix[6],matrix[7],matrix[8],matrix[9],matrix[10],matrix[11]);
    d2b_hex("d4_slash",object,rl_self_slot,0x1130);
}
static void d4_contact_init(void) {
    const char *flag=getenv("DM_D4_CONTACT_SENSOR");
    if(!flag || !*flag)return;
    if(strcmp(flag,"1") || !d3r_enabled ||
       strcmp(dm_main_build(),"28c4287aee36f7499da60f3e68b54c70") ||
       !gate_obs_present(51))die("D4 contact sensor requires isolated direct-aim fixture and private51gate");
    d4_contact_enabled=1;gate_obs_set(51,d4_contact);
    LOG("D4_CONTACT_SENSOR enabled=1 readonly=1 actor_vtable=5c76738 slot=51");
}

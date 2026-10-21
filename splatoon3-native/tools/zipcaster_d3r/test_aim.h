/* Private opt-in derivative. No default host or policy protocol changes.
 * Candidate canonical camera fields MUST be validated against emitted vectors.
 * Build 11.3.0 only; local PlayerCamera vtable+owner live checks on every use.
 */
#ifndef SPL3_D3R_TEST_AIM
#error D3R test aim must never be compiled into a normal host
#endif
static uintptr_t d3r_base,d3r_camera;
static int d3r_enabled,d3r_write,d3r_dump;
static uint64_t d3r_scan_frame;
static uint64_t d3r_sequence,d3r_command_frame,d3r_last=UINT64_MAX;
static float d3r_yaw,d3r_pitch;
static const char *d3r_file;
static int d3r_read(uintptr_t p,void *out,size_t n){
 if(!p||!a6_special_region(p,n,0))return 0;memcpy(out,(void*)p,n);return 1;
}
static uintptr_t d3r_find(uintptr_t player){
 uintptr_t vt=0,owner=0;
 if(d3r_read(d3r_camera,&vt,8)&&vt==d3r_base+0x5d31468&&d3r_read(d3r_camera+0x19c0,&owner,8)&&owner==player)return d3r_camera;
 uint64_t frame=dm_guest_frame();if(d3r_scan_frame&&frame<d3r_scan_frame+120)return 0;d3r_scan_frame=frame;
 mach_vm_address_t lo=player;mach_vm_size_t size=0;vm_region_basic_info_data_64_t info;mach_msg_type_number_t count=VM_REGION_BASIC_INFO_COUNT_64;mach_port_t object=0;
 kern_return_t status=mach_vm_region(mach_task_self(),&lo,&size,VM_REGION_BASIC_INFO_64,(vm_region_info_t)&info,&count,&object);
 if(object)mach_port_deallocate(mach_task_self(),object);
 if(status!=KERN_SUCCESS||lo>player||!(info.protection&VM_PROT_READ))return 0;
 uintptr_t begin=player>0x4000000?player-0x4000000:0,end=player+0x4000000;if(begin<lo)begin=lo;if(end>lo+size)end=lo+size;begin=(begin+7)&~(uintptr_t)7;
 for(uintptr_t p=begin;p+0x19d0<=end;p+=8){
  memcpy(&vt,(void*)p,8);if(vt!=d3r_base+0x5d31468)continue;memcpy(&owner,(void*)(p+0x19c0),8);
  if(owner==player&&a6_special_region(p,0x19d0,1)){d3r_camera=p;LOG("D3R_CAMERA frame=%llu player=%p object=%p owner_verified=1 vtable=5d31468",dm_guest_frame(),(void*)player,(void*)p);return p;}
 }
 return 0;
}
static void d3r_init(void){
 const char *flag=getenv("DM_TEST_AIM");d3r_file=getenv("DM_TEST_AIM_FILE");
 if((!flag||!*flag)&&(!d3r_file||!*d3r_file))return;
 if(!flag||strcmp(flag,"1")||!d3r_file||d3r_file[0]!='/'||!getenv("DM_RL_SOCKET")||strcmp(dm_main_build(),"28c4287aee36f7499da60f3e68b54c70"))die("DM_TEST_AIM requires explicit isolated 11.3.0 test host and absolute control path");
 for(int i=0;i<g_nmod;i++)if(!strcmp(g_mod[i].name,"main"))d3r_base=(uintptr_t)g_mod[i].base;
 if(!d3r_base)die("D3R missing main");if(!gate_obs_present(48)||!gate_obs_present(49)||!gate_obs_present(50))die("D3R private direction gates missing");d3r_enabled=1;d3r_dump=getenv("DM_D3R_DUMP")!=NULL;
 LOG("D3R_TEST_AIM enabled=1 test_only=1 candidate_fields=16c,18c no_position_or_hp_writes=1");
}
static void d3r_poll(uint64_t frame){
 FILE *f=fopen(d3r_file,"r");if(f){
  unsigned long long seq=0;int write=0;float yaw=0,pitch=0;char extra=0;
  int n=fscanf(f,"D3Rv1 %llu %d %f %f %c",&seq,&write,&yaw,&pitch,&extra);fclose(f);
  if(n!=4||!seq||(write!=0&&write!=1)||!isfinite(yaw)||fabsf(yaw)>3.141593f||!isfinite(pitch)||fabsf(pitch)>.9f)die("D3R invalid aim command");
  if(seq!=d3r_sequence){if(seq<d3r_sequence)die("D3R nonmonotone command");d3r_sequence=seq;d3r_command_frame=frame;d3r_write=write;d3r_yaw=yaw;d3r_pitch=pitch;LOG("D3R_COMMAND frame=%llu seq=%llu write=%d yaw=%.9g pitch=%.9g",frame,seq,write,yaw,pitch);}
 }
 if(d3r_write&&frame>d3r_command_frame+600)die("D3R expired enabled command");
}
static void d3r_camera_compute(const uint64_t *r){
 if(!d3r_enabled||!dm_rl_active()||atomic_load(&rl_phase)!=1||rl_self_health<=0)return;
 uintptr_t camera=r[0],owner=0,vt=0;if(camera!=d3r_camera||!d3r_read(camera,&vt,8)||vt!=d3r_base+0x5d31468||!d3r_read(camera+0x19c0,&owner,8)||player_slot(owner)!=rl_self_slot)return;
 uint64_t frame=dm_guest_frame();d3r_poll(frame);
 if(d3r_write){
  if(!a6_special_region(camera+0x16c,0x2c,1))die("D3R camera write region unavailable");
  float direction[3]={sinf(d3r_yaw),0,cosf(d3r_yaw)};
  memcpy((void*)(camera+0x18c),direction,12);memcpy((void*)(camera+0x16c),&d3r_pitch,4);
 }
 if(d3r_write)LOG("D3R_APPLY frame=%llu seq=%llu context=camera_compute yaw=%.9g pitch=%.9g",frame,d3r_sequence,d3r_yaw,d3r_pitch);
}
static void d3r_velocity(const uint64_t *r,int setter){
 if(!d3r_enabled||!dm_rl_active()||atomic_load(&rl_phase)!=1)return;
 uintptr_t p=r[0],vt=0;if(!d3r_read(p,&vt,8))return;
 uintptr_t off=vt-d3r_base;if(off!=0x5c79398&&off!=0x5c75510&&off!=0x5c76df0&&off!=0x5c74bf8)return;
 float v[3],pos[3];if(!d3r_read(setter?r[1]:p+0x1130,v,12)||!d3r_read(p+0x110,pos,12))return;
 if(!isfinite(v[0])||!isfinite(v[1])||!isfinite(v[2]))return;
 LOG("D3R_PROJECTILE frame=%llu kind=%s object=%p vtable=%llx velocity=%.9g,%.9g,%.9g p110=%.9g,%.9g,%.9g readonly=1",dm_guest_frame(),setter?"setter_input":"getter",(void*)p,(unsigned long long)off,v[0],v[1],v[2],pos[0],pos[1],pos[2]);
}
static void d3r_velocity_get(const uint64_t *r){d3r_velocity(r,0);}
static void d3r_velocity_set(const uint64_t *r){d3r_velocity(r,1);}
static void d3r_update(uintptr_t player,int slot,int health){
 if(!d3r_enabled||!dm_rl_active()||atomic_load(&rl_phase)!=1||health<=0)return;
 uint64_t frame=dm_guest_frame();if(frame==d3r_last)return;d3r_last=frame;
 d3r_poll(frame);
 uintptr_t camera=d3r_find(player);if(!camera){if(frame%60==0)LOG("D3R_CAMERA frame=%llu found=0",frame);return;}
 float horizontal[3],pitch=0;d3r_read(camera+0x18c,horizontal,12);d3r_read(camera+0x16c,&pitch,4);
 float norm=horizontal[0]*horizontal[0]+horizontal[2]*horizontal[2];
 if(!isfinite(norm)||fabsf(norm-1)>.03f||!isfinite(pitch)||fabsf(pitch)>1.1f)die("D3R camera state failed candidate range gate");

 float fields[3],eye[3],at[3],spin;d3r_read(camera+0x18c,fields,12);d3r_read(camera+0x17b8,eye,12);d3r_read(camera+0x17c4,at,12);d3r_read(camera+0x162c,&spin,4);
 LOG("D3R_STATE frame=%llu seq=%llu slot=%d write=%d pre_yaw=%.9g pre_pitch=%.9g yaw=%.9g pitch=%.9g v17b8=%.9g,%.9g,%.9g v17c4=%.9g,%.9g,%.9g spin162c=%.9g",frame,d3r_sequence,slot,d3r_write,atan2f(horizontal[0],horizontal[2]),pitch,atan2f(fields[0],fields[2]),pitch,eye[0],eye[1],eye[2],at[0],at[1],at[2],spin);
 if(d3r_dump&&frame%8==0){uint8_t bytes[0x19d0];char hex[0x33a1];const char *digits="0123456789abcdef";memcpy(bytes,(void*)camera,sizeof bytes);for(size_t i=0;i<sizeof bytes;i++){hex[2*i]=digits[bytes[i]>>4];hex[2*i+1]=digits[bytes[i]&15];}hex[sizeof hex-1]=0;LOG("D3R_CAMERA_RAW frame=%llu data=%s",frame,hex);}
}

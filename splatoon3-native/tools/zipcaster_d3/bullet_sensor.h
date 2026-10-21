/* D3 private read-only heap discovery. No native calls/writes/register edits.
 * 11.3.0 BulletShooterBase RTTI getter 1a27b8c, vtable 5c79398,
 * size getter 1a27b98 => 1270. Actor matrix at d8 is a hypothesis to validate.
 */
static uintptr_t d3_base,d3_objects[64];
static int d3_count,d3_enabled;
static uint64_t d3_last,d3_scan;
static float d3_prev[64][12];
static int d3_read(uintptr_t p,void *out,size_t n){if(!p||!a6_special_region(p,n,0))return 0;memcpy(out,(void*)p,n);return 1;}
static void d3_snapshot(uintptr_t object,int index,size_t n){
 uint8_t b[0x1270];char hex[0x24e1];const char *digits="0123456789abcdef";
 if(n>sizeof b||!d3_read(object,b,n))return;
 for(size_t j=0;j<n;j++){hex[2*j]=digits[b[j]>>4];hex[2*j+1]=digits[b[j]&15];}hex[2*n]=0;
 LOG("D3_BULLET frame=%llu readonly=1 index=%d object=%p size=%zu data=%s",dm_guest_frame(),index,(void*)object,n,hex);
}
static void d3_bullets(uintptr_t player){
 if(!d3_enabled||!dm_rl_active()||atomic_load(&rl_phase)!=1)return;
 uint64_t frame=dm_guest_frame();if(frame<d3_last+4)return;d3_last=frame;
 if(frame>=d3_scan+120&&d3_count<64){
  d3_scan=frame;mach_vm_address_t start=player;mach_vm_size_t length=0;vm_region_basic_info_data_64_t info;mach_msg_type_number_t count=VM_REGION_BASIC_INFO_COUNT_64;mach_port_t object=0;
  kern_return_t status=mach_vm_region(mach_task_self(),&start,&length,VM_REGION_BASIC_INFO_64,(vm_region_info_t)&info,&count,&object);
  if(object)mach_port_deallocate(mach_task_self(),object);
  if(status==KERN_SUCCESS&&start<=player&&(info.protection&VM_PROT_READ)){
   uintptr_t lo=player>0x2000000?player-0x2000000:0,hi=player+0x2000000;if(lo<start)lo=start;if(hi>start+length)hi=start+length;lo=(lo+7)&~(uintptr_t)7;
   int added=0;
   for(uintptr_t p=lo;p+8<=hi&&d3_count<64;p+=8){
    uintptr_t vt;memcpy(&vt,(void*)p,8);if(vt!=d3_base+0x5c79398||!a6_special_region(p,0x1270,0))continue;
    int known=0;for(int j=0;j<d3_count;j++)if(d3_objects[j]==p)known=1;
    if(!known){int index=d3_count++;d3_objects[index]=p;d3_snapshot(p,index,0x1270);added++;}
   }
   LOG("D3_DISCOVERY frame=%llu readonly=1 count=%d added=%d scanned=%llu",frame,d3_count,added,(unsigned long long)(hi-lo));
  }
 }
 for(int j=0;j<d3_count;j++){
  uintptr_t vt=0;float m[12];if(!d3_read(d3_objects[j],&vt,8)||vt!=d3_base+0x5c79398||!d3_read(d3_objects[j]+0xd8,m,sizeof m))continue;
  const char *capture=getenv("DM_D3_BULLET_CAPTURE");
  if(capture && !access(capture,F_OK))d3_snapshot(d3_objects[j],j,0x1270);
  else if(memcmp(m,d3_prev[j],sizeof m)){memcpy(d3_prev[j],m,sizeof m);d3_snapshot(d3_objects[j],j,0x200);}
 }
}
static void d3_init(void){
 const char *mode=getenv("DM_D3_BULLET");if(!mode||strcmp(mode,"1"))return;
 if(strcmp(dm_main_build(),"28c4287aee36f7499da60f3e68b54c70"))die("D3 unsupported build");
 for(int i=0;i<g_nmod;i++)if(!strcmp(g_mod[i].name,"main"))d3_base=(uintptr_t)g_mod[i].base;
 if(!d3_base)die("D3 missing main");d3_enabled=1;
 LOG("D3_SENSOR readonly=1 main=%p vtable=5c79398 size=1270 stride=4",(void*)d3_base);
}

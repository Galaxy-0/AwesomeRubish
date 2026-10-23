/* Appended to the existing isolated D3-R aim header in a fresh work build.
 * Camera reads are passive; DM_R0_CAMERA_PLUS5 separately selects the user's
 * requested maximum in a volatile native input copy. It never writes saves.
 */
static uintptr_t r0_options, r0_input;
static void r0_config_loaded(const uint64_t *r) {
 if(!d3r_enabled)return;
 uintptr_t object=r[19];int digital[2];unsigned char gyro=0;
 if(!d3r_read(object+0x70,digital,8)||!d3r_read(object+0x78,&gyro,1))return;
 if(abs(digital[0])>30||abs(digital[1])>30||gyro>1)return;
 r0_options=object;
 LOG("R0_OPTIONS frame=%llu object=%p stick_digital=%d gyro_digital=%d gyro_on=%u readonly=1",dm_guest_frame(),(void*)object,digital[0],digital[1],gyro);
}
static void r0_camera_state(void) {
 if(!d3r_enabled||!d3r_camera||dm_guest_frame()%8)return;
 /* Follow only guarded camera-owned references; no guest writes. */
 if(dm_guest_frame()%64==0){for(int slot=0;slot<2;slot++){uintptr_t object=0;const int offsets[2]={0x18,0x28};if(d3r_read(d3r_camera+offsets[slot],&object,8)&&a6_special_region(object,0x800,0)){unsigned char bytes[0x800];char hex[0x1001];const char *digits="0123456789abcdef";memcpy(bytes,(void*)object,sizeof bytes);for(int i=0;i<0x800;i++){hex[i*2]=digits[bytes[i]>>4];hex[i*2+1]=digits[bytes[i]&15];}hex[0x1000]=0;LOG("R0_CAMERA_REFERENCE frame=%llu offset=%x object=%p data=%s readonly=1",dm_guest_frame(),offsets[slot],(void*)object,hex);}}}
 float fov=0,eye[3],at[3];int digital[2]={-999,-999};unsigned char gyro=255;
 d3r_read(d3r_camera+0x17e4,&fov,4);d3r_read(d3r_camera+0x17b8,eye,12);d3r_read(d3r_camera+0x17c4,at,12);
 for(int slot=0;slot<2;slot++){uintptr_t object=0;if(d3r_read(d3r_camera+0x60+slot*8,&object,8)&&a6_special_region(object,0x200,0)){unsigned char bytes[0x200];char hex[0x401];const char *digits="0123456789abcdef";memcpy(bytes,(void*)object,sizeof bytes);for(int i=0;i<0x200;i++){hex[i*2]=digits[bytes[i]>>4];hex[i*2+1]=digits[bytes[i]&15];}hex[0x400]=0;LOG("R0_CAMERA_OBJECT frame=%llu slot=%d object=%p data=%s readonly=1",dm_guest_frame(),slot,(void*)object,hex);}}
 if(r0_input){float norm[2]={0,0};d3r_read(r0_input+0x5dc,norm,8);LOG("R0_INPUT_LIVE frame=%llu gyro_normalized=%.9g stick_normalized=%.9g",dm_guest_frame(),norm[0],norm[1]);}
 if(r0_options){d3r_read(r0_options+0x70,digital,8);d3r_read(r0_options+0x78,&gyro,1);}
 LOG("R0_CAMERA frame=%llu fov_candidate=%.9g eye=%.9g,%.9g,%.9g at=%.9g,%.9g,%.9g stick_digital=%d gyro_digital=%d gyro_on=%u readonly=1",dm_guest_frame(),fov,eye[0],eye[1],eye[2],at[0],at[1],at[2],digital[0],digital[1],gyro);
}
/* ControlOption temporary copy in the native input-controller initializer.
 * +6d0/+6d4 are digital0..20; native conversion (value-10)/10 is retained.
 * The optional max setting affects this process's volatile copy, not save data.
 */
static void r0_input_options(const uint64_t *r) {
 if(!d3r_enabled)return;
 uintptr_t input=r[19];int values[2];unsigned char gyro;r0_input=input;r0_options=input+0x660;
 if(!d3r_read(input+0x6d0,values,8)||!d3r_read(input+0x6d8,&gyro,1))return;
 if(values[0]<0||values[0]>20||values[1]<0||values[1]>20||gyro>1)die("R0 native option copy range guard");
 LOG("R0_INPUT_OPTIONS frame=%llu object=%p stick_digital=%d gyro_digital=%d gyro_on=%u before=1",dm_guest_frame(),(void*)input,values[0],values[1],gyro);
 const char *max=getenv("DM_R0_CAMERA_PLUS5");
 if(max){
  if(strcmp(max,"1")||!a6_special_region(input+0x6d0,9,1))die("R0 max sensitivity needs isolated test aim host");
  values[0]=20;values[1]=20;gyro=1;
  memcpy((void*)(input+0x6d0),values,8);memcpy((void*)(input+0x6d8),&gyro,1);
  LOG("R0_INPUT_OPTIONS frame=%llu object=%p stick_digital=20 gyro_digital=20 gyro_on=1 normalized_by_native=1 fixture_only=1 save_writes=0",dm_guest_frame(),(void*)input);
 }
}

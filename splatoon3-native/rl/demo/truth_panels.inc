/* Bounded read-only survey at ColPaintBuilder's native UV-map call boundary.
 * x22 is the PanelPtrArray (count at0, ptr buffer at8) in this exact build.
 * During stage construction, before controlled InGame. No native calls/writes. */
static void truth_panels(uintptr_t a,int after){
    if(!getenv("DM_TEST_DEMO_TRUTH") || !demo_capture_enabled())return;
    static unsigned passes; if(!after && ++passes>8)return;if(after && passes>8)return;
    uintptr_t buffer=0;int count=-1;
    if(!d2b_read(a,&count,4)||!d2b_read(a+8,&buffer,8)||count<0||count>50000)return;
    LOG("DEMO_TRUTH_PANELS frame=%llu pass=%u after=%d array=%p buffer=%p count=%d readonly=1",dm_guest_frame(),passes,after,(void*)a,(void*)buffer,count);
    for(int j=0;j<count && j<20000;j++){
        uintptr_t p=0,context=0;if(!d2b_read(buffer+j*8,&p,8))break;
        d2b_read(p+0x70,&context,8);
        LOG("DEMO_TRUTH_PANEL pass=%u after=%d index=%d object=%p context70=%p readonly=1",passes,after,j,(void*)p,(void*)context);
        demo_hex(after?"panel_after":"panel_before",p,0x180,dm_guest_frame());
        demo_hex(after?"panel_context_after":"panel_context_before",context,0x180,dm_guest_frame());
    }
}
static void truth_panels_before(const uint64_t *r){truth_panels(r[1],0);}
static void truth_panels_after(const uint64_t *r){truth_panels(r[22],1);}

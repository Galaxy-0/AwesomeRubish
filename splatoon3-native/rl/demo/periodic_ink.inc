/* Demo-only exact-frame ink capture, on the existing Metal4 submit queue.
 * Two in-flight images maximum. No GPU/CPU waits, no synchronous image encoder.
 * Buffers remain resident and busy until completion AND PNG serialization finish.
 */
static uint64_t demo_pi_frame=UINT64_MAX, demo_pi_base=UINT64_MAX;
static NSMutableArray *demo_pi_targets;
static int demo_pi_interval=-1;
static dispatch_queue_t demo_pi_io;
static _Atomic int demo_pi_busy[2];
static __strong id<MTLBuffer> demo_pi_buffers[2];
static int demo_pi_enabled(void){
    if(demo_pi_interval<0){
        const char *e=getenv("DM_DEMO_INK_EVERY"),*d=getenv("DM_TEST_DEMO");
        demo_pi_interval=e&&d&&!strcmp(d,"1")&&getenv("DM_DEMO_INK_DIR")?atoi(e):0;
        if(demo_pi_interval && (demo_pi_interval<15 || demo_pi_interval>3600))MDIE("demo ink period must be 15..3600");
        if(demo_pi_interval)demo_pi_io=dispatch_queue_create("demo-ink-png",DISPATCH_QUEUE_SERIAL);
    }
    return demo_pi_interval>0;
}
static void demo_pi_write(id<MTLBuffer> buffer,NSString *path,uint64_t frame,uint64_t serial,int slot){
    @autoreleasepool {
        uint64_t begin=clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
        NSMutableData *rgba=[NSMutableData dataWithLength:1600*1600*4];
        uint8_t *dst=rgba.mutableBytes;const uint8_t *src=buffer.contents;
        for(size_t i=0;i<1600*1600;i++){dst[4*i]=src[2*i];dst[4*i+1]=src[2*i+1];dst[4*i+2]=0;dst[4*i+3]=255;}
        CGColorSpaceRef cs=CGColorSpaceCreateDeviceRGB();
        CGDataProviderRef provider=CGDataProviderCreateWithCFData((__bridge CFDataRef)rgba);
        CGImageRef img=CGImageCreate(1600,1600,8,32,6400,cs,kCGImageAlphaLast,provider,NULL,false,kCGRenderingIntentDefault);
        NSString *tmp=[path stringByAppendingString:@".tmp"];
        CGImageDestinationRef target=CGImageDestinationCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:tmp],(__bridge CFStringRef)UTTypePNG.identifier,1,NULL);
        int ok=0;if(img && target){CGImageDestinationAddImage(target,img,NULL);ok=CGImageDestinationFinalize(target);}
        if(ok)ok=rename(tmp.UTF8String,path.UTF8String)==0;
        if(target)CFRelease(target);if(img)CGImageRelease(img);CGDataProviderRelease(provider);CGColorSpaceRelease(cs);
        MLOG("DEMO_INK_ASYNC frame=%llu target=%llu ok=%d bytes=5120000 io_ns=%llu path=%s",(unsigned long long)frame,(unsigned long long)serial,ok,(unsigned long long)(clock_gettime_nsec_np(CLOCK_UPTIME_RAW)-begin),path.UTF8String);
    }
    atomic_store(&demo_pi_busy[slot],0);
}
/* Before ANY command in the next frame: prior frame has been fully submitted.
 * Copy in the same queue before the next frame can change either atlas. */
static void demo_periodic_begin(void){
    if(!demo_pi_enabled())return;
    uint64_t f=atomic_load(&g_cur_frame);
    if(f==demo_pi_frame)return;
    uint64_t old=demo_pi_frame;demo_pi_frame=f;
    if(demo_pi_targets.count){
        for(NSArray *entry in demo_pi_targets){
            id<MTLTexture> texture=entry[0];uint64_t serial=[entry[1] unsignedLongLongValue];
            if(texture.pixelFormat!=MTLPixelFormatRG8Unorm || texture.textureType!=MTLTextureType2D)MDIE("unexpected demo ink format/type");
            int slot=-1;for(int i=0;i<2;i++){int expect=0;if(atomic_compare_exchange_strong(&demo_pi_busy[i],&expect,1)){slot=i;break;}}
            if(slot<0){MLOG("DEMO_INK_DROP frame=%llu target=%llu reason=busy",(unsigned long long)old,(unsigned long long)serial);continue;}
            if(!demo_pi_buffers[slot]){demo_pi_buffers[slot]=[g_dev newBufferWithLength:5120000 options:MTLResourceStorageModeShared];if(!demo_pi_buffers[slot])MDIE("demo ink allocation");res_add(demo_pi_buffers[slot]);}
            id<MTLBuffer> buffer=demo_pi_buffers[slot];
            id encoder=blit();
            enc_b_copy_texture_buffer(encoder,texture,0,0,MTLOriginMake(0,0,0),MTLSizeMake(1600,1600,1),buffer,0,3200,5120000);
            NSString *path=[NSString stringWithFormat:@"%s/frame-%llu-target-%llu.png",getenv("DM_DEMO_INK_DIR"),(unsigned long long)old,(unsigned long long)(serial*100)];
            /* Commit feedback executes only after the GPU's copy is complete. */
            [g_commit_blocks addObject:^{dispatch_async(demo_pi_io,^{demo_pi_write(buffer,path,old,serial,slot);});}];
        }
        [demo_pi_targets removeAllObjects];
    }
    if(demo_pi_base==UINT64_MAX && dm_rl_active() && dm_rl_match_phase()==1)demo_pi_base=f;
}
static void demo_periodic_note(MTL4RenderPassDescriptor *pd,NSUInteger nc){
    if(!demo_pi_enabled() || demo_pi_base==UINT64_MAX || !dm_rl_active() || dm_rl_match_phase()!=1)return;
    uint64_t f=atomic_load(&g_cur_frame);
    if((f-demo_pi_base)%(uint64_t)demo_pi_interval)return;
    if(!demo_pi_targets)demo_pi_targets=[NSMutableArray array];
    for(NSUInteger i=0;i<nc && i<8;i++){
        id<MTLTexture> texture=pd.colorAttachments[i].texture;
        if(!texture || texture.width!=1600 || texture.height!=1600)continue;
        uint64_t serial=i<(NSUInteger)R.rt.n && R.rt.color[i]?R.rt.color[i]->serial:0;
        BOOL found=NO;for(NSArray *entry in demo_pi_targets)if([entry[1] unsignedLongLongValue]==serial)found=YES;
        if(!found)[demo_pi_targets addObject:@[texture,@(serial)]];
    }
}

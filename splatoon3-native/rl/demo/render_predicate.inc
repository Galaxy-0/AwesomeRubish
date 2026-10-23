// Isolated human-demo renderer experiment. Never writes game state/predicates.
// Native reports/fences/visibility results still execute and publish normally.
extern int dm_rl_active(void) __attribute__((weak_import));
extern int dm_rl_match_phase(void) __attribute__((weak_import));
extern uint64_t dm_nvn_frame_count(void);
extern void dm_gfx_shot_at(long,const char *);
static void demo_pred_frame(uint64_t f){
    static const char *dir;static int checked;static uint64_t base=UINT64_MAX;
    if(!checked){checked=1;dir=getenv("DM_DEMO_SHOT_DIR");}
    if(!dir || !dm_rl_active || !dm_rl_match_phase || !dm_rl_active() || dm_rl_match_phase()!=1)return;
    if(base==UINT64_MAX)base=f;
    if(f-base==600 || f-base==1200){char path[4096];snprintf(path,sizeof path,"%s/frame-%llu.png",dir,f-base);dm_gfx_shot_at(0,path);}
}
typedef struct { uint64_t addr, a, b, fence; int valid; } demo_pred_entry;
static demo_pred_entry demo_pred_cache[4096];
static pthread_mutex_t demo_pred_mu=PTHREAD_MUTEX_INITIALIZER;
static uint64_t demo_pred_requests[2048];static unsigned demo_pred_n;
static uint64_t demo_pred_calls,demo_pred_hits,demo_pred_fallback,demo_pred_overflow;
static int demo_pred_mode=-1;
static unsigned demo_pred_hash(uint64_t addr){return (unsigned)(((addr>>4)*0x9e3779b97f4a7c15ull)>>52)&4095;}
static void demo_pred_begin(void){demo_pred_n=0;}
static uint64_t *demo_pred_take(unsigned *n){
    *n=demo_pred_n;if(!*n)return NULL;
    uint64_t *p=malloc(*n*sizeof *p);if(!p)MDIE("DEMO predicate requests allocation");
    memcpy(p,demo_pred_requests,*n*sizeof *p);demo_pred_n=0;return p;
}
static void demo_pred_publish(uint64_t *p,unsigned n,uint64_t fence){
    // Report destinations must remain alive until this queue completion (the
    // same lifetime as the original post_op writes immediately above us).
    // Read only payloads, never timestamp fields; reject older callback data.
    if(!n){free(p);return;}
    pthread_mutex_lock(&demo_pred_mu);
    for(unsigned k=0;k<n;k++){
        unsigned at=demo_pred_hash(p[k]),probes=0;
        while(demo_pred_cache[at].addr && demo_pred_cache[at].addr!=p[k] && probes++<4096)at=(at+1)&4095;
        if(probes>=4096)continue;
        demo_pred_entry *e=demo_pred_cache+at;
        if(e->valid && e->fence>fence)continue;
        const volatile uint64_t *v=(const volatile uint64_t *)(uintptr_t)p[k];
        *e=(demo_pred_entry){p[k],v[0],v[2],fence,1};
    }
    pthread_mutex_unlock(&demo_pred_mu);free(p);
}
static int demo_predicate(unsigned conditional,uint64_t addr,unsigned mode,int *enabled){
    if(demo_pred_mode<0){
        const char *v=getenv("DM_DEMO_PREDICATE");demo_pred_mode=0;
        if(v && strcmp(v,"strict")){
            if(!getenv("DM_TEST_DEMO") || strcmp(getenv("DM_TEST_DEMO"),"1"))MDIE("DEMO predicate requires isolated DM_TEST_DEMO=1");
            if(!strcmp(v,"async"))demo_pred_mode=1;else if(!strcmp(v,"always"))demo_pred_mode=2;else MDIE("DEMO invalid predicate mode");
        }
        MLOG("DEMO_PREDICATE mode=%d default_strict=1 game_writes=0",demo_pred_mode);
    }
    if(!demo_pred_mode || !conditional || !addr || !dm_rl_active || !dm_rl_match_phase || !dm_rl_active() || dm_rl_match_phase()!=1)return 0;
    demo_pred_calls++;*enabled=1;
    if(demo_pred_mode==1){
        pthread_mutex_lock(&demo_pred_mu);
        unsigned at=demo_pred_hash(addr),probes=0;
        while(demo_pred_cache[at].addr && demo_pred_cache[at].addr!=addr && probes++<4096)at=(at+1)&4095;
        demo_pred_entry e=demo_pred_cache[at];
        if(probes<4096 && e.valid && e.addr==addr){*enabled=mode==0?e.a==e.b:e.a!=e.b;demo_pred_hits++;}else demo_pred_fallback++;
        pthread_mutex_unlock(&demo_pred_mu);
        unsigned k;for(k=0;k<demo_pred_n;k++)if(demo_pred_requests[k]==addr)break;
        if(k==demo_pred_n){if(k<2048)demo_pred_requests[demo_pred_n++]=addr;else demo_pred_overflow++;}
    }
    static uint64_t last=UINT64_MAX;uint64_t frame=dm_nvn_frame_count();
    if(frame%300==0 && frame!=last){last=frame;MLOG("DEMO_PREDICATE_STATS frame=%llu calls=%llu hits=%llu fallback=%llu overflow=%llu",frame,demo_pred_calls,demo_pred_hits,demo_pred_fallback,demo_pred_overflow);}
    return 1;
}

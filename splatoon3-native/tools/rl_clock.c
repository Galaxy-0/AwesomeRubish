// Small ctypes ABI for the same C11 atomics read by the native processes.
#include "../upstream/dm/host/dm_rl_clock.h"
int rl_clock_init(dm_rl_clock *clock) {
    clock->magic=DM_RL_CLOCK_MAGIC;
    atomic_init(&clock->state,0);atomic_init(&clock->last,dm_rl_clock_wall());
    return atomic_is_lock_free(&clock->state) && atomic_is_lock_free(&clock->last);
}
uint64_t rl_clock_read(dm_rl_clock *clock) {return dm_rl_clock_read(clock);}
uint64_t rl_clock_pause(dm_rl_clock *clock) {return dm_rl_clock_pause(clock);}
void rl_clock_resume(dm_rl_clock *clock) {dm_rl_clock_resume(clock);}

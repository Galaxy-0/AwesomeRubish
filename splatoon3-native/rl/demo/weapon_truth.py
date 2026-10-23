"""11.3.0 primary Saber action decoding, qualified by controlled native inputs.

E0 is ink cost accumulated during charge, not a frame counter. E4 is a float
animation clock, E8 its deadline. State 1 is a LIGHT swing when E4>=0;
the earlier wait/idle-only interpretation of state 1 was incorrect.
"""

import math

PHASES = {
    "idle": 0,
    "charging": 1,
    "light_swing": 2,
    "full_swing": 3,
    "recovery": 4,
    "charge_cancel_exit": 5,
    "wait": 6,
}


def decode_saber(state, cost, elapsed, duration):
    if (
        not all(math.isfinite(v) for v in [cost, elapsed])
        or not -1e-6 <= cost <= 0.11701
    ):
        return None
    if state not in (1, 5, 6, 8) or duration not in (0, 30, 36):
        return None
    if elapsed < -1.001 or elapsed > 36.001:
        return None
    charge = (
        (cost / 0.007 if cost <= 0.035 else 5 + (cost - 0.035) * 15 / 0.082)
        if state == 5
        else 0.0
    )
    charge = max(0.0, min(20.0, charge))
    # A charge-cancel transition can retain graph state5 for four ticks while
    # E0 has already reset to zero. Do not claim it is charging/full there.
    phase = (
        ("charging" if cost > 1e-6 else "charge_cancel_exit")
        if state == 5
        else ("light_swing" if elapsed >= 0 else "wait")
        if state == 1
        else ("full_swing" if state == 8 else "recovery" if elapsed >= 0 else "idle")
    )
    remaining = max(0.0, duration - elapsed) if elapsed >= 0 else 0.0
    return dict(
        weapon_phase_qualified=True,
        weapon_stage=phase,
        weapon_stage_id=PHASES[phase],
        charge_native_frames=charge,
        charge_frames=charge * 21 / 20,
        charge_progress=charge / 20,
        animation_deadline_remaining_frames=remaining,
        # ReserveAcceptFrame/queued attacks mean animation deadline is NOT a
        # proven next-input lock. Keep simulated action masking independent.
        cooldown_frames=0.0,
        cooldown_lock_qualified=False,
        stage_source="PlayerInkActionSaber+38/E0/E4/E8, controlled 11.3.0",
    )

"""Measured profile for weapon 8000, game 11.3.0 (720896).

Distances are native world units, timing is controlled fixed60 presents.
These are observations under the documented fixtures, not universal guarantees.
No extracted game data or proprietary binaries are distributed here.
"""
WEAPON_ID = 8000
GAME_VERSION = '11.3.0'
GAME_BUILD = '28c4287aee36f7499da60f3e68b54c70'
CHARGE_KEEP_SUPPORTED = False
MINIMUM_OBSERVED_STANDING_RELEASE = 21
MINIMUM_OBSERVED_EMERGE_INPUT_RELEASE = 26
EMERGENCE_TO_RELEASE_INTERVAL = (25, 26)
CONSERVATIVE_STANDING_RELEASE = 24
CONSERVATIVE_EMERGE_RELEASE = 30
LIGHT_REPEAT_INPUT_PERIOD = 30
ROLL_INPUT = 'in own ink: swim forward 30 presents, reverse stick+B together, keep ZL'
SURGE_INPUT = 'establish climb on an inked wall, stop left stick, hold ZL+B 60 presents, release B and push up'
SURGE_CHARGE_PARAMETER_FRAMES = 45  # native full-input recipe uses 60, not claimed minimum
FLICK_COLD_START_OBSERVED_FRAMES = 87  # includes 14-present own-gyro calibration
FLICK_MATCHED_ORDINARY_CONTROL_FRAMES = 176
FLICK_GYRO_AXIS = 2  # virtual flat-controller Z; sign/gain learned from own view
LIGHT_PROJECTILE_DAMAGE = 35
FULL_PROJECTILE_DAMAGE = 70
PARAMETER_LIGHT_CONTACT_DAMAGE = 20  # not independently isolated in native tests
PARAMETER_FULL_CONTACT_DAMAGE = 140  # native close dash confirms >=100 only
LIGHT_RANGE_BRACKET = (18.7896570812, 19.5618558788)
FULL_RANGE_BRACKET = (21.7824151849, 22.5553039819)
RANGE_CONDITIONS = 'Yunohana y=3 flat lane, standing human target, yaw/pitch <=.015 rad'
SUB_WEAPON = 'Burst Bomb'
SUB_ID = 2
SUB_INPUT = 'R press, then release'
SPECIAL_WEAPON = 'Zipcaster'
SPECIAL_ID = 3
SPECIAL_BASE_POINTS = 210
SPECIAL_INPUT = 'full own meter required; RS activation verified; R hook candidate remains unverified'
NATIVE_SUPPORT = {
    'charge_keep': 'unsupported_by_weapon_design',
    'charge_slash': 'supported', 'emerge_charge': 'supported',
    'dash': 'supported', 'combo_move': 'supported',
    'squid_roll': 'supported_motion_witness', 'squid_surge': 'supported_motion_witness',
    'burst_bomb': 'supported', 'zipcaster': 'unsupported_hook_traversal',
    'zipcaster_activation': 'supported_full_meter_RS',
    'predictive_aim': 'supported_camera_lead', 'fast_turn': 'supported',
}

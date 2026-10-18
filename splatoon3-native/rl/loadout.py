"""Legal gear skill names, in this build's native enum-index order."""
PIECES=('head','clothes','shoes')
SKILLS=('none','ink_saver_main','ink_saver_sub','ink_recovery_up','run_speed_up',
        'swim_speed_up','special_charge_up','special_saver','special_power_up',
        'quick_respawn','quick_super_jump','sub_power_up','ink_resistance_up',
        'sub_resistance_up','intensify_action','opening_gambit','last_ditch_effort',
        'tenacity','comeback','ninja_squid','haunt','thermal_ink','respawn_punisher',
        'ability_doubler','stealth_jump','object_shredder','drop_roller')


def encode_loadout(loadout):
    if not isinstance(loadout,dict) or set(loadout)!=set(PIECES):
        raise ValueError('loadout requires head, clothes and shoes')
    result=[]
    for piece in PIECES:
        gear=loadout[piece]
        if not isinstance(gear,dict) or set(gear)!={'main','subs'} or not isinstance(gear['subs'],(list,tuple)) or len(gear['subs'])!=3:
            raise ValueError('each gear requires main and exactly three subs')
        names=[gear['main'],*gear['subs']]
        if any(n not in SKILLS for n in names):raise ValueError('unknown gear skill')
        indexes=[SKILLS.index(n) for n in names];main=indexes[0]
        if 0 in indexes:raise ValueError('all declared gear slots must contain a skill; none is diagnostic only')
        if any(n>14 for n in indexes[1:]):raise ValueError('exclusive skills cannot be subskills')
        if main>14 and main not in {'head':range(15,19),'clothes':range(19,24),'shoes':range(24,27)}[piece]:
            raise ValueError('exclusive main skill on wrong gear piece')
        result.extend(indexes)
    return ','.join(map(str,result))


def uniform_loadout(skill='quick_super_jump'):
    return {piece:dict(main=skill,subs=[skill]*3) for piece in PIECES}

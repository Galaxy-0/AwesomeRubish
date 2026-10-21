"""Extract local .52 sparse numeric parameters; raw tables never leave work/."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.byml import read
from tools.stage_collision import unpack

def extract():
    pack=ROOT/'work/data/v720896/RomFS/Pack/Params.pack.zs';entry='Component/GameParameterTable/WeaponShooterGravity.game__GameParameterTable.bgyml'
    entries=unpack(pack);raw=read(entries[entry])['GameParameters']
    db=ROOT/'work/data/v720896/RomFS/RSDB/WeaponInfoMain.Product.b30.rstbl.byml.zs'
    row=next(r for r in read(subprocess.check_output(['zstd','-dc',str(db)])) if r['Id']==50)
    if row['__RowId']!='Shooter_Gravity_00' or '.52'not in row['Label']:raise AssertionError('catalog mismatch')
    d,w,m=raw['DamageParam'],raw['WeaponParam'],raw['MoveParam']
    result=dict(schema='inklab.d3.parameters.v1',version='11.3.0',weapon_id=50,catalog=row['__RowId'],parameter_values=dict(damage_max_raw=d['ValueMax'],damage_min_raw=d['ValueMin'],damage_max_hp=d['ValueMax']/10,damage_min_hp=d['ValueMin']/10,falloff_start_age_frames=d['ReduceStartFrame'],falloff_end_age_frames=d['ReduceEndFrame'],repeat_frames=w['RepeatFrame'],nominal_catalog_range=row['Range'],spawn_speed_units_per_frame=m['SpawnSpeed'],straight_to_brake_frames=m['GoStraightToBrakeStateFrame'],straight_end_max_speed=m['GoStraightStateEndMaxSpeed'],free_air_resist=m['FreeAirResist'],free_gravity=m['FreeGravity'],standing_swerve_degrees=w['Stand_DegSwerve'],standing_bias_min=w['Stand_DegBiasMin'],standing_bias_decrease=w['Stand_DegBiasDecrease'],jump_swerve_degrees=w['Jump_DegSwerve'],ink_per_shot=w['InkConsume'],shot_move_speed=w['MoveSpeed']),provenance=dict(pack=str(pack.relative_to(ROOT)),pack_sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),entry=entry,entry_sha256=hashlib.sha256(entries[entry]).hexdigest(),catalog_sha256=hashlib.sha256(db.read_bytes()).hexdigest()),limits=['Sparse overrides, not all native defaults.','Range is catalog annotation, not measured guaranteed hit range.','Swerve parameters do not specify a uniform/Gaussian distribution.','SpawnSpeed differs from effective flight speed.'])
    out=ROOT/'work/d3/parameters.json';out.write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':print(json.dumps(extract(),indent=2))

"""Referee-only HP transitions; policies never receive these samples."""
import math


def large_hp_drops(before,samples,minimum=.29):
    previous=before['hp'];last=before['position_sample_frame'];events=[]
    for sample in samples:
        stamp=sample['position_sample_frame']
        if not sample['hp_valid'] or stamp<=last:continue
        loss=previous-sample['hp']
        if loss>=minimum:
            events.append(dict(frame=sample['frame'],sample_frame=stamp,hp_loss=loss))
        previous=sample['hp'];last=stamp
    return events


def roll_witness(run_up,before,samples):
    """Operational roll witness calibrated against matched native controls.

    Only an undamaged boosted reversal arc on the flat, inked fixture counts.
    This is not a decoded action enum or an armor/last-hit attribution claim.
    """
    if len(run_up)<2:return dict(verified=False,reason='missing native run-up')
    first,last=run_up[0],run_up[-1]
    a,b=first['position'],last['position'];dx,dz=b[0]-a[0],b[2]-a[2]
    distance=math.hypot(dx,dz);duration=last['frame']-first['frame']
    motion=last.get('referee_motion',{})
    baseline=(a[1]+b[1])/2
    valid=(duration==30 and distance>=2.5 and abs(a[1]-b[1])<.1 and
           motion.get('form_squid')==1 and motion.get('ground_contact')==0 and
           first['hp_valid'] and last['hp_valid'] and first['hp']>=.999 and last['hp']>=.999 and
           first['position_valid'] and last['position_valid'] and
           0<=last['frame']-last['position_sample_frame']<=8)
    peak=baseline;reverse=0.;count=0;stamp=before['position_sample_frame']
    for sample in samples:
        if not sample['hp_valid'] or not sample['alive'] or sample['hp']<before['hp']-.001:break
        if sample['position_sample_frame']<=stamp:continue
        stamp=sample['position_sample_frame']
        if not sample['position_valid'] or not 0<=sample['frame']-stamp<=8:continue
        p=sample['position'];peak=max(peak,p[1]);count+=1
        if distance:reverse=min(reverse,((p[0]-b[0])*dx+(p[2]-b[2])*dz)/distance)
    boosted=peak-baseline
    verified=valid and boosted>=1.2 and reverse<=-.5
    return dict(verified=verified,reason='matched-control boosted reversal arc' if verified else
                'run-up/undamaged boosted reversal arc not established',run_up_frames=duration,
                run_up_distance=distance,run_up_valid=valid,undamaged_samples=count,
                peak_height_over_ground=boosted,reverse_displacement=reverse)

"""Temporary A5 observer-HUD statistics, deliberately separate from A3b truth."""
import math


class HudEvents:
    def __init__(self,origins,atlas):
        self.origins={a:i['frame'] for a,i in origins.items()};self.atlas=atlas
        self.counters={};self.events=[];self.positions={a:[] for a in origins}

    def update(self,infos,frame):
        for a,i in infos.items():
            sample=i.get('position_sample_frame',0)-self.origins[a]
            if i.get('position_valid') and 0<=frame-sample<=12:
                p=tuple(i['position']);history=self.positions[a]
                if not history or history[-1][0]!=sample:history.append((sample,p))
                self.positions[a]=[(f,p) for f,p in history if frame-f<=30]
        for observer,i in infos.items():
            for text,target in i.get('hud_slot_agents',{}).items():
                slot=int(text)
                if not i.get('hud_counter_valid',[0]*8)[slot]:continue
                key=(observer,target);count=i['hud_downs'][slot];previous=self.counters.get(key,0)
                if count<previous:raise ValueError('HUD counter reset inside a match')
                for _ in range(count-previous):
                    cause,position=self.environmental(target,frame)
                    self.events.append(dict(observer=observer,victim=target,detected_frame=frame,
                                            hud_sample_frame=i['hud_sample_frame'][slot]-self.origins[observer],
                                            environmental=cause,classification_position=position,
                                            source='observer_hud_down_counter',attacker=None,weapon=None))
                self.counters[key]=count

    def environmental(self,target,frame):
        samples=self.positions[target]
        if not samples:return None,None
        points=self.atlas.points
        xmin=min(p[0] for p in points);xmax=max(p[0] for p in points)
        zmin=min(p[2] for p in points);zmax=max(p[2] for p in points)
        ymin=self.atlas.data.get('scope',{}).get('min_y',min(p[1] for p in points))
        for sample,p in reversed(samples):
            if not 0<=frame-sample<=30:continue
            if p[1]<ymin-2:return 'fall_below_playable_floor',p
            if p[0]<xmin-2 or p[0]>xmax+2 or p[2]<zmin-2 or p[2]>zmax+2:return 'outside_static_playable_bounds',p
        return None,samples[-1][1]

    def summary(self,observer,enemy):
        def count(target,environment_only=False):
            key=(observer,target)
            if key not in self.counters:return None
            if not environment_only:return self.counters[key]
            return sum(e['observer']==observer and e['victim']==target and e['environmental'] is not None for e in self.events)
        return dict(enemy_hud_downs=count(enemy),own_hud_downs=count(observer),
                    enemy_environmental_downs=count(enemy,True),own_environmental_downs=count(observer,True),
                    source='observer HUD counts, includes unclassified causes; no last-hit attribution')

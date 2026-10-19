"""A6 own special extension; reuse the existing policy sandbox and type gate.

The frozen v1 records/encoder remain intact. Only an explicit typed OWN sample
can add the human-visible special meter. No referee object crosses the pipe.
"""
from dataclasses import dataclass
import json
import math

from .policy import encode_policy
from .process import PolicyProcess, validate_action


@dataclass(frozen=True)
class OwnSpecial:
    player_id: str
    sample_frame: int
    value: float | None


def own_special(info, player_id, origin):
    value=info.get('special')
    valid=(info.get('special_valid') and type(value) in (int,float) and
           math.isfinite(value) and 0<=value<=1)
    return OwnSpecial(player_id,int(info.get('position_sample_frame',-1))-origin,
                      float(value) if valid else None)


def encode_control(observation, special=None):
    payload=json.loads(encode_policy(observation))  # reject truth/dict/subclass
    value=None
    if special is not None:
        if type(special) is not OwnSpecial:
            raise TypeError('typed own special sample required')
        if special.player_id!=observation.own.public.player_id:
            raise ValueError('foreign special meter')
        if special.value is not None and (type(special.value) not in (int,float) or
                not math.isfinite(special.value) or not 0<=special.value<=1):
            raise ValueError('invalid special meter')
        if 0<=observation.frame-special.sample_frame<=8:
            value=special.value
    payload['own']['special']=value
    return (json.dumps(payload,allow_nan=False,separators=(',',':'))+'\n').encode()


class ControlProcess(PolicyProcess):
    def act(self, observation, special=None):
        payload=encode_control(observation,special)
        try:
            self.child.stdin.write(payload);self.child.stdin.flush()
            return validate_action(self._receive(self.timeout))
        except BaseException:
            self.close()
            raise

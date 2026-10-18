"""POSIX local socket client; independent of the native host graphics API."""
import json
import socket

import numpy as np


class Client:
    def __init__(self, path, timeout=60):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(timeout)
        self.socket.connect(str(path))
        self.stream = self.socket.makefile('rb')
        self.sequence = 0
        self.frame = None
        self.expected = 0

    def receive(self):
        line = self.stream.readline(4097)
        if not line.endswith(b'\n') or len(line) > 4096:
            raise RuntimeError('native RL connection closed or invalid observation header')
        info = json.loads(line)
        if (info.get('version'), info.get('width'), info.get('height'), info.get('channels'), info.get('bytes')) != (1,128,72,3,27648):
            raise RuntimeError(f'invalid observation shape/version: {info}')
        if info['request'] != self.sequence or info['advanced'] != self.expected:
            raise RuntimeError(f'RL step acknowledgement mismatch: {info}')
        if self.frame is not None and info['frame'] != self.frame + self.expected:
            raise RuntimeError(f'RL frame skip mismatch: {self.frame} -> {info}')
        data = self.stream.read(27648)
        if len(data) != 27648: raise RuntimeError('truncated RL image')
        if not 0 <= info['phase'] <= 3: raise RuntimeError('invalid match phase')
        if not 0<=info.get('frames_without_input',0)<=self.expected:
            raise RuntimeError('invalid frames_without_input')
        self.frame = info['frame']
        observation = dict(pixels=np.frombuffer(data, dtype=np.uint8).reshape(72,128,3).copy(),
                           frame=np.array([info['frame']], dtype=np.int64), phase=info['phase'],
                           position=np.asarray(info.get('position',[0,0,0]),dtype=np.float32),
                           position_valid=int(info.get('position_valid',0)),
                           ink=np.array([info.get('ink',0)],np.float32),ink_valid=int(info.get('ink_valid',0)),
                           heading=np.array([info.get('heading',0)],np.float32),heading_valid=int(info.get('heading_valid',0)),
                           remaining_time=np.array([info.get('remaining_time',0)],np.float32),time_valid=int(info.get('time_valid',0)),
                           hp=np.array([info.get('hp',0)],np.float32),hp_valid=int(info.get('hp_valid',0)),
                           special=np.array([info.get('special',0)],np.float32),special_valid=int(info.get('special_valid',0)),
                           score=np.array(info.get('score',[0,0]),np.float32),score_valid=int(info.get('score_valid',0)),
                           score_units=int(info.get('score_units',0)),turf_ratio=np.array(info.get('turf_ratio',[0,0]),np.float32),turf_valid=int(info.get('turf_valid',0)))
        if observation['position'].shape!=(3,) or not np.isfinite(observation['position']).all() or observation['position_valid'] not in (0,1):
            raise RuntimeError('invalid native position observation')
        if not np.isfinite(observation['ink']).all() or not 0<=observation['ink'][0]<=1 or observation['ink_valid'] not in (0,1):
            raise RuntimeError('invalid native ink observation')
        if not np.isfinite(observation['heading']).all() or abs(observation['heading'][0])>np.pi+1e-6 or observation['heading_valid'] not in (0,1):
            raise RuntimeError('invalid native heading observation')
        if not np.isfinite(observation['remaining_time']).all() or not 0<=observation['remaining_time'][0]<=600 or observation['time_valid'] not in (0,1):
            raise RuntimeError('invalid native countdown observation')
        if not np.isfinite(observation['hp']).all() or not 0<=observation['hp'][0]<=1 or observation['hp_valid'] not in (0,1):
            raise RuntimeError('invalid native HP observation')
        if not np.isfinite(observation['special']).all() or not 0<=observation['special'][0]<=1 or observation['special_valid'] not in (0,1):
            raise RuntimeError('invalid native special observation')
        for key,maximum in (('score',100),('turf_ratio',1)):
            value=observation[key]
            if value.shape!=(2,) or not np.isfinite(value).all() or (value<0).any() or (value>maximum).any():raise RuntimeError('invalid native '+key)
        if observation['score_valid'] not in (0,1) or observation['turf_valid'] not in (0,1) or observation['score_units'] not in (0,1,2):raise RuntimeError('invalid native score flags')
        return observation, info

    def send_step(self, action, frames):
        axes = np.asarray(action['sticks'], dtype=float)
        gyro = np.asarray(action['gyro'], dtype=float)
        buttons = np.asarray(action['buttons'])
        if axes.shape != (4,) or gyro.shape != (3,) or buttons.shape != (6,):
            raise ValueError('action requires sticks[4], gyro[3], buttons[6]')
        if not np.isfinite(axes).all() or not np.isfinite(gyro).all() or np.abs(axes).max() > 1 or np.abs(gyro).max() > 1:
            raise ValueError('stick and gyro values must be finite in [-1,1]')
        if not np.isin(buttons, (0,1)).all(): raise ValueError('buttons must be binary')
        if not isinstance(frames, int) or not 1 <= frames <= 3600: raise ValueError('frames must be in [1,3600]')
        # ZR, ZL, R, RS (special), B, Y (camera reset).
        mask = sum(int(v) << bit for v, bit in zip(buttons, (9,8,7,5,1,3)))
        sticks = np.rint(axes*32767).astype(np.int32)
        self.sequence += 1; self.expected = frames
        line = f'STEP {self.sequence} {frames} {mask:x} ' + ' '.join(map(str, sticks)) + ' ' + ' '.join(map(str, gyro)) + '\n'
        self.socket.sendall(line.encode('ascii'))

    def close(self):
        try: self.socket.sendall(b'RELEASE\n')
        except OSError: pass
        self.stream.close(); self.socket.close()

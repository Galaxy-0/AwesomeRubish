"""Opt-in referee recorder. CPU transfer is outside the unrecorded hot path."""

import json
from pathlib import Path
from .env import HEADING, HP, INK, PITCH, SQUID, SUB, YAW


class Recorder:
    def __init__(self, env, environment=0, stride=6):
        self.env = env
        self.index = environment
        self.stride = stride
        self.rows = []
        self.events = [[], []]
        self.last_buttons = [[0] * 5, [0] * 5]
        self.capture(None, None)

    def capture(self, actions, infos):
        e = self.env
        frame = int(e.steps[self.index].item())
        if actions is not None:
            a = actions[self.index].detach().cpu().tolist()
            for player in range(2):
                for k, name in enumerate(["ZR", "ZL", "B", "R", "RS"]):
                    down = a[player][3 + k]
                    previous = self.last_buttons[player][k]
                    if down != previous:
                        self.events[player].append(
                            dict(
                                frame=frame,
                                type=name + ("_down" if down else "_release"),
                                evidence="simulated_input",
                            )
                        )
                    self.last_buttons[player][k] = down
        if infos is not None:
            events = infos["events"][self.index].detach().cpu().tolist()
            for player, ev in enumerate(events):
                if ev[0]:
                    self.events[player].append(
                        dict(
                            frame=frame,
                            type="damage",
                            amount=ev[0] * 100,
                            evidence="gpu_referee",
                        )
                    )
                if ev[1]:
                    self.events[player].append(
                        dict(
                            frame=frame,
                            type="down",
                            evidence="gpu_referee",
                            cause=("weapon" if ev[5] else "self_splat")
                            if len(ev) > 5
                            else "unclassified",
                        )
                    )
        if frame % self.stride == 0:
            self.rows.append(
                dict(
                    frame=frame,
                    state=e.state[self.index].detach().cpu().tolist(),
                    projectiles=e.shots[self.index].detach().cpu().tolist(),
                    actions=None if actions is None else a,
                )
            )

    def write(self, path):
        players = []
        for i, name in enumerate(["alpha", "bravo"]):
            states = []
            views = []
            for row in self.rows:
                s = row["state"][i]
                f = row["frame"]
                form = "submerged" if s[SUB] else "squid" if s[SQUID] else "human"
                states.append(
                    [f, f, *s[:3], s[HEADING], form, s[HP], bool(s[HP] > 0), s[INK]]
                )
                views.append([f, s[YAW], s[PITCH]])
            players.append(
                dict(
                    id=name,
                    role=f"gpu_player_{i}",
                    states=states,
                    events=self.events[i],
                    views=views,
                )
            )
        data = dict(
            schema="inklab.trace.v1",
            id="rl-stage0-random",
            label="RL stage0 · GPU 随机夹具（非训练）",
            source_kind="gpu_simulated_state",
            map="Yunohana",
            fps=60,
            start_frame=self.rows[0]["frame"],
            end_frame=self.rows[-1]["frame"],
            stride=self.stride,
            columns=[
                "frame",
                "sample_frame",
                "x",
                "y",
                "z",
                "heading",
                "form",
                "hp",
                "alive",
                "ink",
            ],
            players=players,
            position_semantics="GPU approximate referee state, not native measurements; no trained policy",
            referee_samples=self.rows,
        )
        Path(path).write_text(json.dumps(data, separators=(",", ":")) + "\n")
        return data

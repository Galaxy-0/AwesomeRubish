"""Policy parameterization only: latch commands become ordinary held buttons.

No auto-charge/release macro, aim, physics, reward or decision-time changes.
Previous is the actor's own last physical controller input, never enemy state.
"""

import torch


def physical(commands, previous, semantics="level"):
    if semantics == "level":
        return commands.clone()
    if semantics != "toggle":
        raise ValueError("unknown button semantics")
    result = commands.clone()
    for head in (3, 4):
        c = commands[..., head]
        result[..., head] = torch.where(c == 0, previous[..., head], (c == 1).long())
    return result


def commands_from_levels(levels, semantics="level"):
    result = levels.clone()
    if semantics == "toggle":
        for head in (3, 4):
            result[..., head] = torch.where(levels[..., head] > 0, 1, 2)
    elif semantics != "level":
        raise ValueError("unknown button semantics")
    return result


def command_mask(mask, previous, semantics="level"):
    if semantics == "level":
        return mask
    if semantics != "toggle":
        raise ValueError("unknown button semantics")
    result = mask.clone()
    for head in (3, 4):
        result[..., head, :] = False
        held = previous[..., head].long()
        result[..., head, 0] = (
            mask[..., head, :].gather(-1, held[..., None]).squeeze(-1)
        )
        result[..., head, 1] = mask[..., head, 1]
        result[..., head, 2] = mask[..., head, 0]
    return result

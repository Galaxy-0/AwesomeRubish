"""Shared M5/M6 native host configuration and controller-only room setup."""
import os


def host_environment(root, out, directory, player, players, air_socket, weapons=None, visible=False):
    route = (root/'tools/routes/m2-local-lobby.keys').read_text().strip()
    if players > 1:
        route += ',f2700:A' + (',f3300:Y,f3900:A' if player == 0 else ',f3900:A,f4500:A')
    env = {k: v for k, v in os.environ.items() if not k.startswith('DM_')}
    env.update(DM_ROOT=str(root/'work'), DM_ROMFS=str(root/'work/data/v720896/RomFS'),
        DM_SAVE=str(directory/'save'), DM_TEMP=str(directory/'temp'),
        DM_MSL_DIR=str(root/'work/build/cache/metal_shader_cache'), DM_FONT_DIR=str(root/'work/build/font'),
        DM_PLAYER=str(player), DM_FULL_UNLOCK='1', DM_HEADLESS='0' if visible and player == 0 else '1',
        DM_WINDOW='1', DM_OPMODE='0', DM_RESOURCE_REPORT='1', DM_MEM_CAP_GB='0',
        DM_MEMSTAT=str(directory/'memory.tsv'), DM_MEMSTAT_DUMP='90', DM_KEYS=route,
        DM_PIPELINE_CACHE=str(root/'work/build/cache/runtime-pipelines'), DM_LOAD_SLOTS=str(out/'load-slots'),
        DM_HID_FIFO=str(directory/'controller.fifo'), DM_WATCH_STALL='180', DM_WATCH_SAMPLE=str(directory/'stall.txt'))
    if weapons: env['DM_WEAPON'] = str(weapons[player])
    env['DM_LDN_AIR' if air_socket else 'DM_LDN_FRONTEND'] = str(air_socket) if air_socket else '1'
    return env


def configure_room(controller, players, mode, stage_index):
    """M5's verified native mode/map/team route. No game-memory writes."""
    for _ in range(mode): controller.press(0, 'Right')
    controller.press(0, 'Down'); controller.press(0, 'A')
    page, cell = divmod(stage_index, 12); row, col = divmod(cell, 4)
    for _ in range(page): controller.press(0, 'R')
    controller.press(0, 'Right')
    for _ in range(col): controller.press(0, 'Right')
    for _ in range(row): controller.press(0, 'Down')
    controller.press(0, 'A'); controller.press(0, 'Down'); controller.press(0, 'A')
    controller.frames(0, 600)
    for player in range(players):
        controller.press(0, 'Right')
        if player >= players//2: controller.press(0, 'Right')
        controller.press(0, 'Down')
    controller.frames(0, 600)


def prepare_match(controller, players):
    controller.press(0, 'A'); controller.frames(0, 900)
    (controller.out/'load-slots/active').touch()
    for player in range(players): controller.send(player, 'A')


BUTTONS = {name: 1 << n for n, name in enumerate(
    ('A','B','X','Y','LS','RS','L','R','ZL','ZR','Plus','Minus','Left','Up','Right','Down'))}

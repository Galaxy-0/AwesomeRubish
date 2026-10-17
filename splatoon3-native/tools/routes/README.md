# M2 controller route

The tutorial route is abandoned as of 2026-10-18. M2 now starts with a fresh
copy of `work/save_ref/save.dat`, imported from the designated emulator save.
Do not continue or replay the opening prefix to advance M2.

`m2-opening-prefix.keys` records the successful exploration inputs through
character creation, Smallfry aim / movement, weapon pickup, two balloon targets,
and two painted wall climbs. The observed endpoint is the right-stick tutorial,
not the local lobby. It includes idle gaps from interactive exploration.

This is a **partial, unreplayed diagnostic route**. Do not use it as M2 acceptance.
It was reconstructed from the successful run's DM_KEYS / FIFO logs. Movement and
rotation holds use wall-clock seconds; frame-triggered starts alone do not make
their results deterministic. The `G*` names currently describe the raw virtual
axes documented in `tools/CONTROLLER.md`; their screen directions are not yet
calibrated (positive X / `GUp` moved the camera downward in this run).

Historical screenshots and action logs remain in `work/m2/explore3/` and
`work/run/m2-explore3.log`. These are not the starting point for the new route.

Once the new route has been verified and replayed from a fresh reference-save copy, save it
as `m2-local-lobby.keys`, keep a visually reviewed local-lobby reference screenshot
at `work/m2/reference-local-lobby.png`, and run the M2 gate with its arrival frame.
Screenshots and game data stay in `work/`; only the controller script is tracked.

`m2-local-lobby.keys` is the new route: start with ZL+ZR, open the X map, move
down twice (the disabled City row is skipped) to The Shoal, confirm, and press
L in its lobby to show Private Battle. The reviewed screenshot frame is 2400.
It requires the build-gated `DM_LDN_FRONTEND=1` idle context and protocol setup;
it does not create or join a room. The cap failure is fixed by sizing each spill
for its records. See `notes/PROGRESS.md` for acceptance status and evidence.

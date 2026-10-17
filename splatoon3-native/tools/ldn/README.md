# Local virtual LDN medium

`air.py` is a local-only replacement for wireless discovery and the datagram
medium. It listens on one Unix domain stream socket; it never creates an IP
socket. Start one medium per experiment and point all participants at it:

```sh
.venv/bin/python tools/ldn/air.py --socket /tmp/spl3-air.sock
# For each dmhost, also set its normal game paths and a separate save copy:
DM_PLAYER=0 DM_LDN_AIR=/tmp/spl3-air.sock upstream/dm/host/dmhost work/build/patched_v720896
```

The service refuses an existing path and duplicate player indices. The socket
has mode 0600. Stop it with SIGTERM; connected clients observe the medium loss.
Use a short path (macOS Unix socket paths are limited to 103 bytes).

`DM_LDN_AIR` enables the host adapter only for the verified main build
`28c4287aee36f7499da60f3e68b54c70`, requires `DM_PLAYER=0..7`, and must name
an already running service. Without it, the original offline behavior and
`DM_LDN_FRONTEND=1` idle-only frontend remain available.

The medium owns AP/Station state, rooms, sessions, membership, scan filtering,
accept policy, beacon updates, UDP queues, and EventFd wake counters. Game PIA
code still runs in main. Guest socket descriptors are virtual and never passed
to an OS networking API. Datagram delivery requires both peers to be members of
the same room; IP destinations outside that room are rejected. UDP is bounded
and may drop when a queue fills. TCP, DNS, SSL, Nintendo services and real radio
frames are outside this implementation.

The host HLE hooks live in `upstream/dm/host/hle_ldn.c`, with socket entrypoints
in `hle_net.c` and `hle_offline.c`; all are captured by the checked-in patch.
ABI reference: [libnx LDN declarations](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/services/ldn.h).
SDK C++ wrappers were also disassembled locally: LDN IPv4 is host order,
BSD sockaddr_in contains network-order address and port, NetworkInfo is 0x480
bytes, ScanFilter is 0x60 bytes. Advertise data is copied exactly from the game.
No canned game beacon or synthetic scan result is supplied.

No-game regression (builds and runs the same C HLE as dmhost):

```sh
make -C upstream/dm/host/tests GAME=0100C2500FC20000 build/t_ldn_peer
.venv/bin/python tests/test_ldn_air.py
```

Artifacts go to `work/tests/ldn-air-*`. Passing this component alone does not
complete M3: two real games must create, discover and join the same room.

Integration details found during bring-up:

- Idle `GetNetworkInfo` must return the LDN InvalidState result `0x40cb`.
  The game's polling path explicitly recognizes that range; generic offline
  failure latches a communication error. A room is still never reported while idle.
- Finalize drops the SystemEvent binding before the guest destroys/reuses its
  storage, and acknowledges identity release through the medium before reconnect.
- LDN NetworkType is bit 2 and scan NetworkType filtering is a bitmask test.
- The game-used PIA receive path is nonblocking (MSG_DONTWAIT). Its SDK errno
  namespace uses EAGAIN=11; BSD/Darwin wire errors are converted at the adapter.
- The game binds UDP port 12345 and requests SO_BROADCAST and SO_REUSEPORT.
  Reuse is enforced for both sockets sharing a virtual port.

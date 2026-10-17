#!/usr/bin/env python3
"""Local-only virtual LDN medium. No Internet sockets, game files or keys.

Wire: little-endian <magic, op, sequence, size> + payload. Replies use op|0x80000000
and start with a BSD errno (0 on success). Unsolicited op=100 is a state snapshot.
ABI layouts follow libnx ldn.h; SDK 22 wrappers were checked in the local dump.
"""
import argparse
import asyncio
from collections import deque
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets
import signal
import struct
import time

MAGIC = 0x334E444C
NET_SIZE = 0x480
MAX_PACKET = 65536
FAIL = 22


def u16(b, off=0): return struct.unpack_from('<H', b, off)[0]
def u32(b, off=0): return struct.unpack_from('<I', b, off)[0]
def put16(b, off, n): struct.pack_into('<H', b, off, n)
def put32(b, off, n): struct.pack_into('<I', b, off, n)


@dataclass(eq=False)
class Peer:
    writer: asyncio.StreamWriter
    player: int = -1
    state: int = 0
    reason: int = 0
    room: object = None
    node: int = -1
    advertise: bytes = b''
    policy: int = 0
    filters: set = field(default_factory=set)
    sockets: dict = field(default_factory=dict)
    next_fd: int = 100
    received: int = 0
    sent: int = 0
    sent_bytes: int = 0
    received_bytes: int = 0
    dropped: int = 0
    queue_peak: int = 0

    @property
    def ip(self): return 0x0A0D0001 + self.player
    @property
    def mac(self): return bytes([2, 0x4E, 0x58, 0, 0, self.player + 1])


@dataclass
class Room:
    host: Peer
    info: bytearray
    security: bytes
    config: bytes
    members: list
    allowed: set = field(default_factory=set)


class Air:
    def __init__(self):
        self.peers = set()
        self.rooms = []
        self.frames = 0

    def packet(self, p, op, seq, data):
        p.writer.write(struct.pack('<IIII', MAGIC, op, seq, len(data)) + data)

    def snapshot(self, p):
        net = bytes(p.room.info) if p.room else bytes(NET_SIZE)
        self.packet(p, 100, 0, struct.pack('<III', p.state, p.reason, p.node & 0xffffffff) + net)

    def publish(self, room):
        room.info[0x67] = len(room.members)
        for member in room.members:
            self.snapshot(member)

    def change(self, p, state, reason=0):
        p.state, p.reason = state, reason
        self.snapshot(p)
        print(f'state player={p.player} state={state} reason={reason}', flush=True)

    def leave(self, p, destroyed=False):
        r = p.room
        for endpoint in p.sockets.values(): endpoint['queue'].clear()
        if not r:
            return
        if p is r.host:
            self.rooms.remove(r)
            for member in list(r.members):
                for endpoint in member.sockets.values(): endpoint['queue'].clear()
                member.room, member.node = None, -1
                self.change(member, 2 if member is p else 4, 3 if destroyed else 4)
        else:
            r.members.remove(p)
            r.info[0x68 + p.node * 0x40:0x68 + (p.node + 1) * 0x40] = bytes(0x40)
            p.room, p.node = None, -1
            self.change(p, 4, 1)
            self.publish(r)

    def add_node(self, r, p, name, version, idx):
        node = bytearray(0x40)
        put32(node, 0, p.ip)  # LDN uses host-order IPv4; BSD sockaddr uses network bytes.
        node[4:10] = p.mac
        node[10:12] = bytes([idx, 1])
        node[12:44] = name[:32]
        put16(node, 46, version)
        r.info[0x68 + idx * 0x40:0x68 + (idx + 1) * 0x40] = node
        p.node, p.room = idx, r
        r.members.append(p)

    def matches(self, info, filt, channel):
        flags = u32(filt, 0x5c)
        if flags & ~0x3f: return False
        checks = ((1, 0, 8, 0), (2, 16, 16, 16), 
                  (8, 0x20, 6, 0x24), (32, 10, 2, 10))
        if flags & 4 and not (u32(filt, 0x20) & info[0x4b]): return False
        if flags & 16:
            length = filt[0x2a]
            if length > 32 or length != info[0x26] or info[0x27:0x27+length] != filt[0x2b:0x2b+length]: return False
        return (not channel or channel == u16(info, 0x48)) and all(
            not flags & bit or info[dst:dst+n] == filt[src:src+n] for bit, dst, n, src in checks)

    def handle(self, p, op, b):
        if op == 1:  # initialize, unique player per medium
            player, = struct.unpack('<I', b)
            if p.state or player > 7 or any(x is not p and x.player == player for x in self.peers):
                return 98, b''
            p.player = player
            self.change(p, 1)
            return 0, b''
        if not p.state: return 50, b''
        if op in (2, 3):  # open AP / station
            if p.state != 1: return FAIL, b''
            self.change(p, 2 if op == 2 else 4)
        elif op in (4, 5):  # close AP / station
            if p.state not in ((2, 3) if op == 4 else (4, 5)): return FAIL, b''
            self.leave(p)
            p.advertise, p.policy = b'', 0
            p.filters.clear()
            self.change(p, 1)
        elif op == 6:  # create: config32 security68 user48 parameter32 count4 addresses
            if p.state != 2 or len(b) < 184: return FAIL, b''
            config, sec, user, param = b[:32], b[32:100], b[100:148], b[148:180]
            count = u32(b, 180)
            version, maximum = u16(config, 20), config[18]
            if not 1 <= maximum <= 8 or version > 32767 or count > 8 or len(b) != 184 + count*12:
                return FAIL, b''
            if not 16 <= u16(sec, 2) <= 64: return FAIL, b''
            net = bytearray(NET_SIZE)
            net[:16] = config[:16]
            net[16:32] = param[16:32] if any(param) else secrets.token_bytes(16)
            net[0x20:0x26] = p.mac
            ssid = net[16:32].hex().encode()
            net[0x26] = len(ssid)
            net[0x27:0x47] = ssid
            put16(net, 0x48, u16(config, 16) or 6)
            net[0x4a:0x4c] = bytes([3, 2])  # NetworkType LDN bit, independent of private address policy
            net[0x50:0x60] = param[:16] if any(param) else secrets.token_bytes(16)
            put16(net, 0x60, 1)
            net[0x62:0x64] = bytes([p.policy, 1])
            net[0x66] = maximum
            put16(net, 0x26a, len(p.advertise))
            net[0x26c:0x26c+len(p.advertise)] = p.advertise
            allowed = {b[184+i*12+4:184+i*12+10] for i in range(count)}
            r = Room(p, net, sec, config, [], allowed)
            self.rooms.append(r)
            self.add_node(r, p, user, version, 0)
            p.state, p.reason = 3, 0
            self.publish(r)
            print(f'create player={p.player} session={net[16:32].hex()} intent={net[:16].hex()} advertise={p.advertise.hex()}', flush=True)
        elif op == 7:  # scan: channel32 max32 filter96 private32
            if p.state not in (3, 4, 5) or len(b) != 108: return FAIL, b''
            ch, maximum = struct.unpack_from('<II', b)
            if not 1 <= maximum <= 24: return FAIL, b''
            filt = b[8:104]
            if not u32(b, 104):
                filt = bytearray(filt); put32(filt, 92, u32(filt, 92) & 0x37)
            found = [bytes(r.info) for r in self.rooms if r.host is not p and self.matches(r.info, filt, ch)][:maximum]
            if found:
                print(f'scan player={p.player} count={len(found)} session={found[0][16:32].hex()} advertise={found[0][0x26c:0x26c+u16(found[0],0x26a)].hex()}', flush=True)
            return 0, struct.pack('<I', len(found)) + b''.join(found)
        elif op == 8:  # join: NetworkInfo security68 user48 version32 option32
            if p.state != 4 or len(b) != NET_SIZE + 124: return FAIL, b''
            net, sec, user = b[:NET_SIZE], b[NET_SIZE:NET_SIZE+68], b[NET_SIZE+68:NET_SIZE+116]
            version, option = struct.unpack_from('<II', b, NET_SIZE+116)
            r = next((r for r in self.rooms if r.info[:32] == net[:32] and r.info[0x20:0x26] == net[0x20:0x26]), None)
            if not r: return 2, b''
            if len(r.members) >= r.info[0x66] or version != u16(r.info, 0x68+46) or option > 1: return 111, b''
            size = u16(sec, 2)
            if size != u16(r.security, 2) or sec[4:4+size] != r.security[4:4+size]: return 13, b''
            policy = r.info[0x62]
            if policy == 1 or (policy == 2 and p.mac in r.host.filters) or (policy == 3 and p.mac not in r.host.filters): return 13, b''
            if r.allowed and p.mac not in r.allowed: return 13, b''
            idx = next(i for i in range(1, 8) if not r.info[0x68+i*0x40+11])
            self.add_node(r, p, user, version, idx)
            p.state, p.reason = 5, 0
            self.publish(r)
            print(f'join player={p.player} host={r.host.player} session={net[16:32].hex()} nodes={len(r.members)}', flush=True)
        elif op == 9:  # destroy
            if p.state != 3: return FAIL, b''
            self.leave(p, True)
        elif op == 10:
            if p.state != 5: return FAIL, b''
            self.leave(p)
        elif op == 11:
            if p.state not in (2, 3) or len(b) > 384: return FAIL, b''
            p.advertise = b
            if p.room:
                p.room.info[0x26c:0x3ec] = b + bytes(384-len(b))
                put16(p.room.info, 0x26a, len(b))
                self.publish(p.room)
        elif op == 12:
            policy, = struct.unpack('<I', b)
            if p.state not in (2, 3) or policy > 3: return FAIL, b''
            p.policy = policy
            if p.room:
                p.room.info[0x62] = policy
                self.publish(p.room)
        elif op == 13:
            if p.state not in (2, 3) or len(b) != 6: return FAIL, b''
            p.filters.add(b)
        elif op == 14:
            if p.state not in (2, 3): return FAIL, b''
            p.filters.clear()
        elif op == 15:
            ip, = struct.unpack('<I', b)
            if p.state != 3: return FAIL, b''
            target = next((x for x in p.room.members if x is not p and x.ip == ip), None)
            if not target: return 2, b''
            self.leave(target)
            self.change(target, 4, 5)
        elif op == 16:
            self.leave(p)
            p.sockets.clear()
            p.player = -1
            self.change(p, 0)
        elif op == 20:  # virtual BSD UDP socket; no OS IP socket is ever opened
            family, kind, protocol = struct.unpack('<III', b)
            if family != 2 or kind & 0xf != 2 or protocol not in (0, 17): return 43, b''
            if len(p.sockets) >= 64: return 24, b''
            fd = p.next_fd; p.next_fd += 1
            p.sockets[fd] = dict(port=0, queue=deque(), event=None)
            print(f'socket player={p.player} fd={fd} family={family} type={kind} protocol={protocol}', flush=True)
            return 0, struct.pack('<I', fd)
        elif op == 21:  # bind fd, sockaddr_in (BSD len/family, network-order port/IP)
            fd = u32(b); s = p.sockets.get(fd)
            if not s or len(b) != 20: return 9, b''
            if b[5] != 2 or int.from_bytes(b[8:12], 'big') not in (0, p.ip): return 49, b''
            port = int.from_bytes(b[6:8], 'big') or (40000+fd)
            if any(x is not s and x['port'] == port and not (s.get('reuseport') and x.get('reuseport')) for x in p.sockets.values()): return 48, b''
            s['port'] = port
            print(f'bind player={p.player} fd={fd} port={port}', flush=True)
        elif op == 22:  # send fd + sockaddr + payload, membership-isolated
            fd = u32(b); s = p.sockets.get(fd)
            if not s or s['event'] is not None: return 9, b''
            if not p.room or p.state not in (3, 5): return 50, b''
            if len(b) < 20 or len(b) > 20+65507 or b[5] != 2: return FAIL, b''
            dest, port = int.from_bytes(b[8:12], 'big'), int.from_bytes(b[6:8], 'big')
            if dest not in [x.ip for x in p.room.members] + [0xffffffff, 0x0a0d00ff]: return 51, b''
            if not s['port']: s['port'] = 40000+fd
            source = bytes([16, 2]) + s['port'].to_bytes(2, 'big') + p.ip.to_bytes(4, 'big') + bytes(8)
            p.sent += 1
            p.sent_bytes += len(b)-20
            for x in p.room.members:
                if x is p or dest not in (x.ip, 0xffffffff, 0x0a0d00ff): continue
                for recv in x.sockets.values():
                    if recv['port'] == port and recv['event'] is None:
                        if len(recv['queue']) >= 256:
                            x.dropped += 1
                            continue
                        recv['queue'].append(source + b[20:])
                        x.queue_peak = max(x.queue_peak, len(recv['queue']))
                        self.frames += 1
            if self.frames and self.frames & (self.frames-1) == 0:
                print(f'data frames={self.frames} session={p.room.info[16:32].hex()}', flush=True)
            return 0, struct.pack('<I', len(b)-20)
        elif op == 23:
            fd, = struct.unpack('<I', b); s = p.sockets.get(fd)
            if not s: return 9, b''
            if not s['queue']: return 35, b''
            p.received += 1
            if p.received & (p.received-1) == 0:
                print(f'recv player={p.player} frames={p.received} session={p.room.info[16:32].hex() if p.room else "-"}', flush=True)
            packet = s['queue'].popleft()
            p.received_bytes += len(packet)-16
            return 0, packet
        elif op == 24:
            fd, = struct.unpack('<I', b)
            if fd not in p.sockets: return 9, b''
            del p.sockets[fd]
        elif op == 25:  # nonblocking poll snapshot; timeout is handled in the client
            if len(b) % 8 or len(b) > 512: return FAIL, b''
            out = bytearray(b)
            for off in range(0, len(b), 8):
                fd, events = struct.unpack_from('<ih', b, off)
                s = p.sockets.get(fd)
                ready = 0 if fd < 0 else 32 if not s else ((1 if s['queue'] or s['event'] else 0) | 4) & events
                struct.pack_into('<h', out, off+6, ready)
            return 0, bytes(out)
        elif op == 26:
            fd, = struct.unpack('<I', b); s = p.sockets.get(fd)
            if not s: return 9, b''
            return 0, bytes([16, 2]) + s['port'].to_bytes(2, 'big') + p.ip.to_bytes(4, 'big') + bytes(8)
        elif op == 27:  # EventFd initial value64, flags32
            value, flags = struct.unpack('<QI', b)
            if len(p.sockets) >= 64: return 24, b''
            fd = p.next_fd; p.next_fd += 1
            p.sockets[fd] = dict(port=0, queue=deque(), event=value)
            return 0, struct.pack('<I', fd)
        elif op in (28, 29):
            fd = u32(b); s = p.sockets.get(fd)
            if not s or s['event'] is None: return 9, b''
            if op == 28:
                if not s['event']: return 35, b''
                val = s['event']; s['event'] = 0
                return 0, struct.pack('<Q', val)
            value = struct.unpack_from('<Q', b, 4)[0]
            if value == 0xffffffffffffffff or s['event'] + value >= 0xffffffffffffffff: return FAIL, b''
            s['event'] += value
        elif op == 30:  # socket options: only known UDP options are accepted by the adapter
            if len(b) != 16 or u32(b) not in p.sockets: return 9, b''
            fd, level, option, value = struct.unpack('<IIII', b)
            if level == 0xffff and option == 0x200: p.sockets[fd]['reuseport'] = bool(value)
        else:
            return 45, b''
        return 0, b''

    async def metrics(self):
        # Wall time is shared by all local hosts. Report delivery and backlog
        # independently of game scene progress; a live frame loop is not PIA health.
        start = time.monotonic()
        while True:
            await asyncio.sleep(5)
            for p in sorted(self.peers, key=lambda x: x.player):
                queued = sum(len(s['queue']) for s in p.sockets.values())
                session = p.room.info[16:32].hex() if p.room else '-'
                print(f'metric t={time.monotonic()-start:.3f} player={p.player} '
                      f'state={p.state} session={session} sent={p.sent} '
                      f'sent_bytes={p.sent_bytes} recv={p.received} '
                      f'recv_bytes={p.received_bytes} queued={queued} '
                      f'queue_peak={p.queue_peak} dropped={p.dropped}', flush=True)

    async def client(self, reader, writer):
        p = Peer(writer)
        self.peers.add(p)
        try:
            while True:
                magic, op, seq, size = struct.unpack('<IIII', await reader.readexactly(16))
                if magic != MAGIC or size > MAX_PACKET:
                    break
                payload = await reader.readexactly(size)
                try:
                    err, data = self.handle(p, op, payload)
                except (ValueError, IndexError, struct.error):
                    err, data = FAIL, b''
                self.packet(p, op | 0x80000000, seq, struct.pack('<I', err) + data)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, BrokenPipeError):
            pass
        finally:
            self.leave(p)
            self.peers.discard(p)
            writer.close()


async def run(path):
    # Refuse existing paths: never unlink a running medium or unrelated file.
    if path.exists():
        raise RuntimeError(f'path already exists: {path}')
    air = Air()
    server = await asyncio.start_unix_server(air.client, path=str(path), limit=MAX_PACKET+16)
    os.chmod(path, 0o600)
    stopped = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
    metrics = asyncio.create_task(air.metrics())
    print(f'ready unix={path}', flush=True)
    try:
        async with server:
            await stopped.wait()
    finally:
        metrics.cancel()
        for p in list(air.peers): p.writer.close()
        path.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.socket))

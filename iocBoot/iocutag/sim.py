#!/usr/bin/env python3
"""
Simulated timing device

Each tick sends one block:
  [0:20)    trailer: sec, nsec, tag, value, seq  (5 x uint32, big-endian)
  [20:...)  1024 x int32 waveform

tag is the "actual flavor" bitfield: 0x10 LBEG, 0x20 MPEG, 0 = beam off.
"""

import time
import struct
import logging
import asyncio

from numpy.random import randn
import numpy as np

try:
    import uvloop
except ImportError:
    uvloop = None  # default asyncio only reaches ~95Hz at --rate 120

_log = logging.getLogger(__name__)

LBEG = 0x10
MPEG = 0x20


def getargs():
    from argparse import ArgumentParser
    P = ArgumentParser()
    P.add_argument('--bind', default='0.0.0.0:5678')
    P.add_argument('--rate', type=float, default=120.0, help='tick rate in Hz (default 120)')
    P.add_argument('-v', '--verbose', action='store_const', default=logging.INFO, const=logging.DEBUG)
    return P

class Server:
    def __init__(self, rate=120.0):
        self.clients = {}
        # control word, set by the IOC (message 1):
        # bit 0 - beam on
        # bit 1 - source LBEG/MPEG
        # bit 2 - auto toggle source
        self.ctrl = 0
        self.tick_period = 1.0/rate
        self.period_ticks = 1   # ticks between auto-toggle flips
        self._tick_count = 0
        self.seq = 0
        self._T = np.linspace(0.0, 10.0, 1024)

        self._tick = asyncio.ensure_future(self.tick())

    async def tick(self):
        try:
            while True:
                if self.ctrl&4:
                    self._tick_count += 1
                    if self._tick_count >= max(self.period_ticks, 1):
                        self.ctrl ^= 2 # auto toggle source
                        self._tick_count = 0
                else:
                    self._tick_count = 0

                await asyncio.sleep(self.tick_period)
                sec, nsec = divmod(time.time(), 1.0)
                sec, nsec = int(sec), int(nsec*1e9)
                self.seq = (self.seq + 1) & 0xffffffff

                T = self._T
                V = randn(*T.shape)*2.0

                amp = 0.0
                mean = 0.0
                std = 1.0

                tag = 0
                if self.ctrl&1:
                    # beam on
                    if self.ctrl&2:
                        tag = MPEG # H- -> WNR
                        amp, mean, std = 10.0, 3.0, 1.0
                    else:
                        tag = LBEG # H- -> PSR
                        amp, mean, std = 15.0, 6.6, 1.5

                value = {LBEG: 111, MPEG: 222}.get(tag, 0)

                amp += randn()/5.0
                mean += randn()/5.0
                std += randn()/5.0
                V += amp * np.exp(-(T-mean)**2/(2*std**2))

                V = (V*20.0).astype('>i4')

                trailer = struct.pack('>IIIII', sec, nsec, tag, value, self.seq)
                body = trailer + V.tobytes()
                M = struct.pack('>2sHI', b'PS', 0, len(body)) + body

                for sock in self.clients.values():
                    sock.write(M)
                for peer, sock in self.clients.items():
                    try:
                        await asyncio.wait_for(sock.drain(), 0.5)
                    except asyncio.TimeoutError:
                        _log.error('%s TX stalled', peer)
                        sock.close()

        except:
            _log.exception('Tick fails')

    async def handle(self, reader, writer):
        peer = writer.get_extra_info('peername')
        _log.info('%s connects', peer)
        try:
            self.clients[peer] = writer

            while True:
                H = await reader.readexactly(8)
                PS, msgid, blen = struct.unpack('>2sHI', H)
                if PS!=b'PS':
                    raise RuntimeError('Corrupt header '+repr(H))
                B = await reader.readexactly(blen)
                _log.debug("%s sends %d %s", peer, msgid, B)

                if msgid==1: # set control word
                    self.ctrl, = struct.unpack('>I', B[:4])
                    _log.info('%s CTRL=%x', peer, self.ctrl)
                elif msgid==2: # set auto-toggle period, in ms (rounds to whole ticks)
                    period_ms, = struct.unpack('>I', B[:4])
                    self.period_ticks = max(1, round(period_ms/1000.0/self.tick_period))
                    self._tick_count = 0
                    _log.info('%s PERIOD=%dms (%d ticks)', peer, period_ms, self.period_ticks)

        except Exception as e:
            _log.exception('%s error', peer)
        finally:
            _log.info('%s disconnects', peer)
            self.clients.pop(peer)

async def main(args):
    iface, _sep, port = args.bind.partition(':')
    serv = Server(rate=args.rate)

    listener = await asyncio.start_server(serv.handle, iface, int(port or '5678'))

    _log.info('Serving from %s at %.1fHz', listener.sockets[0].getsockname(), args.rate)
    async with listener:
        await listener.serve_forever()

if __name__=='__main__':
    args = getargs().parse_args()
    logging.basicConfig(level=args.verbose)
    if uvloop is not None:
        uvloop.install()
    else:
        _log.warning('uvloop not installed; tick rates near 120Hz may fall short (pip install uvloop)')
    asyncio.run(main(args))

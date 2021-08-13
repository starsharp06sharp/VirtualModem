#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio

from cmd_processor import dispatch_command
from common import (Mode, MsgType, QueueMessage, RespMode, VConnEventType,
                    VConnState, phone2modem)
from virtual_connection import VirtualConnection


class Modem(object):
    def __init__(self, id, phone, bps):
        super().__init__()
        self.id = id
        self.phone = phone
        self.bps = bps
        self.activated = False
        self.vconn = None
        self.clear_status()

    def clear_status(self):
        self.mode = Mode.CMD
        self.registers = [0] * 256
        self.msg_recvq = asyncio.Queue()
        self.com_sendq = asyncio.Queue()
        # buffer for data received from the remote in CMD mode
        self.bufferd_send_data = b''
        # make virtual connection half closed
        if self.vconn:
            self.vconn.status = VConnState.CLOSED
        self.vconn = None

    async def main_loop(self):
        while True:
            msg = await self.msg_recvq.get()
            if self.mode == Mode.DATA:
                if msg.type == MsgType.ComData:
                    # b'+++': escape to command mode
                    # The escape sequence was preceded and followed by one second of silence
                    if msg.data == b'+++':
                        self.mode = Mode.CMD
                    else:
                        await self.vconn.push_data(self, msg.data)
                elif msg.type == MsgType.VConnData:
                    await self.com_sendq.put(msg.data)
                else:
                    assert msg.type == MsgType.VConnEvent
                    assert msg.data == VConnEventType.HANG
                    self.vconn = None
                    self.com_sendq.put(b'NO CARRIER\r')
                    self.mode = Mode.CMD
            else:
                if msg.type == MsgType.ComData:
                    res = await dispatch_command(self, msg.data)
                    if res:
                        await self.com_sendq.put(res)
                    # if transferred to data mode, check if there is a buffered data
                    if self.mode == Mode.DATA and self.bufferd_send_data:
                        await self.com_sendq.put(self.bufferd_send_data)
                        self.bufferd_send_data = b''
                elif msg.type == MsgType.VConnData:
                    # CMD mode, just buffer it
                    self.bufferd_send_data += msg.data
                else:
                    assert msg.type == MsgType.VConnEvent
                    if msg.data == VConnEventType.HANG:
                        print(
                            f'{self.id}|Remote close connection during CMD mode')
                    else:
                        self.com_sendq.put(b'RING\r')

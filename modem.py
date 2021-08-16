#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio

from cmd_processor import dispatch_command
from common import (Mode, MsgType, QueueMessage, VConnEventType, VConnState,
                    clear_queue)


class Modem(object):
    def __init__(self, id, phone, bps):
        super().__init__()
        self.id = id
        self.phone = phone
        self.bps = bps
        self.activated = False
        self.msg_recvq = asyncio.Queue()
        self.com_sendq = asyncio.Queue()
        self.vconn = None
        self.clear_status()

    def clear_status(self):
        self.mode = Mode.CMD
        self.registers = [0] * 256
        self.cmd_recv_buffer = b''
        self.data_recv_buffer = b''
        clear_queue(self.msg_recvq)
        clear_queue(self.com_sendq)
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
                    await self.handle_com_data(msg.data)
                elif msg.type == MsgType.VConnData:
                    await self.com_sendq.put(msg.data)
                elif msg.type == MsgType.EndDataModeEvent:
                    await self.try_end_data_mode()
                else:
                    assert msg.type == MsgType.VConnEvent
                    assert msg.data == VConnEventType.HANG
                    self.vconn = None
                    await self.com_sendq.put(b'NO CARRIER\r')
                    self.mode = Mode.CMD
                    print(
                        f'{self.id}|Remote close connection during DATA mode')
            else:
                if msg.type == MsgType.ComData:
                    await self.handle_at_command(msg.data)
                elif msg.type == MsgType.VConnData:
                    # CMD mode, just buffer it
                    self.bufferd_send_data += msg.data
                else:
                    assert msg.type == MsgType.VConnEvent
                    if msg.data == VConnEventType.HANG:
                        self.vconn = None
                        await self.com_sendq.put(b'NO CARRIER\r')
                        print(
                            f'{self.id}|Remote close connection during CMD mode')
                    else:
                        await self.com_sendq.put(b'RING\r')

    async def handle_at_command(self, data):
        self.cmd_recv_buffer += data
        while True:
            ri = self.cmd_recv_buffer.find(b'\r')
            if ri < 0:
                break
            cmd = self.cmd_recv_buffer[:ri].strip()
            self.cmd_recv_buffer = self.cmd_recv_buffer[ri+1:]
            if not cmd:
                continue
            res = await dispatch_command(self, cmd)
            if res:
                await self.com_sendq.put(res)
            # if transferred to data mode, check if there is a buffered data
            if self.mode == Mode.DATA and self.bufferd_send_data:
                await self.com_sendq.put(self.bufferd_send_data)
                self.bufferd_send_data = b''
                self.cmd_recv_buffer = b''
                break

    async def try_end_data_mode(self):
        if not self.data_recv_buffer:
            return
        # are still the escape sequence after one second
        if self.data_recv_buffer == b'+++':
            print(f'{self.id}|Return to CMD mode')
            self.mode = Mode.CMD
            await self.com_sendq.put(b'OK\r')
        else:
            await self.vconn.push_data(self, self.data_recv_buffer)
            self.data_recv_buffer = b''

    async def handle_com_data(self, data):
        self.data_recv_buffer += data
        # b'+++': escape to command mode
        # The escape sequence was preceded and followed by one second of silence
        if self.data_recv_buffer in {b'+', b'++'}:
            return
        if self.data_recv_buffer == b'+++':
            async def send_check_msg_asecond_later():
                await asyncio.sleep(0.5)
                msg = QueueMessage(MsgType.EndDataModeEvent, b'')
                await self.msg_recvq.put(msg)
            asyncio.create_task(send_check_msg_asecond_later())
            return

        await self.vconn.push_data(self, self.data_recv_buffer)
        self.data_recv_buffer = b''

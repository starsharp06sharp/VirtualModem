#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio

from common import MsgType, QueueMessage, VConnEventType, VConnState
from speed_limiter import SpeedLimiter


class VirtualConnection(object):
    def __init__(self, m1, m2):
        super().__init__()
        self.modems = (m1, m2)
        self.status = VConnState.CONNECTING
        self.bps = min(m1.bps, m2.bps)
        self.speed_limiter = [SpeedLimiter(self.bps), SpeedLimiter(self.bps)]
        self.dial_answered = asyncio.Event()

    def _get_remote_modem_index(self, cur_modem):
        for i in range(len(self.modems)):
            if self.modems[i].id != cur_modem.id:
                return i

    async def push_data(self, cur_modem, data):
        '''push data to remote modem'''
        if not data:
            return
        ri = self._get_remote_modem_index(cur_modem)
        await self.speed_limiter[ri].simulate_send_delay(len(data))
        msg = QueueMessage(MsgType.VConnData, data)
        await self.modems[ri].msg_recvq.put(msg)
        return

    async def dial(self, cur_modem) -> bool:
        ri = self._get_remote_modem_index(cur_modem)
        msg = QueueMessage(MsgType.VConnEvent, VConnEventType.DIAL)
        await self.modems[ri].msg_recvq.put(msg)
        await self.dial_answered.wait()
        self.dial_answered.clear()
        return self.status == VConnState.CONNECTED

    def answer(self):
        self.status = VConnState.CONNECTED
        self.dial_answered.set()
        return

    async def close(self, cur_modem):
        ri = self._get_remote_modem_index(cur_modem)
        self.status = VConnState.CLOSED
        msg = QueueMessage(MsgType.VConnEvent, VConnEventType.HANG)
        await self.modems[ri].msg_recvq.put(msg)
        for m in self.modems:
            m.vconn = None

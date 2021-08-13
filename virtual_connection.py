#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from common import (
    VConnState,
)
from speed_limiter import SpeedLimiter

class VirtualConnection(object):
    def __init__(self, m1, m2):
        super().__init__()
        self.modems = (m1, m2)
        self.data = [b'', b'']
        self.status = VConnState.CONNECTING
        self.bps = min(m1.bps, m2.bps)
        self.speed_limiter = [SpeedLimiter(self.bps), SpeedLimiter(self.bps)]

    def push_data(self, cur_modem, data):
        '''push data to remote modem'''
        for i in range(len(self.modems)):
            if self.modems[i].id == cur_modem.id:
                continue
            print(f'{cur_modem.id}>{self.modems[i].id}|{repr(data)}')
            self.data[i] += data
            return

    def fetch_data(self, cur_modem):
        '''fetch pushed data'''
        for i in range(len(self.modems)):
            if self.modems[i].id == cur_modem.id:
                if not self.data[i]:
                    return b''
                data = self.data[i]
                print(f'{cur_modem.id}<{self.modems[(i+1)%2].id}|{repr(data)}')
                self.data[i] = b''
                return data
        return b''
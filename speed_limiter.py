#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import random
from datetime import datetime


class SpeedLimiter(object):
    def __init__(self, bps):
        '''
        init speed limit window, structure:
        current second: [bytes left on 0ms, bytes left on 1ms, ... 999ms]
        '''
        super().__init__()
        self.ts = int(datetime.now().timestamp())
        byte_ps = round(bps / 8)
        normal_window_bytes = int(byte_ps / 1000)
        expanded_window_bytes = normal_window_bytes + 1
        expanded_window_num = int(byte_ps) - normal_window_bytes * 1000
        normal_window_num = 1000 - expanded_window_num
        self.window_tmpl = [normal_window_bytes] * normal_window_num + \
            [expanded_window_bytes] * expanded_window_num
        random.shuffle(self.window_tmpl)
        self.bytes_left = self.window_tmpl.copy()

    def try_reduce_window_at(self, tms, byte_count):
        ts = int(tms / 1000)
        if self.ts != ts:
            self.ts = ts
            self.bytes_left = self.window_tmpl.copy()
        ms = tms - ts * 1000
        self.bytes_left[ms] -= byte_count
        if self.bytes_left[ms] < 0:
            left_byte = -self.bytes_left[ms]
            self.bytes_left[ms] = 0
            return left_byte
        return 0

    async def simulate_send_delay(self, byte_count):
        tms = int(datetime.now().timestamp() * 1000)
        sleep_to_tms = tms - 1
        while byte_count > 0:
            sleep_to_tms += 1
            byte_count = self.try_reduce_window_at(sleep_to_tms, byte_count)
        if sleep_to_tms > tms:
            sleep_time = sleep_to_tms / 1000 - datetime.now().timestamp()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

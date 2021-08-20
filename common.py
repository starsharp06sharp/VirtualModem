#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
import asyncio
import contextvars
import functools
import logging
import logging.handlers
from collections import namedtuple
from enum import Enum

import config

fileHandler = logging.handlers.RotatingFileHandler(
    'log/network.log', encoding='utf-8', maxBytes=16*1024*1024, backupCount=9)
fileHandler.setLevel(config.log_level)
fileHandler.setFormatter(logging.Formatter(
    u'%(asctime)s|%(levelname)s|%(filename)s|%(lineno)3d:%(message)s'))

logger = logging.getLogger('logger')
logger.setLevel(config.log_level)
logger.addHandler(fileHandler)


class Mode(Enum):
    CMD = 0
    DATA = 1


class VConnState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    CLOSED = 2


class MsgType(Enum):
    ComData = 0
    ComEvent = 1
    VConnData = 2
    VConnEvent = 3


class CommEventType(Enum):
    PortPowerOff = 0
    DataModeSeemsEnd = 1


class VConnEventType(Enum):
    DIAL = 0
    HANG = 1


QueueMessage = namedtuple('QueueMessage', ('type', 'data'))

phone2modem = {}

support_bps = {
    2400,
    4800,
    9600,
    14400,
    19200,
    28800,
    33600,
    56000,
}


def clear_queue(q: asyncio.Queue):
    while True:
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            return


if hasattr(asyncio, 'to_thread'):
    asyncio_to_thread = asyncio.to_thread
else:
    async def asyncio_to_thread(func, /, *args, **kwargs):
        loop = asyncio.events.get_running_loop()
        ctx = contextvars.copy_context()
        func_call = functools.partial(ctx.run, func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)

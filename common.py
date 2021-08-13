#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
import logging
import logging.handlers
from collections import defaultdict, namedtuple
from enum import Enum

fileHandler = logging.handlers.RotatingFileHandler(
    'log/network.log', encoding='utf-8', maxBytes=16*1024*1024, backupCount=9)
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(logging.Formatter(
    u'%(asctime)s|%(levelname)s|%(filename)s|%(lineno)3d:%(message)s'))

logger = logging.getLogger('logger')
logger.setLevel(logging.DEBUG)
logger.addHandler(fileHandler)


class Mode(Enum):
    CMD = 0
    DATA = 1


class RespMode(Enum):
    ECHO = -1
    CODE = 0
    MSG = 1


class VConnState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    CLOSED = 2

class MsgType(Enum):
    ComData = 0
    VConnData = 1
    VConnEvent = 2

class VConnEventType(Enum):
    DIAL = 0
    HANG = 1

QueueMessage = namedtuple('QueueMessage', ('type', 'data'))

modems = []
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

code_msg_dict = defaultdict(lambda: b'UNKNOWN RETCODE', {
    0: b'OK',
    1: b'RING',
    3: b'NO CARRIER',
    4: b'ERROR',
    5: b'CONNECT 1200',
    6: b'NO DIALTONE',
    7: b'BUSY',
    8: b'NO ANSWER',
    9: b'CONNECT 0600',
    10: b'CONNECT 2400',
    11: b'CONNECT 4800',
    12: b'CONNECT 9600',
    13: b'CONNECT 7200',
    14: b'CONNECT 12000',
    15: b'CONNECT 14400',
    16: b'CONNECT 19200',
    17: b'CONNECT 38400',
    18: b'CONNECT 57600',
    19: b'CONNECT 115200',
    22: b'CONNECT 75TX/1200RX',
    23: b'CONNECT 1200TX/75RX',
    24: b'DELAYED',
    32: b'BLACKLISTED',
    33: b'FAX',
    35: b'DATA',
    40: b'CARRIER 300',
    44: b'CARRIER 1200/75',
    45: b'CARRIER 75/1200',
    46: b'CARRIER 1200',
    47: b'CARRIER 2400',
    48: b'CARRIER 4800',
    49: b'CARRIER 7200',
    50: b'CARRIER 9600',
    51: b'CARRIER 12000',
    52: b'CARRIER 14400',
    53: b'CARRIER 16800',
    54: b'CARRIER 19200',
    55: b'CARRIER 21600',
    56: b'CARRIER 24000',
    57: b'CARRIER 26400',
    58: b'CARRIER 28800',
    59: b'CARRIER 31200',
    60: b'CARRIER 33600',
    61: b'CONNECT 16800',
    62: b'CONNECT 21600',
    63: b'CONNECT 24000',
    64: b'CONNECT 26400',
    65: b'CONNECT 28800',
    66: b'CONNECT 33600',
})


def translate_resp(mode, cmd, res):
    if isinstance(res, bytes):
        return res
    if isinstance(res, str):
        return res.encode('ascii')
    if mode == RespMode.CODE:
        return str(res).encode('ascii')
    if mode == RespMode.MSG:
        global code_msg_dict
        return code_msg_dict[res]
    return cmd

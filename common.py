#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
import logging
import logging.handlers
from collections import namedtuple
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

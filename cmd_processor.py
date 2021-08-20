#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio

import sound
from common import Mode, VConnState, phone2modem
from virtual_connection import VirtualConnection


async def ATE(modem, cmd) -> bytes:
    # support text mode only
    if cmd == b'ATE0V1':
        return b'OK'
    return b'ERROR'


async def ATS(modem, cmd) -> bytes:
    expr = list(map(int, cmd[3:].split(b'=')))
    reg_index = expr[0]
    if len(expr) == 1:
        # Load
        return str(modem.registers[reg_index]).encode('ascii')
    else:
        # Store
        value = expr[1]
        modem.registers[reg_index] = value
        return b'OK'


async def ATA(modem, cmd) -> bytes:
    if modem.vconn and modem.vconn.status != VConnState.CLOSED:
        modem.vconn.answer()
        modem.mode = Mode.DATA
        return f'CONNECT {modem.vconn.bps}'.encode('ascii')
    else:
        modem.vconn = None
        return b'BUSY'


async def ATH(modem, cmd) -> bytes:
    if modem.vconn:
        await modem.vconn.close(modem)
    return b'OK'


async def ATO(modem, cmd) -> bytes:
    if not modem.vconn:
        return b'NO CARRIER'
    modem.mode = Mode.DATA
    return f'CARRIER {modem.vconn.bps}'.encode('ascii')


def build_vconn(from_m, to_phone):
    # find remote modem
    try:
        to_m = phone2modem[to_phone]
    except KeyError:
        raise ValueError(f'unkown phone {to_phone}')
    # cant call yourself
    if from_m.id == to_m.id:
        raise ValueError('cant call yourself')
    # check both modem is activated and idle
    if not from_m.activated or not to_m.activated:
        raise RuntimeError('modem is deactivated')
    if from_m.vconn or to_m.vconn:
        raise RuntimeError('modem is busy line')
    # create virtual connection
    from_m.vconn = VirtualConnection(from_m, to_m)
    to_m.vconn = from_m.vconn
    return from_m.vconn


def cancel_vconn(vconn):
    for m in vconn.modems:
        m.vconn = None


async def ATD(modem, cmd) -> bytes:
    phone_number = cmd[4:].decode('ascii')
    await sound.play_dial_tone(phone_number)
    try:
        vconn = build_vconn(modem, phone_number)
    except BaseException as e:
        print(f'{modem.id}|Dial to {phone_number} failed: {e}')
        return b'BUSY'

    try:
        ok = await vconn.dial(modem)
    except TimeoutError:
        cancel_vconn(vconn)
        print(f'{modem.id}|Dial to {phone_number} failed: timeout')
        return b'NO ANSWER'
    if not ok:
        cancel_vconn(vconn)
        print(f'{modem.id}|Dial to {phone_number} failed: refused by remote')
        return b'BUSY'

    await sound.play_handshake_sound(vconn.bps)
    print(f'{modem.id}|Dial to {phone_number} success: {modem.vconn.bps}bps')
    modem.mode = Mode.DATA
    return f'CONNECT {modem.vconn.bps}'.encode('ascii')


cmd2func = [
    (b'ATE', ATE),
    (b'ATS', ATS),
    (b'ATA', ATA),
    (b'ATH', ATH),
    (b'ATO', ATO),
    # P for 'Pulse dial', T for 'Tone dial'
    (b'ATDP', ATD),
    (b'ATDT', ATD),
]


async def dispatch_command(modem, cmd) -> bytes:
    global cmd2func
    for prefix, func in cmd2func:
        if cmd.startswith(prefix):
            return await func(modem, cmd) + b'\r'

    if cmd != b'AT':
        # Unknown command
        print(f'{modem.id}|Unknown cmd:{cmd!r}')
    return b'OK\r'

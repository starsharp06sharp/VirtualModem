#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio

from common import Mode, VConnState, phone2modem


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
        await modem.vconn.close()
    return b'OK'


def build_vconn(modem, phone):
    # find remote modem
    try:
        to_m = phone2modem[phone]
    except KeyError:
        raise ValueError(f'unkown phone {phone}')
    # check both modem is activated and idle
    if not self.activated or not to_m.activated:
        raise RuntimeError('modem is deactivated')
    if self.vconn or to_m.vconn:
        raise RuntimeError('modem is busy line')
    # create virtual connection
    self.vconn = VirtualConnection(self, to_m)
    to_m.vconn = self.vconn
    return self.vconn


def cancel_vconn(vconn):
    for m in vconn.modems:
        m.vconn = None


async def ATD(modem, cmd) -> bytes:
    phone_number = cmd[4:].decode('ascii')
    try:
        vconn = build_vconn(modem, phone_number)
    except BaseException as e:
        print(f'{modem.id}|Dial to {phone_number} failed: {e}')
        return b'BUSY'

    try:
        ok = await asyncio.wait_for(asyncio.shield(vconn.dial()), 3)
    except asyncio.TimeoutError:
        cancel_vconn(vconn)
        print(f'{modem.id}|Dial to {phone_number} failed: timeout')
        return b'NO ANSWER'
    if not ok:
        cancel_vconn(vconn)
        print(f'{modem.id}|Dial to {phone_number} failed: refused by remote')
        return b'BUSY'

    return f'CONNECT {modem.vconn.bps}'.encode('ascii')


cmd2func = [
    (b'ATE', ATE),
    (b'ATS', ATS),
    (b'ATA', ATA),
    (b'ATH', ATH),
    # TODO: ATO 没有链接时注意报错
    # P for 'Pulse dial', T for 'Tone dial'
    (b'ATDP', ATD),
    (b'ATDT', ATD),
]


async def dispatch_command(modem, cmd) -> bytes:
    global cmd2func
    assert cmd.startswith(b'AT')

    for prefix, func in cmd2func:
        if cmd.startswith(prefix):
            return await func(modem, cmd) + b'\r'
    # Unknown command
    print(f'{modem.id}|Unknown cmd:{repr(cmd)}')
    return b'OK\r'

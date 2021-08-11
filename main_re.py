#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket
import selectors
from collections import defaultdict
from enum import Enum
import config


sel = selectors.DefaultSelector()
modems = []
phone2modem = {}


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


class VirtualConnection(object):
    def __init__(self, m1, m2):
        super().__init__()
        self.modems = (m1, m2)
        self.data = [b'', b'']
        self.status = VConnState.CONNECTING
    
    def push_data(self, cur_modem, data):
        for i in range(len(self.modems)):
            if self.modems[i].id != cur_modem.id:
                print(f'{cur_modem.id}>{self.modems[i].id}|{repr(data)}')
                self.data[i] += data
                return
    
    def fetch_data(self, cur_modem):
        for i in range(len(self.modems)):
            if self.modems[i].id != cur_modem.id:
                if not self.data[i]:
                    return b''
                data = self.data[i]
                self.data[i] = b''
                return data
        return b''


class Modem(object):
    def __init__(self, id, phone, bps):
        super().__init__()
        self.id = id
        self.phone = phone
        self.bps = bps
        self.conn = None
        self.recv_buffer = b''
        self.virtual_conn = None
        self.clear_status()

    def set_conn(self, conn):
        self.conn = conn
        self.recv_buffer = b''

    def clear_status(self):
        self.mode = Mode.CMD
        self.resp_mode = RespMode.MSG
        self.registers = [0] * 256
        # make virtual_conn half closed
        if self.virtual_conn:
            self.virtual_conn.status = VConnState.CLOSED
        self.virtual_conn = None

    def virtual_connect(self, phone) -> bool:
        # find remote modem
        try:
            to_m = phone2modem[phone]
        except KeyError:
            raise ValueError(f'unkown phone {phone}')
        # check both modem is activated and idle
        if not self.conn or not to_m.conn:
            raise RuntimeError('modem is deactivated')
        if self.virtual_conn or to_m.virtual_conn:
            raise RuntimeError('already got connected')
        # create virtual connection
        self.virtual_conn = VirtualConnection(self, to_m)
        to_m.virtual_conn = self.virtual_conn
        # TODO: ring remote_modem's bell
        # TODO: make virtual connection establishing

    def close_conn(self):
        print(f'====== Modem{self.id} End ======')
        sel.unregister(self.conn)
        self.conn.close()
        self.conn = None

    def recv_data(self, conn):
        data = self.conn.recv(4096)
        if not data:
            self.close_conn()
            return
        self.recv_buffer += data
        while self.recv_buffer:
            if self.mode == Mode.DATA:
                pindex = self.recv_buffer.find(b'+++')
                if pindex >= 0:
                    package = self.recv_buffer[:pindex]
                    self.recv_buffer = self.recv_buffer[pindex+3:]
                    self.mode = Mode.CMD
                else:
                    package = self.recv_buffer
                    self.recv_buffer = b''
                self.virtual_conn.push_data(self, package)

            else:
                rindex = self.recv_buffer.find(b'\r')
                if rindex >= 0:
                    cmd = self.recv_buffer[:rindex].strip()
                    self.recv_buffer = self.recv_buffer[rindex+1:]
                else:
                    break
                if not cmd:
                    continue
                res = self.dispatch_command(cmd) + b'\r'
                self.conn.sendall(res)

    def dispatch_command(self, cmd):
        res = 0
        if cmd == b'ATE1':
            self.resp_mode = RespMode.ECHO
        elif cmd == b'ATE0V0':
            self.resp_mode = RespMode.CODE
        elif cmd == b'ATE0V1':
            self.resp_mode = RespMode.MSG
        elif cmd.startswith(b'ATS'):
            expr = list(map(int, cmd[3:].split(b'=')))
            reg_index = expr[0]
            if len(expr) == 1:
                # Load
                res = str(self.registers[reg_index])
            else:
                # Store
                value = expr[1]
                self.registers[reg_index] = value
        # P for 'Pulse dial', T for 'Tone dial'
        elif cmd.startswith(b'ATDT') or cmd.startswith(b'ATDP'):
            phone_number = cmd[4:].decode('ascii')
            try:
                self.virtual_connect(phone_number)
            except BaseException as e:
                print(f'Dial to {phone_number} failed: {e}')
                res = 7
            else:
                # TODO: do this until self.virtual_conn.status == VConnState.CLOSED 
                self.mode = Mode.DATA
                res = 66
        elif cmd == b'ATA':
            if self.virtual_conn.status != VConnState.CLOSED:
                self.virtual_conn.status = VConnState.CONNECTED
                self.mode = Mode.DATA
            else:
                self.virtual_conn = None
                res = 8

        res = translate_resp(self.resp_mode, cmd, res)
        print(f'{self.id}|{repr(cmd)}|{repr(res)}')
        return res

    def try_send_data(self):
        if not self.conn:
            return
        if self.mode != Mode.DATA:
            return
        if not self.virtual_conn:
            return
        data = self.virtual_conn.fetch_data(self)
        if data:
            print(f'{self.id}:{repr(data)}') # TODO: WTF? sendall doesnt work
            self.conn.sendall(data)
        # close this virtual_conn completely when half closed by remote
        if self.virtual_conn.status == VConnState.CLOSED:
            self.virtual_conn = None


def create_accept_func(m):
    def accept_fun(sock):
        print(f'====== Modem{m.id} Start ======')
        conn, addr = sock.accept()
        m.set_conn(conn)
        sel.register(conn, selectors.EVENT_READ, m.recv_data)
    return accept_fun


def main():
    id = 0
    for modem_cfg in config.modems:
        # create modem object
        m = Modem(id, modem_cfg['phone'], modem_cfg['bps'])
        sock = socket.create_server(modem_cfg['address'])
        # register modem object
        sel.register(sock, selectors.EVENT_READ, create_accept_func(m))
        modems.append(m)
        phone2modem[modem_cfg['phone']] = m
        id += 1

    # mian loop
    while True:
        events = sel.select(1)
        # handle events
        for key, mask in events:
            callback = key.data
            callback(key.fileobj)
        # send data
        for m in modems:
            m.try_send_data()
        # TODO: deal with CONNECTING virtual_conn (RING the bell)


if __name__ == '__main__':
    main()

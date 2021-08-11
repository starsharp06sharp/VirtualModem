#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket
import selectors
from collections import defaultdict
from enum import Enum
import config


sel = selectors.DefaultSelector()
modems = []
phone2id = {}


class Mode(Enum):
    CMD = 0
    DATA = 1


class RespMode(Enum):
    ECHO = -1
    CODE = 0
    MSG = 1


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


class Modem(object):
    def __init__(self, id, phone, bps):
        super().__init__()
        self.id = id
        self.phone = phone
        self.bps = bps
        self.conn = None
        self.recv_buffer = b''
        self.send_buffer = b''
        self.clear_status()

    def set_conn(self, conn):
        self.conn = conn
        self.recv_buffer = b''

    def clear_status(self):
        self.mode = Mode.CMD
        self.resp_mode = RespMode.MSG
        self.registers = [0] * 256
        self.remote_modem = None

    def virtual_connect(self, phone) -> bool:
        # find remote modem
        try:
            to_id = phone2id[phone]
            to_m = modems[to_id]
        except (KeyError, IndexError):
            return False
        # check both modem is activated and idle
        if self.remote_modem or to_m.remote_modem:
            return False
        if not self.conn or not to_m.conn:
            return False
        # create virtual link
        self.remote_modem = to_m
        to_m.remote_modem = self
        to_m.send_buffer = b''
        return True

    def push_to_remote(self, package):
        if not self.remote_modem:
            return False
        if not self.remote_modem.conn:
            return False
        self.remote_modem.send_buffer += package
        return True

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
                if rindex >= 0:
                    package = self.recv_buffer[:pindex]
                    self.recv_buffer = self.recv_buffer[rindex+3:]
                    self.mode = Mode.CMD
                else:
                    package = self.recv_buffer
                    self.recv_buffer = b''
                ok = self.push_to_remote(package)
                if not ok:
                    self.close_conn()
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
            ok = self.virtual_connect(phone_number)
            if not ok:
                print(f'Dial to {phone_number} failed.')
                res = 7
            else:
                self.mode = Mode.DATA
                res = 66

        res = translate_resp(self.resp_mode, cmd, res)
        print(f'{repr(cmd)}|{repr(res)}')
        return res

    def try_send_data(self):
        if not self.conn:
            return
        if self.mode != Mode.DATA:
            return
        if not self.send_buffer:
            return
        self.conn.sendall(self.send_buffer)
        self.send_buffer = b''


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
        phone2id[modem_cfg['phone']] = id
        id += 1

    # mian loop
    while True:
        events = sel.select()
        # handle events
        for key, mask in events:
            callback = key.data
            callback(key.fileobj)
        # send data
        for m in modems:
            m.try_send_data()


if __name__ == '__main__':
    main()

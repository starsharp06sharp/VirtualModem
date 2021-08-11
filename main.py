#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket
import socketserver
from collections import defaultdict
from enum import Enum

'''
Test:
==== Handle Start ====
3|'AT\r'
7|'ATE0V1\r'
3|'AT\r'
7|'ATS0=0\r'
3|'AT\r'
7|'ATE0V1\r'
3|'AT\r'
12|'ATDT7557755\r'
3|'+++'
4|'ATH\r'
3|'AT\r'
7|'ATE0V1\r'
3|'AT\r'
7|'ATS0=0\r'
====  Handle End  ====
'''


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


class VirtualModemHandler(socketserver.BaseRequestHandler):
    def __init__(self, *args, **kw):
        self.bufferd = b''
        self.clear_status()
        super().__init__(*args, **kw)

    def clear_status(self):
        self.mode = Mode.CMD
        self.resp_mode = RespMode.MSG
        self.registers = [0] * 256
        self.connection = None

    def handle(self):
        print('==== Handle Start ====')
        no_more_data = False
        while(True):
            data = self.request.recv(4096)
            if not data:
                no_more_data = True
            self.bufferd += data
            while self.bufferd:
                if self.mode == Mode.DATA:
                    pindex = self.bufferd.find(b'+++')
                    if rindex >= 0:
                        res = self.bufferd[:pindex]
                        self.bufferd = self.bufferd[rindex+3:]
                        self.mode = Mode.CMD
                    else:
                        res = self.bufferd
                        self.bufferd = b''
                    self.connection.sendall(res)
                else:
                    rindex = self.bufferd.find(b'\r')
                    if rindex >= 0:
                        cmd = self.bufferd[:rindex].strip()
                        self.bufferd = self.bufferd[rindex+1:]
                    elif no_more_data:
                        cmd = self.bufferd.strip()
                        self.bufferd = b''
                    else:
                        break
                    if not cmd:
                        continue
                    res = self.dispatch_command(cmd) + b'\r'
                    self.request.sendall(res)
            if no_more_data:
                break
        print('====  Handle End  ====')

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
            print('Dial to {}'.format(phone_number))
            try:
                self.connection = connect_to("localhost", 8888)
            except socket.error as e:
                print(f'Connect error: {e}')
                res = 7
            else:
                self.mode = Mode.DATA
                res = 66

        res = translate_resp(self.resp_mode, cmd, res)
        print('{}|{}'.format(repr(cmd), repr(res)))
        return res


def connect_to(host, port):
    sock = socket.create_connection((host, port), 5)
    ring_msg = 'RING\r'
    sock.sendall(ring_msg)
    data = sock.recv(4096)
    print(f'<{repr(ring_msg)}>{repr(data)}')
    return sock


if __name__ == '__main__':
    HOST, PORT = "localhost", 9999
    server = socketserver.TCPServer((HOST, PORT), VirtualModemHandler)
    server.serve_forever()

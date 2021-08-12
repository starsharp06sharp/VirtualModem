#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from logging import Logger
import selectors
import socket
import time
import config
from common import *


sel = selectors.DefaultSelector()
modems = []
phone2modem = {}


class VirtualConnection(object):
    def __init__(self, m1, m2):
        super().__init__()
        self.modems = (m1, m2)
        self.data = [b'', b'']
        self.status = VConnState.CONNECTING

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
        self.dialing = False

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

    def close_conn(self):
        print(f'====== Modem{self.id} End ======')
        sel.unregister(self.conn)
        self.conn.close()
        self.conn = None

    def recv_from_com(self, conn):
        data = self.conn.recv(4096)
        logger.info(f'>{self.id} {repr(data)}')
        if not data:
            self.close_conn()
            return
        self.recv_buffer += data
        while self.recv_buffer:
            # FIXME: dirty implementation, refactor it by asyncio
            if self.dialing:
                if self.virtual_conn.status == VConnState.CONNECTED:
                    self.dialing = False
                    self.mode = Mode.DATA
                    res = translate_resp(self.resp_mode, b'OK', 66) + b'\r'
                    logger.info(f'<{self.id} {repr(res)}')
                    self.conn.sendall(res)
                elif self.virtual_conn.status == VConnState.CLOSED:
                    self.dialing = False
                    res = translate_resp(self.resp_mode, b'BUSY', 7) + b'\r'
                    logger.info(f'<{self.id} {repr(res)}')
                    self.conn.sendall(res)
                else:
                    time.sleep(0.3)
                    return

            if self.mode == Mode.DATA:
                # The escape sequence was preceded and followed by one second of silence
                if self.recv_buffer == b'+++':
                    print(f'{self.id}+++')
                    self.recv_buffer = b''
                    self.mode = Mode.CMD
                    continue
                package = self.recv_buffer
                self.recv_buffer = b''
                if not package:
                    continue
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
                res = self.dispatch_command(cmd)
                if res != -1:
                    res += b'\r'
                    logger.info(f'<{self.id} {repr(res)}')
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
                self.dialing = True
                res = -1
        elif cmd == b'ATA':
            if self.virtual_conn.status != VConnState.CLOSED:
                self.virtual_conn.status = VConnState.CONNECTED
                self.mode = Mode.DATA
                res = 66
            else:
                self.virtual_conn = None
                res = 8
        elif cmd == b'ATH':
            if self.virtual_conn:
                # disable in one way
                self.virtual_conn.status = VConnState.CLOSED
                self.virtual_conn = None

        if res != -1:
            res = translate_resp(self.resp_mode, cmd, res)
        print(f'{self.id}|{repr(cmd)}|{repr(res)}')
        return res

    def try_send2com(self):
        if not self.conn:
            return
        if self.mode == Mode.DATA:
            return self.try_send_data()
        elif self.mode == Mode.CMD:
            return self.try_ring_the_bell()

    def try_ring_the_bell(self):
        if not self.virtual_conn:
            return
        # Calling from remote
        if not self.dialing and self.virtual_conn.status == VConnState.CONNECTING:
            print(f'>{self.id}|RING')
            logger.info(f'<{self.id} b\'RING\\r\'')
            self.conn.sendall(b'RING\r')
            return
        # FIXME: dirty implementation, refactor it by asyncio
        if self.dialing:
            if self.virtual_conn.status == VConnState.CONNECTED:
                self.dialing = False
                self.mode = Mode.DATA
                print(f'{self.id}<|CONNECT')
                res = translate_resp(self.resp_mode, b'CONNECT', 66) + b'\r'
                logger.info(f'<{self.id} {repr(res)}')
                self.conn.sendall(res)
            elif self.virtual_conn.status == VConnState.CLOSED:
                self.dialing = False
                print(f'{self.id}<|BUSY')
                res = translate_resp(self.resp_mode, b'BUSY', 7) + b'\r'
                logger.info(f'<{self.id} {repr(res)}')
                self.conn.sendall(res)

    def try_send_data(self):
        if not self.virtual_conn:
            return
        data = self.virtual_conn.fetch_data(self)
        if data:
            logger.info(f'<{self.id} {repr(data)}')
            self.conn.sendall(data)
        # close this virtual_conn completely when half closed by remote
        if self.virtual_conn.status == VConnState.CLOSED:
            self.virtual_conn = None
            print(f'{self.id}<|NO CARRIER')
            res = translate_resp(self.resp_mode, b'NO CARRIER', 3)+b'\r'
            logger.info(f'<{self.id} {repr(res)}')
            self.conn.sendall(res)
            self.mode = Mode.CMD


def create_accept_func(m):
    def accept_fun(sock):
        print(f'====== Modem{m.id} Start ======')
        conn, addr = sock.accept()
        m.set_conn(conn)
        sel.register(conn, selectors.EVENT_READ, m.recv_from_com)
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
    select_timeout = 1
    while True:
        events = sel.select(select_timeout)
        mid_data_comes = set()
        # Read data from COM
        for key, mask in events:
            callback = key.data
            callback(key.fileobj)
            if hasattr(callback, '__self__'):
                mid_data_comes.add(callback.__self__.id)

        # Send data to COM
        for m in modems:
            m.try_send2com()
        if events:
            select_timeout = 0
        else:
            select_timeout = 1


if __name__ == '__main__':
    main()

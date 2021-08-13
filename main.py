#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import selectors
import socket
import time
import config
from common import *
from virtual_connection import VirtualConnection


sel = selectors.DefaultSelector()
modems = []
phone2modem = {}


class Modem(object):
    def __init__(self, id, phone, bps):
        super().__init__()
        self.id = id
        self.phone = phone
        self.bps = bps
        self.sock = None
        self.recv_buffer = b''
        self.vconn = None
        self.clear_status()

    def set_com_sock(self, sock):
        self.sock = sock
        self.recv_buffer = b''

    def clear_status(self):
        self.mode = Mode.CMD
        self.resp_mode = RespMode.MSG
        self.registers = [0] * 256
        # make virtual connection half closed
        if self.vconn:
            self.vconn.status = VConnState.CLOSED
        self.vconn = None
        self.dialing = False

    def connect2remote(self, phone):
        # find remote modem
        try:
            to_m = phone2modem[phone]
        except KeyError:
            raise ValueError(f'unkown phone {phone}')
        # check both modem is activated and idle
        if not self.sock or not to_m.sock:
            raise RuntimeError('modem is deactivated')
        if self.vconn or to_m.vconn:
            raise RuntimeError('already got connected')
        # create virtual connection
        self.vconn = VirtualConnection(self, to_m)
        to_m.vconn = self.vconn

    def close_com_sock(self):
        print(f'====== Modem{self.id} End ======')
        sel.unregister(self.sock)
        self.sock.close()
        self.sock = None

    def recv_from_com(self, sock):
        data = self.sock.recv(4096)
        logger.info(f'>{self.id} {repr(data)}')
        if not data:
            self.close_com_sock()
            return
        self.recv_buffer += data
        while self.recv_buffer:
            # FIXME: dirty implementation, refactor it by asyncio
            if self.dialing:
                if self.vconn.status == VConnState.CONNECTED:
                    self.dialing = False
                    self.mode = Mode.DATA
                    res = translate_resp(self.resp_mode, b'OK', 66) + b'\r'
                    logger.info(f'<{self.id} {repr(res)}')
                    self.sock.sendall(res)
                elif self.vconn.status == VConnState.CLOSED:
                    self.dialing = False
                    res = translate_resp(self.resp_mode, b'BUSY', 7) + b'\r'
                    logger.info(f'<{self.id} {repr(res)}')
                    self.sock.sendall(res)
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
                self.vconn.push_data(self, package)

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
                    self.sock.sendall(res)

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
                self.connect2remote(phone_number)
            except BaseException as e:
                print(f'Dial to {phone_number} failed: {e}')
                res = 7
            else:
                self.dialing = True
                res = -1
        elif cmd == b'ATA':
            if self.vconn.status != VConnState.CLOSED:
                self.vconn.status = VConnState.CONNECTED
                self.mode = Mode.DATA
                res = 66
            else:
                self.vconn = None
                res = 8
        elif cmd == b'ATH':
            if self.vconn:
                # disable in one way
                self.vconn.status = VConnState.CLOSED
                self.vconn = None

        if res != -1:
            res = translate_resp(self.resp_mode, cmd, res)
        print(f'{self.id}|{repr(cmd)}|{repr(res)}')
        return res

    def try_send2com(self):
        if not self.sock:
            return
        if self.mode == Mode.DATA:
            return self.try_send_data()
        elif self.mode == Mode.CMD:
            return self.try_ring_the_bell()

    def try_ring_the_bell(self):
        if not self.vconn:
            return
        # Calling from remote
        if not self.dialing and self.vconn.status == VConnState.CONNECTING:
            print(f'>{self.id}|RING')
            logger.info(f'<{self.id} b\'RING\\r\'')
            self.sock.sendall(b'RING\r')
            return
        # FIXME: dirty implementation, refactor it by asyncio
        if self.dialing:
            if self.vconn.status == VConnState.CONNECTED:
                self.dialing = False
                self.mode = Mode.DATA
                print(f'{self.id}<|CONNECT')
                res = translate_resp(self.resp_mode, b'CONNECT', 66) + b'\r'
                logger.info(f'<{self.id} {repr(res)}')
                self.sock.sendall(res)
            elif self.vconn.status == VConnState.CLOSED:
                self.dialing = False
                print(f'{self.id}<|BUSY')
                res = translate_resp(self.resp_mode, b'BUSY', 7) + b'\r'
                logger.info(f'<{self.id} {repr(res)}')
                self.sock.sendall(res)

    def try_send_data(self):
        if not self.vconn:
            return
        data = self.vconn.fetch_data(self)
        if data:
            logger.info(f'<{self.id} {repr(data)}')
            self.sock.sendall(data)
        # close this virtual connection completely when half closed by remote
        if self.vconn.status == VConnState.CLOSED:
            self.vconn = None
            print(f'{self.id}<|NO CARRIER')
            res = translate_resp(self.resp_mode, b'NO CARRIER', 3)+b'\r'
            logger.info(f'<{self.id} {repr(res)}')
            self.sock.sendall(res)
            self.mode = Mode.CMD


def create_accept_func(m):
    def accept_fun(listen_sock):
        print(f'====== Modem{m.id} Start ======')
        sock, addr = listen_sock.accept()
        m.set_com_sock(sock)
        sel.register(sock, selectors.EVENT_READ, m.recv_from_com)
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

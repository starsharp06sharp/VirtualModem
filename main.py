#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socketserver

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


class VirtualModemHandler(socketserver.BaseRequestHandler):
    def __init__(self, *args, **kw):
        self.bufferd = b''
        self.registers = [0] * 256
        self.echo_mode = True
        super().__init__(*args, **kw)

    def handle(self):
        print('==== Handle Start ====')
        no_more_data = False
        while(True):
            data = self.request.recv(4096)
            if not data:
                no_more_data = True
            self.bufferd += data
            while True:
                ri = self.bufferd.find(b'\r')
                if ri >= 0:
                    cmd = self.bufferd[:ri]
                    self.bufferd = self.bufferd[ri+1:]
                elif no_more_data:
                    cmd = self.bufferd
                    self.bufferd = b''
                else:
                    break
                if not cmd:
                    continue
                res = self.dispatch_command(cmd)
                self.request.sendall(res + b'\r')
            if no_more_data:
                break
        print('====  Handle End  ====')
    
    def dispatch_command(self, cmd):
        res = b'0'
        print('{}|{}'.format(repr(cmd), repr(res)))
        return res


if __name__ == '__main__':
    HOST, PORT = "localhost", 9999
    server = socketserver.TCPServer((HOST, PORT), VirtualModemHandler)
    server.serve_forever()

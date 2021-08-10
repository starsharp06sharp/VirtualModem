#!/usr/bin/env python
# -*- coding: utf-8 -*-
import SocketServer

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

class VirtualModemHandler(SocketServer.BaseRequestHandler):
    def handle(self):
        print '==== Handle Start ===='
        while(True):
            raw_data = self.request.recv(4096)
            if not raw_data:
                break
            data = raw_data#.strip()
            print '{}|{}'.format(len(data), repr(data))
            if len(data) == 0:
                res = ''
            else:
                res = 0
            self.request.sendall('{}\r'.format(res))
        print '====  Handle End  ===='


if __name__ == '__main__':
    HOST, PORT = "localhost", 9999
    server = SocketServer.TCPServer((HOST, PORT), VirtualModemHandler)
    server.serve_forever()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio

import config
from common import MsgType, QueueMessage, phone2modem
from modem import Modem


async def read_to_queue_loop(reader, queue):
    while True:
        data = await reader.read(4096)
        if not data:
            return
        msg = QueueMessage(MsgType.ComData, data)
        await queue.put(msg)


async def write_from_queue_loop(queue, writer):
    try:
        while True:
            data = await queue.get()
            writer.write(data)
            await writer.drain()
    except asyncio.CancelledError:
        pass
    finally:
        writer.close()
        await writer.wait_closed()


def create_handler(m: Modem):
    async def handle_read_write(reader, writer):
        print(f'======  Modem{m.id} activated  ======')
        assert not m.activated
        m.activated = True
        read_task = asyncio.create_task(read_to_queue_loop(reader, m.msg_recvq))
        write_task = asyncio.create_task(write_from_queue_loop(m.com_sendq, writer))
        await read_task
        write_task.cancel()
        m.activated = False
        m.clear_status()
        print(f'====== Modem{m.id} deactivated ======')
    return handle_read_write


async def main():
    id = 0
    fibers = []
    try:
        for modem_cfg in config.modems:
            # create modem object
            m = Modem(id, modem_cfg['phone'], modem_cfg['bps'])
            # register modem object
            svr = await asyncio.start_server(create_handler(m), *modem_cfg['address'])
            await svr.__aenter__()
            fibers.append(svr.serve_forever())
            fibers.append(m.main_loop())
            phone2modem[modem_cfg['phone']] = m
            id += 1

        await asyncio.gather(*fibers)
    finally:
        for f in fibers:
            if hasattr(f, '__aexit__'):
                await f.__aexit__()


if __name__ == '__main__':
    asyncio.run(main())

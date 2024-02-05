#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio

import config
from common import CommEventType, MsgType, QueueMessage, logger, phone2modem
from fake_conn_server import create_server
from modem import Modem


async def read_to_queue_loop(id, reader, queue):
    while True:
        data = await reader.read(4096)
        logger.info(f'>{id} {data!r}')
        if not data:
            return
        msg = QueueMessage(MsgType.ComData, data)
        await queue.put(msg)


async def write_from_queue_loop(id, queue, writer):
    try:
        while True:
            data = await queue.get()
            logger.info(f'<{id} {data!r}')
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


def create_handler(m: Modem):
    async def handle_read_write(reader, writer):
        print(f'======  Modem{m.id} activated  ======')
        assert not m.activated
        m.activated = True
        read_task = asyncio.create_task(
            read_to_queue_loop(m.id, reader, m.msg_recvq))
        write_task = asyncio.create_task(
            write_from_queue_loop(m.id, m.com_sendq, writer))
        await read_task
        await m.msg_recvq.put(QueueMessage(MsgType.ComEvent, CommEventType.PortPowerOff))
        write_task.cancel()
        m.activated = False
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
            svr = await create_server(create_handler(m), modem_cfg['address'])
            if hasattr(svr, '__aenter__'):
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

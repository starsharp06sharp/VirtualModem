#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio

import config
from common import modems, phone2modem
from modem import Modem


def create_handler(m):
    async def handle_read_write(reader, writer):
        print(f'======  Modem{m.id} activated  ======')
        # TODO: impl
        print(f'====== Modem{m.id} deactivated ======')
    return handle_read_write


async def main():
    id = 0
    fibers = []
    for modem_cfg in config.modems:
        # create modem object
        m = Modem(id, modem_cfg['phone'], modem_cfg['bps'])
        # register modem object
        svr = await asyncio.start_server(create_handler(m), *modem_cfg['address'])
        fibers.append(svr.serve_forever())
        # TODO: start server main loop
        modems.append(m)
        phone2modem[modem_cfg['phone']] = m
        id += 1

    await asyncio.gather(*fibers)


if __name__ == '__main__':
    asyncio.run(main())

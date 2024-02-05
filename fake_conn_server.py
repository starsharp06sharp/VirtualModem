import asyncio
import functools
import sys


class FakeConnServer(object):

    def __init__(self, handler, conn_func):
        super().__init__()
        self._handler = handler
        self._conn_func = conn_func

    async def serve_forever(self):
        while True:
            try:
                reader, writer = await self._conn_func()
            except FileNotFoundError:
                await asyncio.sleep(3)
                continue
            await self._handler(reader, writer)


async def create_server(handler, address):
    if isinstance(address, (tuple, list)):
        return await asyncio.start_server(handler, *address)
    elif isinstance(address, str):
        if sys.platform != "win32":
            return FakeConnServer(handler, functools.partial(asyncio.open_unix_connection, address))
        return FakeConnServer(handler, functools.partial(open_namedpipe_connection, address))
    else:
        raise TypeError(f"Invalid address {address}")


async def open_namedpipe_connection(path=None, *, limit=2**16):
    loop = asyncio.events.get_running_loop()

    reader = asyncio.streams.StreamReader(limit=limit, loop=loop)
    protocol = asyncio.streams.StreamReaderProtocol(reader, loop=loop)
    transport, _ = await loop.create_pipe_connection(lambda: protocol, path)
    writer = asyncio.streams.StreamWriter(transport, protocol, reader, loop)
    return reader, writer

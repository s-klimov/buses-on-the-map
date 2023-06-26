import json
from contextlib import suppress

import trio
import trio.testing
from trio_websocket import serve_websocket, ConnectionClosed


send_channel, receive_channel = trio.open_memory_channel(0)
buses = dict()


async def send_message(request):
    ws = await request.accept()

    async for message in receive_channel:
        buse = json.loads(message)
        buses[buse['busId']] = buse

        buses_msg = json.dumps(
            {'msgType': 'Buses', 'buses': list(buses.values())}
        )

        try:
            await ws.send_message(buses_msg)
        except ConnectionClosed:
            break


async def get_message(request):
    ws = await request.accept()

    try:
        while message := await ws.get_message():

            await send_channel.send(message)
    except ConnectionClosed:
        pass


async def main():
    async with trio.open_nursery() as nursery:
        nursery.start_soon(
            serve_websocket, get_message, '127.0.0.1', 8080, None
        )
        nursery.start_soon(
            serve_websocket, send_message, '127.0.0.1', 8000, None
        )


if __name__ == '__main__':
    with suppress(KeyboardInterrupt):
        trio.run(main)

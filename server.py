import json
import logging
import warnings
from contextlib import suppress

import trio
import trio.testing
import asyncclick as click
from trio import TrioDeprecationWarning
from trio_websocket import serve_websocket, ConnectionClosed


warnings.filterwarnings(action='ignore', category=TrioDeprecationWarning)
send_channel, receive_channel = trio.open_memory_channel(0)
buses = dict()
logging.basicConfig(
    format='%(asctime)s - %(levelname)s: %(name)s: %(message)s',
    datefmt='%m/%d/%Y %H:%M:%S',
)
logger = logging.getLogger('server')


async def exchange_messages(request):
    ws = await request.accept()

    async with trio.open_nursery() as nursery:
        nursery.start_soon(listen_browser, ws)
        nursery.start_soon(send_buses, ws)


async def listen_browser(ws):

    with suppress(ConnectionClosed):
        while message := await ws.get_message():
            logger.debug('%s', (message,))


async def send_buses(ws):

    async for message in receive_channel:
        buse = json.loads(message)
        buses[buse['busId']] = buse

        buses_msg = json.dumps(
            {'msgType': 'Buses', 'buses': list(buses.values())}
        )
        logger.debug('%s', (buses_msg,))
        try:
            await ws.send_message(buses_msg)
        except ConnectionClosed:
            break


async def get_message(request):
    ws = await request.accept()

    with suppress(ConnectionClosed):
        while message := await ws.get_message():

            await send_channel.send(message)


@click.command()
@click.option(
    '-v', '--verbose', count=True, help='Настройка логирования.'
)  # https://click.palletsprojects.com/en/8.1.x/options/#counting
async def main(verbose):

    if verbose in [0, 1]:
        level = logging.ERROR
    elif verbose == 2:
        level = logging.WARNING
    elif verbose == 3:
        level = logging.INFO
    else:
        level = logging.DEBUG

    logger.setLevel(level)
    async with trio.open_nursery() as nursery:
        nursery.start_soon(
            serve_websocket, get_message, '127.0.0.1', 8080, None
        )
        nursery.start_soon(
            serve_websocket, exchange_messages, '127.0.0.1', 8000, None
        )


if __name__ == '__main__':

    with suppress(KeyboardInterrupt):
        trio.run(main(_anyio_backend='trio'))

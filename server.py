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

    bounds = dict()

    async with trio.open_nursery() as nursery:
        nursery.start_soon(listen_browser, ws, bounds)
        nursery.start_soon(send_buses, ws, bounds)


async def listen_browser(ws, bounds):

    with suppress(ConnectionClosed):
        while (message := await ws.get_message()) and json.loads(message).get(
            'msgType'
        ) == 'newBounds':
            logger.debug('%s', (message,))
            bounds.clear()
            bounds.update(json.loads(message)['data'])

            # FIXME удалить отладочный код
            top_buses = {
                bus_id: coordinate
                for bus_id, coordinate in buses.items()
                if is_inside(
                    bounds=bounds, lat=coordinate['lat'], lng=coordinate['lng']
                )
            }
            logger.debug('%d buses inside bounds' % (len(top_buses),))


async def send_buses(ws, bounds):

    async for message in receive_channel:
        bus = json.loads(message)
        buses[bus['busId']] = bus

        top_buses = {
            bus_id: coordinate
            for bus_id, coordinate in buses.items()
            if is_inside(
                bounds=bounds, lat=coordinate['lat'], lng=coordinate['lng']
            )
        } if bounds else {}

        buses_msg = json.dumps(
            {'msgType': 'Buses', 'buses': list(top_buses.values())}
        )
        try:
            await ws.send_message(buses_msg)
        except ConnectionClosed:
            break


def is_inside(bounds: dict, lat: float, lng: float):
    return (
        bounds['south_lat'] < lat < bounds['north_lat']
        and bounds['west_lng'] < lng < bounds['east_lng']
    )


async def get_message(request):
    ws = await request.accept()

    with suppress(ConnectionClosed):
        while message := await ws.get_message():

            await send_channel.send(message)


def get_log_level(ctx, param, value):
    levels = [
        logging.ERROR,
        logging.WARNING,
        logging.INFO,
        logging.DEBUG,
    ]
    level = levels[min(value, len(levels) - 1)]

    return level


@click.command()
@click.option(
    '-v',
    '--verbose',
    count=True,
    callback=get_log_level,
    help='Настройка логирования.',
)  # https://click.palletsprojects.com/en/8.1.x/options/#counting
async def main(verbose):

    logger.setLevel(verbose)

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

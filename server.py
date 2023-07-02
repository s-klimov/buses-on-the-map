import json
import logging
import warnings
from contextlib import suppress
from dataclasses import dataclass, asdict

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


@dataclass
class Bus:
    """Автобус на карте"""

    busId: str  # номер автобуса
    lat: float  # географическая ширина местоположения автобуса
    lng: float  # географическая долгота местоположения автобуса
    route: str  # номер маршрута


@dataclass
class WindowBounds:
    """Координаты окна карты фронтенда"""

    south_lat: float | None = None
    north_lat: float | None = None
    west_lng: float | None = None
    east_lng: float | None = None

    def is_inside(self, lat: float, lng: float) -> bool:
        """Находится ли заданная координата внутри окна?
        :param lat: Географиеская ширина координаты.
        :param lng: Географиеская долгота координаты.
        """
        return (
            self.south_lat < lat < self.north_lat
            and self.west_lng < lng < self.east_lng
        )

    def is_none(self) -> bool:
        """Возвращает значение Истина, если хотя бы одна из координат окна не определена."""
        return (
            self.south_lat is None
            or self.north_lat is None
            or self.west_lng is None
            or self.east_lng is None
        )

    def update(
        self,
        south_lat: float = None,
        north_lat: float = None,
        west_lng: float = None,
        east_lng: float = None,
    ):
        self.south_lat = south_lat
        self.north_lat = north_lat
        self.west_lng = west_lng
        self.east_lng = east_lng


async def exchange_messages(request):
    ws = await request.accept()

    bounds = WindowBounds()

    async with trio.open_nursery() as nursery:
        nursery.start_soon(listen_browser, ws, bounds)
        nursery.start_soon(send_buses, ws, bounds)


async def listen_browser(ws, bounds: WindowBounds):

    with suppress(ConnectionClosed):
        while (message := await ws.get_message()) and json.loads(message).get(
            'msgType'
        ) == 'newBounds':
            logger.debug('%s', (message,))
            bounds.update(**json.loads(message)['data'])


async def send_buses(ws, bounds: WindowBounds):

    async for message in receive_channel:
        bus = Bus(**json.loads(message))
        if bounds.is_none():
            continue

        if not bounds.is_inside(lat=bus.lat, lng=bus.lng):
            buses.pop(bus.busId, None)
            continue

        buses[bus.busId] = bus
        logger.debug('sent bus on the map %s' % (bus,))

        buses_msg = json.dumps(
            {
                'msgType': 'Buses',
                'buses': [asdict(bus) for bus in buses.values()],
            }
        )
        try:
            await ws.send_message(buses_msg)
        except ConnectionClosed:
            break


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

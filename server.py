import json
import logging
import time
import warnings
from contextlib import suppress
from dataclasses import dataclass, asdict

import trio
import trio.testing
import asyncclick as click
from trio import TrioDeprecationWarning
from trio_websocket import serve_websocket, ConnectionClosed

from validators import is_instance_valid

REFRESH_TIMEOUT = 0.2  # Задержка в обновлении координат сервера.

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

    def __post_init__(self):
        if not isinstance(self.busId, str):
            raise ValueError(
                f'{self.busId}: Номер автобуса должен быть задан строкой.'
            )
        if not isinstance(self.lat, float):
            raise ValueError(
                f'{self.lat}: Географическая широта местоположения автобуса должна быть числом с плавающей точкой.'
            )
        if not isinstance(self.lng, float):
            raise ValueError(
                f'{self.lng}: Географическая долгота местоположения автобуса должна быть числом с плавающей точкой.'
            )
        if not isinstance(self.route, str):
            raise ValueError(
                f'{self.route}: Номер маршрута должен быть задан строкой.'
            )


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

    def __post_init__(self):

        if not (self.south_lat is None or isinstance(self.south_lat, float)):
            raise ValueError(
                f'{self.south_lat}: Нижняя граница карты быть числом с плавающей точкой.'
            )
        if not (self.north_lat is None or isinstance(self.north_lat, float)):
            raise ValueError(
                f'{self.north_lat}: Верхняя граница карты должна быть числом с плавающей точкой.'
            )
        if not (self.west_lng is None or isinstance(self.west_lng, float)):
            raise ValueError(
                f'{self.west_lng}: Левая граница карты должна быть числом с плавающей точкой.'
            )
        if not (self.east_lng is None or isinstance(self.east_lng, float)):
            raise ValueError(
                f'{self.east_lng}: Правая граница карты должна быть числом с плавающей точкой.'
            )


@dataclass
class Bounds:
    """Ответ фронтенда"""

    msgType: str
    data: WindowBounds

    def __post_init__(self):
        if not (isinstance(self.msgType, str) and self.msgType == 'newBounds'):
            raise ValueError(
                f'{self.msgType}: Тип сообщения должен быть строкой "newBounds".'
            )

        self.data = WindowBounds(**self.data)


async def talk_to_browser(request):
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
            is_valid, message = is_instance_valid(message, Bounds)
            logger.debug('%s', (message,))
            if is_valid:
                bounds.update(**json.loads(message)['data'])


async def send_buses(ws, bounds: WindowBounds):

    start = time.monotonic()

    async for bus in receive_channel:
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
            },
            ensure_ascii=False,
        )
        try:
            if time.monotonic() - start >= REFRESH_TIMEOUT:
                await ws.send_message(buses_msg)
                start = time.monotonic()
        except ConnectionClosed:
            break


async def get_message(request):
    ws = await request.accept()

    with suppress(ConnectionClosed):
        while message := await ws.get_message():

            is_valid, message = is_instance_valid(message, Bus)
            if is_valid:
                await send_channel.send(Bus(**json.loads(message)))
            else:
                ws.send_message(message)


def validate_port_number(ctx, param, value):
    if not 0 <= value <= 65535:
        raise click.BadParameter(
            'Номер порта - ожидается целое число без знака, в диапазоне от 0 до 65535.'
        )
    return value


def get_log_level(ctx, param, value):
    levels = [
        logging.ERROR,
        logging.WARNING,
        logging.INFO,
        logging.DEBUG,
    ]
    level = levels[min(value, len(levels) - 1)]

    return level


# !!! Просьба не менять входные аргументы
@click.command()
@click.option(
    '--refresh_timeout',
    type=float,
    default=REFRESH_TIMEOUT,
    show_default=True,
    help='Задержка в обновлении координат сервера.',
)
@click.option(
    '--bus_port',
    type=int,
    default=8080,
    show_default=True,
    callback=validate_port_number,
    help='Порт для имитатора автобусов.',
)
@click.option(
    '--browser_port',
    type=int,
    default=8000,
    show_default=True,
    callback=validate_port_number,
    help='Порт для браузера.',
)
@click.option(
    '-v',
    '--verbose',
    count=True,
    callback=get_log_level,
    help='Настройка логирования.',
)  # https://click.palletsprojects.com/en/8.1.x/options/#counting
async def main(refresh_timeout, bus_port, browser_port, verbose):

    logger.setLevel(verbose)

    global REFRESH_TIMEOUT
    REFRESH_TIMEOUT = refresh_timeout

    async with trio.open_nursery() as nursery:
        nursery.start_soon(
            serve_websocket, get_message, '127.0.0.1', bus_port, None
        )
        nursery.start_soon(
            serve_websocket, talk_to_browser, '127.0.0.1', browser_port, None
        )


if __name__ == '__main__':

    with suppress(KeyboardInterrupt):
        trio.run(main(_anyio_backend='trio'))

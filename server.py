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
            logger.debug('%s', (message,))
            bounds.update(**json.loads(message)['data'])


async def send_buses(ws, bounds: WindowBounds):

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

            # Проверяем полученную строку на валидность преобразования в json и на то, что полученный json
            # имеет требуемую структуру
            try:
                bus = Bus(**json.loads(message))
            except json.JSONDecodeError:
                ws.send_message(
                    '{"errors": ["Requires valid JSON"], "msgType": "Errors"}'
                )
            except TypeError:
                ws.send_message(
                    '{"errors": ["Requires msgType specified"], "msgType": "Errors"}'
                )
            else:
                await send_channel.send(bus)


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
# bus_port - порт для имитатора автобусов
# browser_port - порт для браузера
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
async def main(bus_port, browser_port, verbose):

    logger.setLevel(verbose)

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

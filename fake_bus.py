"""Скрипт имитации автобусов"""

import itertools
import json
import logging
import os
import warnings
from collections import deque
from contextlib import suppress, AsyncExitStack
from functools import wraps
from pathlib import Path
from random import randrange

import asyncclick as click
import asyncstdlib as a
import trio
import trio_websocket
from trio import MemoryReceiveChannel, MemorySendChannel
from trio import TrioDeprecationWarning
from trio_websocket import open_websocket_url

ROUTES_DIR = 'routes'    # папка с маршрутами автобусов
BUS_NUM_LENGTH = 3       # количество символов в номере автобуса
RELAUNCH_INTERVAL = (
    1  # интервал переподключения в секундах при обрыве соединения с сервером
)

warnings.filterwarnings(action='ignore', category=TrioDeprecationWarning)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%m/%d/%Y %H:%M:%S',
)
logger = logging.getLogger('fake-bus')


async def load_routes(directory_path=ROUTES_DIR):
    """
    Генератор, который возвращает json'ы с маршрутами из файлов папки с маршрутами.
    :param directory_path: Имя/путь папки с json-файлами, содержащими маршруты.
    """
    for filename in os.listdir(directory_path):
        logger.info('Открываем файл %s' % (filename,))
        if filename.endswith('.json'):
            filepath = os.path.join(Path(directory_path), filename)
            async with await trio.open_file(
                filepath, 'r', encoding='utf8'
            ) as afp:
                route_full_info = await afp.read()
                yield json.loads(route_full_info)


async def run_bus(
    send_channel: MemorySendChannel,
    bus_id: str,
    points: list,
    route_name: str,
    refresh_timeout: float,
    /,
):
    """
    Хэндлер запуска автобуса в очередь trio.
    :param send_channel: Очередь trio.
    :param bus_id: Номер автобуса.
    :param points: Точки маршрута.
    :param route_name: Номер маршрута.
    :param refresh_timeout: Интервал в секундах между перемещениями автобусов по точкам маршрутов на карте.
    """
    for lat, long in itertools.cycle(points):
        coordinate = {
            'busId': bus_id,
            'lat': lat,
            'lng': long,
            'route': route_name,
        }
        await send_channel.send(json.dumps(coordinate))
        await trio.sleep(refresh_timeout)


def generate_bus_id(route_id, bus_index, emulator_id):
    """Генератор номера автобуса."""
    return f'{route_id}-{emulator_id}{str(bus_index).zfill(BUS_NUM_LENGTH)}'


def relaunch_on_disconnect(f):
    """
    Декоратор, отслеживающий соединение с сервером.
    При обнаружении разрыва соединения происходит попытка нового подключения.
    """

    @wraps(f)
    async def wrapper(*args, **kwds):
        with suppress(KeyboardInterrupt):
            while True:
                try:
                    await f(*args, **kwds)
                except (
                    trio_websocket.HandshakeError,
                    trio_websocket.ConnectionClosed,
                ):
                    logger.error(
                        'Ошибка соединения с сервером. Попытка подключения через %d сек'
                        % (RELAUNCH_INTERVAL,)
                    )
                    await trio.sleep(RELAUNCH_INTERVAL)

    return wrapper


@relaunch_on_disconnect
async def send_updates(
    server: str,
    websockets_number: int,
    receive_channel: MemoryReceiveChannel,
    /,
):
    """
    Отправляет координаты автобуса по web-сокету. Web-сокет выбирается случайным образом из заданных.
    :param server: Адрес сервера.
    :param websockets_number: Количество открытых web-сокетов.
    :param receive_channel: Канал для приема координат автобуса для последующей отправки.
    """
    async with AsyncExitStack() as stack:
        sockets = [
            await stack.enter_async_context(open_websocket_url(server))
            for _ in range(websockets_number)
        ]
        logger.info('Открыто %d сокетов.' % (len(sockets),))
        async for message in receive_channel:
            with suppress(KeyboardInterrupt):
                await sockets[randrange(websockets_number)].send_message(
                    message
                )


def validate_routes_number(ctx, param, value) -> int:
    """Валидатор для параметра routes_number. Ограничен количеством файлов с маршрутами в папке routes."""
    if value < 1 or value > 595:
        raise click.BadParameter(
            'Количество маршрутов должно быть от 1 до 595.'
        )
    return value


def get_log_level(ctx, param, value) -> int:
    """Преобразует количество указанных v (verbose) в параметрах скрипта к уровню логирования"""
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
    '--server',
    default='ws://127.0.0.1:8080/ws',
    show_default=True,
    help='Адрес сервера.',
)
@click.option(
    '--routes_number',
    default=595,
    show_default=True,
    callback=validate_routes_number,
    help='Количество маршрутов (от 1 до 595).',
)
@click.option(
    '--buses_per_route',
    default=100,
    show_default=True,
    help='Количество автобусов на каждом маршруте.',
)
@click.option(
    '--websockets_number',
    default=10,
    show_default=True,
    help='Количество открытых веб-сокетов.',
)
@click.option(
    '--emulator_id',
    default='',
    help='Префикс к busId на случай запуска нескольких экземпляров имитатора.',
)
@click.option(
    '--refresh_timeout',
    type=float,
    default=0.3,
    show_default=True,
    help='Пауза между отправками следующих координат фейковых автобусов.',
)
@click.option(
    '-v',
    '--verbose',
    count=True,
    callback=get_log_level,
    help='Настройка логирования.',
)  # https://click.palletsprojects.com/en/8.1.x/options/#counting
async def main(
    server,
    routes_number,
    buses_per_route,
    websockets_number,
    emulator_id,
    refresh_timeout,
    verbose,
):

    logger.setLevel(verbose)

    send_channel, receive_channel = trio.open_memory_channel(0)

    async with trio.open_nursery() as nursery:
        nursery.start_soon(
            send_updates, server, websockets_number, receive_channel
        )

        async for i, route in a.enumerate(load_routes()):
            if i == routes_number:
                break

            coordinates = (
                route['coordinates'] + route['coordinates'][::-1]
            )  # добавляем обратный путь

            points = deque(coordinates)

            for bus_index in range(randrange(1, buses_per_route)):
                logger.debug(
                    'Запускаем автобус %s по маршруту %s'
                    % (
                        bus_index,
                        route['name'],
                    )
                )

                points.rotate(
                    randrange(len(coordinates))
                )  # поездку начинаем с произвольной точки маршрута

                nursery.start_soon(
                    run_bus,
                    send_channel,
                    generate_bus_id(route['name'], bus_index, emulator_id),
                    points.copy(),
                    route['name'],
                    refresh_timeout,
                )


if __name__ == '__main__':
    with suppress(KeyboardInterrupt):
        trio.run(main(_anyio_backend='trio'))

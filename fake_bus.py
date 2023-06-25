import contextlib
import json
import os
from collections import deque
from pathlib import Path
from random import randrange

import trio

from trio import MemoryReceiveChannel, MemorySendChannel
from trio_websocket import open_websocket_url
import itertools

INTERVAL = 0.1           # интервал в секундах между перемещениями автобусов по точкам маршрутов на карте
ROUTES_DIR = 'routes'    # папка с маршрутами автобусов
MAX_BUSES_ON_ROUTE = 100   # максимальное количество автобусов на маршруте
BUS_NUM_LENGTH = 3       # количество символов в номере автобуса
SOCKETS_COUNT = 5        # количество открытых сокетов для обмена с сервером


async def load_routes(directory_path=ROUTES_DIR):
    for filename in os.listdir(directory_path):
        if filename.endswith('.json'):
            filepath = os.path.join(Path(directory_path), filename)
            async with await trio.open_file(
                filepath, 'r', encoding='utf8'
            ) as afp:
                route_full_info = await afp.read()
                yield json.loads(route_full_info)


async def run_bus(
    send_channel: MemorySendChannel, bus_id: str, route: dict, /
):

    coordinates = (
        route['coordinates'] + route['coordinates'][::-1]
    )  # добавляем обратный путь

    points = deque(coordinates)
    points.rotate(
        randrange(len(coordinates))
    )  # поездку начинаем с произвольной точки маршрута

    for lat, long in itertools.cycle(points):
        coordinate = {
            'busId': bus_id,
            'lat': lat,
            'lng': long,
            'route': route['name'],
        }
        await send_channel.send(json.dumps(coordinate))
        await trio.sleep(INTERVAL)


def generate_bus_id(route_id, bus_index):
    return f'{route_id}-{str(bus_index).zfill(BUS_NUM_LENGTH)}'


async def send_updates(
    server_address: str, receive_channel: MemoryReceiveChannel, /
):
    """
    Отправляет координаты автобуса по web-сокету. Web-сокет выбирается случайным образом из заданных.
    :param server_address: Адрес сервера
    :param receive_channel: Канал для приема координат автобуса для последующей отправки.
    """
    async with contextlib.AsyncExitStack() as stack:
        sockets = [
            await stack.enter_async_context(open_websocket_url(server_address))
            for _ in range(SOCKETS_COUNT)
        ]
        async for message in receive_channel:
            await sockets[randrange(SOCKETS_COUNT)].send_message(message)


async def main():
    server_address = 'ws://127.0.0.1:8080/ws'
    send_channel, receive_channel = trio.open_memory_channel(0)

    async with trio.open_nursery() as nursery:
        nursery.start_soon(send_updates, server_address, receive_channel)

        async for route in load_routes():
            for bus_index in range(randrange(1, MAX_BUSES_ON_ROUTE)):
                nursery.start_soon(
                    run_bus,
                    send_channel,
                    generate_bus_id(route['name'], bus_index),
                    route,
                )


if __name__ == '__main__':
    trio.run(main)

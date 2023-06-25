import json
import os
from collections import deque
from pathlib import Path
from random import randrange

import trio
from sys import stderr

from trio_websocket import open_websocket_url
import itertools

INTERVAL = 0.1
ROUTES_DIR = 'routes'
MAX_BUSES_ON_ROUTE = 3  # максимальное количество автобусов на маршруте


async def load_routes(directory_path=ROUTES_DIR):
    for filename in os.listdir(directory_path):
        if filename.endswith('.json'):
            filepath = os.path.join(Path(directory_path), filename)
            async with await trio.open_file(
                filepath, 'r', encoding='utf8'
            ) as afp:
                route_full_info = await afp.read()
                yield json.loads(route_full_info)


async def run_bus(url, bus_id, route, /):

    coordinates = (
        route['coordinates'] + route['coordinates'][::-1]
    )  # добавляем обратный путь

    points = deque(coordinates)
    points.rotate(randrange(len(coordinates)))  # поездку начинаем с произвольной точки маршрута

    try:
        async with open_websocket_url(url) as ws:
            for lat, long in itertools.cycle(points):
                coordinate = {
                    'busId': bus_id,
                    'lat': lat,
                    'lng': long,
                    'route': route['name'],
                }
                await ws.send_message(json.dumps(coordinate))
                await trio.sleep(INTERVAL)
    except OSError as ose:
        print('Connection attempt failed: %s' % ose, file=stderr)


def generate_bus_id(route_id, bus_index):
    return f"{route_id}-{str(bus_index).zfill(3)}"


async def main():

    async with trio.open_nursery() as nursery:
        async for route in load_routes():
            for bus_index in range(randrange(1, MAX_BUSES_ON_ROUTE)):
                nursery.start_soon(
                    run_bus,
                    'ws://127.0.0.1:8080/ws',
                    generate_bus_id(route['name'], bus_index),
                    route,
                )


if __name__ == '__main__':
    trio.run(main)

import json
from pathlib import Path

import trio
from sys import stderr

from trio_websocket import open_websocket_url
import itertools

INTERVAL = 2
ROUTES_DIR = 'routes'


async def fetch():
    bus_id = 'd644ve'

    route612_filename = Path(ROUTES_DIR) / '120.json'
    async with await trio.open_file(route612_filename) as afp:
        route_full_info = await afp.read()
        route = json.loads(route_full_info)

    coordinates = (
        route['coordinates'] + route['coordinates'][::-1]
    )  # добавляем обратный путь

    for lat, long in itertools.cycle(coordinates):
        coordinate = {
            'busId': bus_id,
            'lat': lat,
            'lng': long,
            'route': route['name'],
        }
        yield coordinate
        await trio.sleep(INTERVAL)


async def main():
    bus_d644ve = fetch()

    try:
        async with open_websocket_url('ws://127.0.0.1:8000/ws') as ws:
            while True:
                coordinates = await anext(bus_d644ve)
                buses = {
                    "msgType": "Buses",
                    "buses": [
                        coordinates,
                        {"busId": "a134aa", "lat": 55.7494, "lng": 37.621, "route": "670к"},
                    ],
                }
                await ws.send_message(json.dumps(buses))
    except OSError as ose:
        print('Connection attempt failed: %s' % ose, file=stderr)


trio.run(main)

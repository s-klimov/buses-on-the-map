import json

import trio
from trio_websocket import serve_websocket, ConnectionClosed


async def send_message(request):
    ws = await request.accept()

    buses = {
        'msgType': 'Buses',
        'buses': [],
    }

    while True:
        try:
            message = await ws.get_message()
            coordinate = json.loads(message)
            if coordinate.get('msgType') == 'newBounds':
                continue

            print('Received message: %s' % message)
            buses['buses'].append(coordinate)
            await ws.send_message(json.dumps(buses))
        except ConnectionClosed:
            break


async def main():
    await serve_websocket(send_message, '127.0.0.1', 8000, ssl_context=None)


if __name__ == '__main__':
    trio.run(main)

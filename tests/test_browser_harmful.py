from server import Bounds
from validators import is_instance_valid


async def test_bounds_success():
    message = (
        '{"msgType": "newBounds", "data": {"east_lng": 37.65563964843751, "north_lat": 55.77367652953477, '
        '"south_lat": 55.72628839374007, "west_lng": 37.54440307617188}}'
    )
    is_valid, message = is_instance_valid(message, Bounds)
    assert is_valid


async def test_requires_valid_json():
    is_valid, message = is_instance_valid('message', Bounds)
    assert not is_valid
    assert (
        message == '{"errors": ["Requires valid JSON"], "msgType": "Errors"}'
    )


async def test_requires_msg_type_specified():
    message = (
        '{"msgType": 185, "data": {"east_lng": 37.65563964843751, "north_lat": 55.77367652953477, '
        '"south_lat": 55.72628839374007, "west_lng": 37.54440307617188}}'
    )
    is_valid, message = is_instance_valid(
        message,
        Bounds,
    )
    assert not is_valid
    assert 'Тип сообщения должен быть строкой "newBounds".' in message


async def test_requires_east_lng_type_specified():
    message = (
        '{"msgType": "newBounds", "data": {"east_lng": "error", "north_lat": 55.77367652953477, '
        '"south_lat": 55.72628839374007, "west_lng": 37.54440307617188}}'
    )
    is_valid, message = is_instance_valid(
        message,
        Bounds,
    )
    assert not is_valid
    assert (
        'Правая граница карты должна быть числом с плавающей точкой.'
        in message
    )


async def test_requires_struct_specified():
    message = (
        '{"msgType": "newBounds", "data": {"east_lng": 37.65563964843751, "north_lat": 55.77367652953477, '
        '"south_lat": 55.72628839374007, "west_lng": 37.54440307617188, "some": "field"}, "some": "field"}'
    )
    is_valid, message = is_instance_valid(
        message,
        Bounds,
    )
    assert not is_valid
    assert (
        message
        == '{"errors": ["Requires msgType specified"], "msgType": "Errors"}'
    )

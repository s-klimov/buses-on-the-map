from server import Bus
from validators import is_coordinate_valid


async def test_requires_valid_json():
    is_valid, message = is_coordinate_valid('message', Bus)
    assert not is_valid
    assert (
        message == '{"errors": ["Requires valid JSON"], "msgType": "Errors"}'
    )


async def test_requires_lng_type_specified():
    is_valid, message = is_coordinate_valid(
        '{"busId": "c790сс", "lat": "c55.7500", "lng": 37.600, "route": "120"}',
        Bus,
    )
    assert not is_valid
    assert (
        'Географическая широта местоположения автобуса должна быть числом с плавающей точкой.'
        in message
    )


async def test_requires_lat_type_specified():
    is_valid, message = is_coordinate_valid(
        '{"busId": "c790сс", "lat": 55.7500, "lng": "c37.600", "route": "120"}',
        Bus,
    )
    assert not is_valid
    assert (
        'Географическая долгота местоположения автобуса должна быть числом с плавающей точкой.'
        in message
    )


async def test_requires_lat_type_specified():
    is_valid, message = is_coordinate_valid(
        '{"busId": "c790сс", "lat": 55.7500, "lng": 37.600, "route": "120", "some": "field"}',
        Bus,
    )
    assert not is_valid
    assert (
        message
        == '{"errors": ["Requires msgType specified"], "msgType": "Errors"}'
    )

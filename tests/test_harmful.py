import pytest
import trio


@pytest.mark.trio
async def test_sleep():
    start_time = trio.current_time()
    await trio.sleep(1)
    end_time = trio.current_time()
    assert end_time - start_time >= 1


async def test_should_fail():
    assert False

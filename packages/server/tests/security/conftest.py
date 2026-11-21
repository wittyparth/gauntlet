import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def clean_redis(state):
    async def wipe() -> None:
        async for k in state.redis.scan_iter("gauntlet:*"):
            if not k.decode().startswith("gauntlet:run:"):
                await state.redis.delete(k)

    await wipe()
    yield
    await wipe()

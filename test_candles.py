import asyncio

from config.loader import load_config
from pocketoptionapi_async import AsyncPocketOptionClient


async def main():
    config = load_config()

    client = AsyncPocketOptionClient(
        config.pocket_option.ssid,
        is_demo=config.pocket_option.is_demo,
        enable_logging=True,
    )

    connected = await client.connect()

    print()
    print("CONNECTED =", connected)

    if not connected:
        return

    print("IS_DEMO =", client.is_demo)

    try:
        candles = await client.get_candles(
            asset="EURUSD",
            timeframe=60,
            count=5,
        )

        print()
        print("CANDLES:")
        print(candles)

    except Exception as e:
        print()
        print("CANDLE ERROR:", repr(e))

    finally:
        await client.disconnect()


asyncio.run(main())

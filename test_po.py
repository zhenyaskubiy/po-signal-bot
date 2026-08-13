import asyncio
from config.loader import load_config
from pocketoptionapi_async import AsyncPocketOptionClient

async def main():
    cfg = load_config()

    print("is_demo:", cfg.pocket_option.is_demo)

    client = AsyncPocketOptionClient(
        cfg.pocket_option.ssid,
        is_demo=cfg.pocket_option.is_demo,
        enable_logging=True,
    )

    print("client.is_demo:", client.is_demo)
    print("uid:", client.uid)
    print("session:", client.session_id[:20] + "...")

    print("\nПідключення...")

    connected = await client.connect()

    print("\nCONNECTED =", connected)

    if connected:
        try:
            balance = await client.get_balance()
            print("BALANCE =", balance.balance)
            print("CURRENCY =", balance.currency)
        except Exception as e:
            print("GET BALANCE ERROR:", repr(e))

asyncio.run(main())

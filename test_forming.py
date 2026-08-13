import asyncio
from datetime import datetime, timezone

from pocketoptionapi_async import AsyncPocketOptionClient

from config.loader import load_config


async def main():
    cfg = load_config()

    client = AsyncPocketOptionClient(
        cfg.pocket_option.ssid,
        is_demo=cfg.pocket_option.is_demo,
        enable_logging=False,
    )

    connected = await client.connect()

    if not connected:
        print("❌ Не вдалося підключитися")
        return

    print("✅ Підключено")
    print("")

    asset = "EURUSD_otc"
    timeframe = 60

    try:
        for i in range(70):
            candles = await client.get_candles(
                asset=asset,
                timeframe=timeframe,
                count=3,
            )

            if not candles:
                print("❌ Свічки не отримані")
                await asyncio.sleep(1)
                continue

            candles.sort(
                key=lambda c: c.timestamp
            )

            latest = candles[-1]

            dt = latest.timestamp

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            print(
                f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} | "
                f"candle={dt.strftime('%H:%M:%S')} | "
                f"O={latest.open} | "
                f"H={latest.high} | "
                f"L={latest.low} | "
                f"C={latest.close}"
            )

            await asyncio.sleep(1)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
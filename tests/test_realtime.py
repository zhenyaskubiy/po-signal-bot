import asyncio
import json

from pocketoptionapi_async import AsyncPocketOptionClient


# ============================================================
# REAL ACCOUNT
# ============================================================

SESSION = r'''a:4:{s:10:"session_id";s:32:"4c876861e67e47532ade2b864ff5310d";s:10:"ip_address";s:13:"78.137.22.161";s:10:"user_agent";s:117:"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.3 Safari/605.1.15";s:13:"last_activity";i:1786663123;}434c894736720451e969979d404c5dc7'''

UID = 99335428
ASSET = "EURUSD"


# ============================================================
# FORMING SSID
# ============================================================

SSID = "42" + json.dumps(
    [
        "auth",
        {
            "session": SESSION,
            "isDemo": 0,
            "uid": UID,
            "platform": 1,
            "isFastHistory": True,
            "isOptimized": True,
        },
    ],
    separators=(",", ":"),
)


# ============================================================
# MAIN
# ============================================================

async def main():

    print("🔌 Створюємо клієнт...")

    client = AsyncPocketOptionClient(
        SSID,
        is_demo=False,
        enable_logging=True,
    )

    async def on_stream(data):

        if data.get("asset") != ASSET:
            return

        print("\n📡 STREAM UPDATE:")
        print(data)

    client.add_event_callback(
        "stream_update",
        on_stream,
    )

    print("🔌 Підключення до REAL Pocket Option...")

    connected = await client.connect()

    if not connected:
        print("❌ Не підключено")
        return

    print()
    print("========================================")
    print("✅ ПІДКЛЮЧЕНО ДО REAL POCKET OPTION")
    print("========================================")
    print(f"📈 Asset: {ASSET}")
    print("👂 Очікуємо realtime stream...")
    print("🛑 Ctrl+C для виходу")
    print()

    try:
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        pass

    finally:
        print("\n🔌 Відключення...")
        await client.disconnect()
        print("✅ Відключено")


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\n🛑 Зупинено.")
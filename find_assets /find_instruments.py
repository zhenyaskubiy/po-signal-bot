
import asyncio
import logging
import json

from pocketoptionapi_async import AsyncPocketOptionClient
from config.loader import load_config


logging.basicConfig(level=logging.WARNING)


async def main():
    cfg = load_config()

    client = AsyncPocketOptionClient(
        cfg.pocket_option.ssid,
        is_demo=cfg.pocket_option.is_demo,
        enable_logging=True,
    )

    websocket = client._websocket

    all_assets = []
    otc_assets = []
    received_messages = 0

    async def handle_json_data(data):
        nonlocal received_messages

        received_messages += 1

        if not isinstance(data, list):
            return

        # У твоїй версії бібліотеки updateAssets приходить
        # як JSON bytes і потрапляє сюди через подію "json_data".
        #
        # Типовий asset:
        # [5, '#AAPL', 'Apple', 'stock', ...]

        for item in data:

            if not isinstance(item, list):
                continue

            if len(item) < 4:
                continue

            asset_id = item[0]
            symbol = item[1]
            name = item[2]
            asset_type = item[3]

            if not isinstance(symbol, str):
                continue

            # Зберігаємо все, що схоже на інструмент
            asset = {
                "id": asset_id,
                "symbol": symbol,
                "name": name,
                "type": asset_type,
                "raw": item,
            }

            # Уникаємо дублікатів
            if not any(
                existing["symbol"] == symbol
                for existing in all_assets
            ):
                all_assets.append(asset)

                if "_otc" in symbol.lower():
                    otc_assets.append(asset)

    # Головне: ловимо json_data ДО підключення
    websocket.add_event_handler(
        "json_data",
        handle_json_data
    )

    print("=" * 70)
    print("🔌 ПІДКЛЮЧЕННЯ ДО POCKET OPTION")
    print("=" * 70)

    connected = await client.connect()

    if not connected:
        print("❌ Не вдалося підключитися")
        return

    print("✅ Підключено!")

    print("\n" + "=" * 70)
    print("📡 ОЧІКУЄМО UPDATEASSETS")
    print("=" * 70)

    # Чекаємо всі початкові дані від сервера
    await asyncio.sleep(10)

    print("\n" + "=" * 70)
    print("📊 РЕЗУЛЬТАТ")
    print("=" * 70)

    print(f"\n📦 JSON-повідомлень отримано: {received_messages}")
    print(f"📊 Унікальних інструментів: {len(all_assets)}")
    print(f"📈 OTC-інструментів: {len(otc_assets)}")

    # ---------------------------------------------------------
    # ВСІ ІНСТРУМЕНТИ
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("📊 ВСІ ЗНАЙДЕНІ ІНСТРУМЕНТИ")
    print("=" * 70)

    if all_assets:

        for asset in all_assets:
            print(
                f"{asset['symbol']:<30} | "
                f"{str(asset['name']):<30} | "
                f"{asset['type']}"
            )

    else:
        print("❌ Інструменти не знайдені.")

    # ---------------------------------------------------------
    # OTC
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("💱 OTC ІНСТРУМЕНТИ")
    print("=" * 70)

    if otc_assets:

        for asset in otc_assets:
            print(
                f"{asset['symbol']:<30} | "
                f"{str(asset['name']):<30} | "
                f"{asset['type']}"
            )

    else:
        print("❌ OTC-інструменти не знайдені.")

    # ---------------------------------------------------------
    # ЗРУЧНИЙ СПИСОК ДЛЯ БОТА
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("🐍 СПИСОК ДЛЯ SIGNAL BOT")
    print("=" * 70)

    if otc_assets:

        symbols = [
            asset["symbol"]
            for asset in otc_assets
        ]

        print("\nINSTRUMENTS = [")

        for symbol in symbols:
            print(f'    "{symbol}",')

        print("]")

    # ---------------------------------------------------------
    # ВИВОДИМО RAW ПЕРШОГО OTC
    # ---------------------------------------------------------
    #
    # Це дуже важливо, якщо структура asset відрізняється.
    # Ми побачимо повний запис сервера.
    #

    if otc_assets:

        print("\n" + "=" * 70)
        print("🔬 RAW ДАНІ ПЕРШОГО OTC")
        print("=" * 70)

        print(
            json.dumps(
                otc_assets[0]["raw"],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

    print("\n" + "=" * 70)
    print("🔌 ВІДКЛЮЧЕННЯ")
    print("=" * 70)

    await client.disconnect()

    print("✅ Готово.")


if __name__ == "__main__":
    asyncio.run(main())

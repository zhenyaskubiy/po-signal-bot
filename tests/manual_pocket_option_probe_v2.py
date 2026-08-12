"""
РОЗВІДУВАЛЬНИЙ скрипт #2 — для бібліотеки pocketoptionapi-async
(альтернатива BinaryOptionsToolsV2, яка постійно рвала з'єднання).

НЕ частина автоматичних тестів, запускається вручну.

Як користуватись:
1. Той самий SSID, що вже є в config/settings.yaml (pocket_option.ssid) —
   міняти нічого не треба, спробуємо той самий рядок з новою бібліотекою.
2. Запустіть:
       python -m tests.manual_pocket_option_probe_v2
3. Скрипт підключиться, покаже баланс і кілька перших свічок — після
   цього сам зупиниться.
4. Скопіюйте весь вивід і покажіть його.

Зупинка вручну: Ctrl+C.
"""

from __future__ import annotations

import asyncio

from pocketoptionapi_async import AsyncPocketOptionClient

from config.loader import load_config

PROBE_INSTRUMENT = "EURUSD_otc"


async def main() -> None:
    cfg = load_config()

    if cfg.data_source != "pocket_option" or "ВАШ_SESSION_TOKEN" in cfg.pocket_option.ssid:
        print(
            "У config/settings.yaml потрібно data_source: \"pocket_option\" "
            "і реальний pocket_option.ssid — зараз там плейсхолдер."
        )
        return

    print(f"Підключаюсь до Pocket Option через pocketoptionapi-async (demo={cfg.pocket_option.is_demo})...")
    client = AsyncPocketOptionClient(cfg.pocket_option.ssid, is_demo=cfg.pocket_option.is_demo)

    try:
        connected = await client.connect()
        print(f"connect() повернув: {connected}")
    except Exception as e:
        print(f"❌ Помилка при connect(): {e}")
        return

    try:
        balance = await client.get_balance()
        print(f"\n✅ Тип балансу: {type(balance)}")
        print(f"Вміст: {balance}")
        if hasattr(balance, "balance"):
            print(f"balance.balance = {balance.balance}, balance.currency = {getattr(balance, 'currency', '?')}\n")
    except Exception as e:
        print(f"❌ Помилка при get_balance(): {e}")

    print(f"Пробую отримати свічки по {PROBE_INSTRUMENT}...\n")
    try:
        candles = await client.get_candles(asset=PROBE_INSTRUMENT, timeframe=60)
        print("=" * 60)
        print(f"Тип candles: {type(candles)}, кількість: {len(candles) if hasattr(candles, '__len__') else '?'}")
        for i, candle in enumerate(candles):
            print(f"  #{i}: {candle}")
            if i >= 4:
                break
        print("=" * 60)
    except Exception as e:
        print(f"❌ Помилка при get_candles(): {e}")

    await client.disconnect()
    print("\nВідключено. Розвідку завершено — скопіюйте весь вивід вище.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nЗупинено вручну.")
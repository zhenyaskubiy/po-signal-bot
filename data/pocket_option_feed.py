"""
Реальне підключення до Pocket Option через pocketoptionapi-async.

⚠️ ВАЖЛИВО (підтверджено діагностикою 15.08):
get_candles() у цій бібліотеці повертає ЗАМОРОЖЕНИЙ кеш — однакові дані
щоразу, незалежно від того, скільки реального часу пройшло. Тому свічки
для реального аналізу БІЛЬШЕ НЕ БЕРУТЬСЯ звідти.

Натомість свічки будуються самостійно з живого потоку тіків
(add_event_callback("stream_update", ...)), який підтверджено ДІЙСНО
живий — ціни в ньому змінюються щосекунди.

get_candles() лишається тільки для одноразового "розігріву" історії
при підключенні (щоб Supertrend одразу мав дані для ATR), а не для
відстеження нових свічок у реальному часі.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pocketoptionapi_async import AsyncPocketOptionClient

from core.candle import Candle

logger = logging.getLogger(__name__)


class PocketOptionFeed:
    def __init__(self, ssid: str, is_demo: bool = True, timeframe_seconds: int = 60):
        self.ssid = ssid
        self.is_demo = is_demo
        self.timeframe_seconds = timeframe_seconds

        self._client: Optional[AsyncPocketOptionClient] = None
        self._payouts: Dict[str, float] = {}

        # Свічка, яка зараз "будується" з живих тіків — по одній на інструмент.
        self._forming: Dict[str, Candle] = {}
        # Черга вже завершених (закритих) свічок, які ще не забрав engine.
        self._closed_queue: Dict[str, List[Candle]] = {}

        self._last_logged_price_ts: Dict[str, float] = {}

    # ============================================================
    # LIVE STREAM — тут відбувається вся реальна робота
    # ============================================================

    async def _on_stream_update(self, data) -> None:
        if not isinstance(data, dict) or "_placeholder" in data:
            return

        asset = data.get("asset")
        ticks = data.get("data")
        if not asset or not ticks:
            return

        # Обробляємо ВСІ тіки в пачці (не тільки останній) — щоб не пропустити
        # момент переходу через межу хвилини, якщо кілька тіків прийшли разом.
        for tick in ticks:
            try:
                tick_ts = float(tick[0])
                price = float(tick[1])
            except (TypeError, ValueError, IndexError):
                continue

            self._absorb_tick(asset, tick_ts, price)

        self._last_logged_price_ts[asset] = float(ticks[-1][0])

    def _absorb_tick(self, asset: str, tick_ts: float, price: float) -> None:
        bucket_start = int(tick_ts // self.timeframe_seconds * self.timeframe_seconds)
        current = self._forming.get(asset)

        if current is None:
            # Перший тік для цього інструменту — просто починаємо нову свічку
            self._forming[asset] = Candle(
                open=price, high=price, low=price, close=price, timestamp=bucket_start
            )
            return

        if current.timestamp == bucket_start:
            # Той самий часовий інтервал — оновлюємо high/low/close поточної свічки
            self._forming[asset] = Candle(
                open=current.open,
                high=max(current.high, price),
                low=min(current.low, price),
                close=price,
                timestamp=bucket_start,
            )
            return

        if bucket_start > current.timestamp:
            # Почалась нова хвилина — попередня свічка щойно ЗАКРИЛАСЬ
            self._closed_queue.setdefault(asset, []).append(current)
            self._forming[asset] = Candle(
                open=price, high=price, low=price, close=price, timestamp=bucket_start
            )
            logger.info(
                "🔒 Закрито свічку з живого потоку | %s | %s | O:%.5f H:%.5f L:%.5f C:%.5f",
                asset,
                self._format_timestamp(current.timestamp),
                current.open, current.high, current.low, current.close,
            )
        # bucket_start < current.timestamp — застарілий тік, ігноруємо

    # ============================================================
    # CONNECT
    # ============================================================

    async def connect(self, instruments: Optional[List[str]] = None) -> None:
        logger.info("🔌 Підключення до Pocket Option...")

        self._client = AsyncPocketOptionClient(self.ssid, is_demo=self.is_demo, enable_logging=False)
        self._client.add_event_callback("stream_update", self._on_stream_update)

        connected = await self._client.connect()
        if not connected:
            raise RuntimeError("Не вдалося підключитися до Pocket Option. Перевір SSID.")

        balance = await self._client.get_balance()
        logger.info("✅ Підключено до Pocket Option | Баланс: %s %s", balance.balance, balance.currency)

        # Обов'язково викликаємо get_candles для кожного активу, 
        # щоб сервер Pocket Option відкрив підписку на WebSocket-потік цього символу
        if instruments:
            for instrument in instruments:
                try:
                    await self._client.get_candles(asset=instrument, timeframe=self.timeframe_seconds, count=10)
                    logger.info("📡 Активовано потік для інструменту: %s", instrument)
                except Exception as e:
                    logger.error("❌ Помилка активації потоку для %s: %s", instrument, e)

    # ============================================================
    # PAYOUT (відомий ліміт бібліотеки — див. попередні повідомлення)
    # ============================================================

    async def refresh_payouts(self) -> None:
        logger.warning("⚠️ Реальний payout недоступний через цю бібліотеку — використовується 100%% для всіх.")
        self._payouts = {}

    def get_payout(self, instrument: str) -> float:
        return self._payouts.get(instrument, 100.0)

    # ============================================================
    # ІНТЕРФЕЙС ДЛЯ InstrumentEngine
    # ============================================================

    async def get_latest_closed_candle(self, instrument: str, timeframe_seconds: int) -> Optional[Candle]:
        queue = self._closed_queue.get(instrument)
        if not queue:
            return None
        return queue.pop(0)  # FIFO — не пропускаємо жодної закритої свічки

    async def get_current_forming_candle(self, instrument: str, timeframe_seconds: int) -> Optional[Candle]:
        return self._forming.get(instrument)

    async def get_latest_candle(self, instrument: str, timeframe_seconds: int) -> Optional[Candle]:
        """Сумісність зі старим інтерфейсом — повертає тільки закриту."""
        return await self.get_latest_closed_candle(instrument, timeframe_seconds)

    # ============================================================
    # УТИЛІТИ
    # ============================================================

    @staticmethod
    def _format_timestamp(timestamp: float) -> str:
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "INVALID"

    # ============================================================
    # DISCONNECT
    # ============================================================

    async def disconnect(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.disconnect()
            logger.info("🔌 Відключено від Pocket Option.")
        finally:
            self._client = None
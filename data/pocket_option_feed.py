"""
Реальне підключення до Pocket Option через pocketoptionapi-async.

Головне правило:

    candles[-1] -> НАЙСВІЖІША / формуюча свічка
    candles[-2] -> остання повністю ЗАКРИТА свічка

Формуюча свічка:
    - НЕ передається в Supertrend;
    - НЕ передається в CandleCounter;
    - використовується тільки для confirmation.

Закрита свічка:
    - передається в InstrumentEngine;
    - використовується для Supertrend;
    - використовується для CandleCounter.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import time
from pocketoptionapi_async import AsyncPocketOptionClient

from core.candle import Candle


logger = logging.getLogger(__name__)


class PocketOptionFeed:
    
    def __init__(
        self,
        ssid: str,
        is_demo: bool = True,
    ):
        self.ssid = ssid
        self.is_demo = is_demo

        self._client: Optional[AsyncPocketOptionClient] = None

        # --------------------------------------------------------
        # Payout
        # --------------------------------------------------------

        self._payouts: dict[str, float] = {}

        # --------------------------------------------------------
        # Діагностика / захист від дублювання логів
        # --------------------------------------------------------

        self._last_closed_timestamp: dict[str, float] = {}
        self._last_forming_timestamp: dict[str, float] = {}
        self._last_latest_timestamp: dict[str, float] = {}
        
# ============================================================
# LIVE STREAM
# ============================================================

    async def _on_stream_update(
        self,
        data,
    ) -> None:

        if "_placeholder" in data:
            return

        asset = data.get("asset")
        ticks = data.get("data")

        if not asset or not ticks:
            return

        price = ticks[-1][1]

        logger.info(
            "📈 %s | price %.5f",
            asset,
            price
        )
    # ============================================================
    # CONNECT
    # ============================================================

    async def connect(self) -> None:
        """
        Підключення до Pocket Option.
        """

        logger.info("🔌 Підключення до Pocket Option...")

        self._client = AsyncPocketOptionClient(
            self.ssid,
            is_demo=self.is_demo,
            enable_logging=False,
        )

        self._client.add_event_callback(
                    "stream_update",
                    self._on_stream_update
                )

        connected = await self._client.connect()

        if not connected:
            raise RuntimeError(
                "Не вдалося підключитися до Pocket Option. "
                "Перевір SSID."
            )

        balance = await self._client.get_balance()

        logger.info(
            "✅ Підключено до Pocket Option | Баланс: %s %s",
            balance.balance,
            balance.currency,
        )

    # ============================================================
    # PAYOUT
    # ============================================================

    async def refresh_payouts(self) -> None:
        """
        Поки що реальний payout не отримуємо.

        Значення 100.0 нижче — лише fallback для роботи
        логіки сигналів.
        """

        logger.warning(
            "⚠️ Реальний payout поки недоступний "
            "через поточну версію pocketoptionapi_async."
        )

        self._payouts = {}

    def get_payout(self, instrument: str) -> float:
        """
        Повертає payout.

        Якщо реальний payout не отриманий,
        використовується 100%.
        """

        return self._payouts.get(
            instrument,
            100.0,
        )

    # ============================================================
    # TIMESTAMP
    # ============================================================
    @staticmethod
    def _timestamp_to_float(
        timestamp,
    ) -> Optional[float]:

        if timestamp is None:
            return None

        try:

            # datetime
            if hasattr(timestamp, "timestamp"):
                return float(timestamp.timestamp())

            # int / float / numeric string
            return float(timestamp)

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None
    # ============================================================
    # RAW -> Candle
    # ============================================================

    @staticmethod
    def _to_candle(
        raw_candle,
    ) -> Optional[Candle]:
        """
        Перетворює raw-свічку API у нашу Candle.

        Некоректні свічки відкидаються.
        """

        # --------------------------------------------------------
        # Timestamp
        # --------------------------------------------------------

        timestamp = PocketOptionFeed._timestamp_to_float(
            getattr(
                raw_candle,
                "timestamp",
                None,
            )
        )

        if timestamp is None:
            return None

        # --------------------------------------------------------
        # OHLC
        # --------------------------------------------------------

        try:

            open_price = float(
                raw_candle.open
            )

            high_price = float(
                raw_candle.high
            )

            low_price = float(
                raw_candle.low
            )

            close_price = float(
                raw_candle.close
            )

        except (
            TypeError,
            ValueError,
            AttributeError,
        ):
            return None

        # --------------------------------------------------------
        # Перевірка OHLC
        # --------------------------------------------------------

        if high_price < max(
            open_price,
            close_price,
        ):
            logger.warning(
                "⚠️ Відкинуто некоректну свічку: "
                "high < open/close"
            )
            return None

        if low_price > min(
            open_price,
            close_price,
        ):
            logger.warning(
                "⚠️ Відкинуто некоректну свічку: "
                "low > open/close"
            )
            return None

        # --------------------------------------------------------
        # Створюємо Candle
        # --------------------------------------------------------

        return Candle(
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            timestamp=timestamp,
        )

    # ============================================================
    # RAW CANDLES
    # ============================================================

    async def _get_raw_candles(
        self,
        instrument: str,
        timeframe_seconds: int,
    ):
        """
        Отримує історичні свічки з Pocket Option.
        """

        if self._client is None:
            raise RuntimeError(
                "Pocket Option client ще не підключений."
            )

        candles = await self._client.get_candles(
            asset=instrument,
            timeframe=timeframe_seconds,
            count=100,
        )

        if not candles:

            logger.warning(
                "⚠️ %s: Pocket Option не повернув свічки.",
                instrument,
            )

            return []
        
        logger.info(
            "RAW CANDLES %s: %s",
            instrument,
            candles[-3:]
        )

        return candles

    # ============================================================
    # SORTED CANDLES
    # ============================================================

    async def _get_sorted_candles(
        self,
        instrument: str,
        timeframe_seconds: int,
    ) -> list[Candle]:
        """
        Отримує та нормалізує свічки.

        Результат:

            [найстаріша, ..., передостання, найновіша]

        Тобто:

            candles[-1] = найсвіжіша
            candles[-2] = передостання
        """

        raw_candles = await self._get_raw_candles(
            instrument=instrument,
            timeframe_seconds=timeframe_seconds,
        )

        if not raw_candles:
            return []

        candles: list[Candle] = []

        for raw_candle in raw_candles:

            candle = self._to_candle(
                raw_candle
            )

            if candle is not None:
                candles.append(candle)

        if not candles:

            logger.warning(
                "⚠️ %s: жодна свічка не пройшла "
                "перевірку timestamp/OHLC.",
                instrument,
            )

            return []

        # --------------------------------------------------------
        # КРИТИЧНО:
        # завжди сортуємо за timestamp
        # --------------------------------------------------------

        candles.sort(
            key=lambda candle: candle.timestamp
        )

        return candles

    # ============================================================
    # FORMAT TIMESTAMP
    # ============================================================

    @staticmethod
    def _format_timestamp(timestamp: float) -> str:
        try:
            return datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        except Exception:
            return "INVALID"
    # ============================================================
    # DIRECTION
    # ============================================================

    @staticmethod
    def _direction(
        candle: Candle,
    ) -> str:

        if candle.close > candle.open:
            return "🟢 BULLISH"

        if candle.close < candle.open:
            return "🔴 BEARISH"

        return "⚪ DOJI"

    # ============================================================
    # LOG LATEST
    # ============================================================

    def _log_latest_candle(
        self,
        instrument: str,
        candle: Candle,
    ) -> None:
        """
        Логує найсвіжішу свічку один раз.
        """

        previous = self._last_latest_timestamp.get(
            instrument
        )

        if previous == candle.timestamp:
            return

        self._last_latest_timestamp[
            instrument
        ] = candle.timestamp

        logger.info(
            "🕯 НАЙСВІЖІША СВІЧКА | %s | %s\n"
            "   Open:  %.5f\n"
            "   High:  %.5f\n"
            "   Low:   %.5f\n"
            "   Close: %.5f\n"
            "   Напрямок: %s\n"
            "   timestamp: %.0f",
            instrument,
            self._format_timestamp(
                candle.timestamp
            ),
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            self._direction(candle),
            candle.timestamp,
        )

    # ============================================================
    # GET LATEST CLOSED CANDLE
    # ============================================================

    async def get_latest_closed_candle(
        self,
        instrument: str,
        timeframe_seconds: int,
    ) -> Optional[Candle]:
        """
        Повертає ОСТАННЮ ПОВНІСТЮ ЗАКРИТУ свічку.

        Вважаємо:

            candles[-1] -> формуюча
            candles[-2] -> закрита

        Формуюча свічка тут НІКОЛИ не повертається.
        """

        candles = await self._get_sorted_candles(
            instrument=instrument,
            timeframe_seconds=timeframe_seconds,
        )

        # --------------------------------------------------------
        # Немає свічок
        # --------------------------------------------------------

        if not candles:
            return None

        # --------------------------------------------------------
        # Найсвіжіша
        # --------------------------------------------------------

        latest = candles[-1]

        self._log_latest_candle(
            instrument=instrument,
            candle=latest,
        )

        # --------------------------------------------------------
        # Потрібні мінімум 2 свічки
        # --------------------------------------------------------

        if len(candles) < 2:

            logger.warning(
                "⚠️ %s: недостатньо свічок. "
                "Потрібно мінімум 2.",
                instrument,
            )

            return None

        # --------------------------------------------------------
        # Передостання = закрита
        # --------------------------------------------------------

        closed = candles[-2]

        # --------------------------------------------------------
        # Захист від повторної передачі
        # --------------------------------------------------------

        previous_timestamp = (
            self._last_closed_timestamp.get(
                instrument
            )
        )

        if previous_timestamp == closed.timestamp:
            return None

        self._last_closed_timestamp[
            instrument
        ] = closed.timestamp

        # --------------------------------------------------------
        # Лог
        # --------------------------------------------------------

        logger.info(
            "🔒 НОВА ЗАКРИТА СВІЧКА | %s | %s\n"
            "   Open:  %.5f\n"
            "   High:  %.5f\n"
            "   Low:   %.5f\n"
            "   Close: %.5f\n"
            "   Напрямок: %s\n"
            "   timestamp: %.0f",
            instrument,
            self._format_timestamp(
                closed.timestamp
            ),
            closed.open,
            closed.high,
            closed.low,
            closed.close,
            self._direction(closed),
            closed.timestamp,
        )

        return closed

    # ============================================================
    # GET CURRENT FORMING CANDLE
    # ============================================================

    async def get_current_forming_candle(
        self,
        instrument: str,
        timeframe_seconds: int,
    ) -> Optional[Candle]:
        """
        Повертає найсвіжішу формуючу свічку.

        Вона використовується ТІЛЬКИ для confirmation.

        Вона НЕ передається:

            Supertrend
            CandleCounter
        """

        candles = await self._get_sorted_candles(
            instrument=instrument,
            timeframe_seconds=timeframe_seconds,
        )

        if not candles:
            return None

        # --------------------------------------------------------
        # Найсвіжіша = формуюча
        # --------------------------------------------------------

        forming = candles[-1]

        previous_timestamp = (
            self._last_forming_timestamp.get(
                instrument
            )
        )

        # --------------------------------------------------------
        # Логуємо тільки коли почалася нова свічка
        # --------------------------------------------------------

# --------------------------------------------------------
# Логуємо тільки коли почалася нова свічка
# --------------------------------------------------------

        if previous_timestamp != forming.timestamp:

            self._last_forming_timestamp[
                instrument
            ] = forming.timestamp

            logger.info(
                "🟡 НОВА ФОРМУЮЧА СВІЧКА | %s | %s\n"
                "   Open:  %.5f\n"
                "   High:  %.5f\n"
                "   Low:   %.5f\n"
                "   Close: %.5f\n"
                "   Напрямок: %s\n"
                "   timestamp: %.0f",
                instrument,
                self._format_timestamp(
                    forming.timestamp
                ),
                forming.open,
                forming.high,
                forming.low,
                forming.close,
                self._direction(forming),
                forming.timestamp,
            )
        return forming
    # ============================================================
    # COMPATIBILITY
    # ============================================================

    async def get_latest_candle(
        self,
        instrument: str,
        timeframe_seconds: int,
    ) -> Optional[Candle]:
        """
        Старий метод для сумісності.

        ПОВЕРТАЄ ТІЛЬКИ ЗАКРИТУ свічку.

        Формуюча сюди не потрапляє.
        """

        return await self.get_latest_closed_candle(
            instrument=instrument,
            timeframe_seconds=timeframe_seconds,
        )

    # ============================================================
    # DISCONNECT
    # ============================================================

    async def disconnect(self) -> None:
        """
        Відключення від Pocket Option.
        """

        if self._client is None:
            return

        try:

            await self._client.disconnect()

            logger.info(
                "🔌 Відключено від Pocket Option."
            )

        finally:

            self._client = None
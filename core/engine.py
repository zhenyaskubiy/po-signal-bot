"""
Основний двигун аналізу одного інструменту.

Логіка:

1. Отримуємо тільки ЗАКРИТІ свічки.
2. Закриті свічки послідовно передаємо:
       Candle -> Supertrend -> CandleCounter
3. Коли серія антитрендових свічок досягає потрібної кількості,
   створюємо WARNING через SignalQueue.
4. Після WARNING окремо перевіряємо ПОТОЧНУ формуючу свічку.
5. Формуюча свічка НЕ потрапляє в Supertrend/CandleCounter.
6. Якщо через confirmation_delay_seconds вона все ще антитрендова,
   SignalQueue повертає CALL/PUT.
7. Якщо вона розвернулась — сигнал скасовується.

Для simulator використовується run_with_feed().
Для Pocket Option — run_with_live_feed().
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional, Protocol

from core.candle import Candle
from core.candle_counter import CandleCounter
from core.runtime_settings import RuntimeSettingsStore
from core.signal_queue import SignalEvent, SignalQueue
from core.supertrend import SupertrendCalculator

logger = logging.getLogger(__name__)


# ============================================================
# Типи
# ============================================================

SignalCallback = Callable[[SignalEvent], Awaitable[None]]


class CandleFeed(Protocol):
    """
    Мінімальний інтерфейс джерела свічок.

    Симулятор може мати тільки get_latest_candle().
    Реальний Pocket Option Feed додатково має:
      - get_latest_closed_candle()
      - get_current_forming_candle()
    """

    async def get_latest_candle(
        self,
        instrument: str,
        timeframe_seconds: int,
    ) -> Optional[Candle]:
        ...


# ============================================================
# InstrumentEngine
# ============================================================

class InstrumentEngine:
    """
    Аналіз одного інструменту.

    Для кожного інструменту створюється окремий екземпляр.
    """

    def __init__(
        self,
        instrument: str,
        signal_queue: SignalQueue,
        supertrend_atr_period: int = 10,
        supertrend_multiplier: float = 3.0,
        timeframe_seconds: int = 60,
        min_payout_percent: float = 0.0,
        runtime_settings: Optional[RuntimeSettingsStore] = None,
    ):
        self.instrument = instrument
        self.signal_queue = signal_queue

        self.timeframe_seconds = timeframe_seconds
        self.min_payout_percent = min_payout_percent

        self.runtime_settings = runtime_settings

        # Індикатор Supertrend.
        self.supertrend = SupertrendCalculator(
            atr_period=supertrend_atr_period,
            multiplier=supertrend_multiplier,
        )

        # Лічильник антитрендових свічок.
        self.candle_counter = CandleCounter()

        # Остання ЗАКРИТА свічка, яку ми вже обробили.
        self._last_processed_timestamp: Optional[float] = None

        # Останній відомий Supertrend.
        self._last_supertrend_direction: Optional[str] = None

        # Для діагностики.
        self._processed_candles = 0

    # --------------------------------------------------------
    # Налаштування
    # --------------------------------------------------------

    def _required_candles(self) -> int:
        """
        Кількість антитрендових свічок, необхідна для WARNING.

        Якщо RuntimeSettingsStore доступний — беремо значення
        звідти, щоб його можна було змінювати через Telegram
        без перезапуску.
        """

        if self.runtime_settings is not None:
            return self.runtime_settings.get().required_anti_trend_candles

        # Значення за замовчуванням.
        return 4

    def _expiration_seconds(self) -> int:
        """
        Поточний час експірації.
        """

        if self.runtime_settings is not None:
            return self.runtime_settings.get().expiration_seconds

        return self.timeframe_seconds

    def reset_counter(self) -> None:
        """
        Скидає лічильник свічок і час останньої обробленої свічки,
        щоб бот почав підрахунок із чистого аркуста після зміни налаштувань.
        """
        self.candle_counter.state.count = 0
        self.candle_counter.state.locked_color = None
        self._last_processed_timestamp = None
        logger.info("%s: 🔄 Лічильник серії скинуто через зміну налаштувань.", self.instrument)

    # --------------------------------------------------------
    # Обробка однієї ЗАКРИТОЇ свічки
    # --------------------------------------------------------

    async def process_closed_candle(
        self,
        candle: Candle,
        payout: float,
        on_signal: SignalCallback,
    ) -> None:
        """
        Обробляє одну повністю закриту свічку.

        ВАЖЛИВО:
        сюди не повинна потрапляти формуюча свічка.
        """

        timestamp = float(candle.timestamp)

        # ----------------------------------------------------
        # Захист від повторної обробки
        # ----------------------------------------------------

        if self._last_processed_timestamp is not None:
            if timestamp <= self._last_processed_timestamp:
                return

        self._last_processed_timestamp = timestamp

        # ----------------------------------------------------
        # Supertrend
        # ----------------------------------------------------

        supertrend_result = self.supertrend.update(candle)

        current_direction = supertrend_result.direction

        logger.debug(
            "%s | Supertrend=%s | changed=%s | value=%.5f",
            self.instrument,
            current_direction,
            supertrend_result.changed,
            supertrend_result.value,
        )

        # ----------------------------------------------------
        # CandleCounter
        # ----------------------------------------------------

        previous_count = self.candle_counter.state.count

        state = self.candle_counter.update(
            candle=candle,
            supertrend_direction=current_direction,
            supertrend_changed=supertrend_result.changed,
        )

        self._last_supertrend_direction = current_direction
        self._processed_candles += 1

        logger.info(
            "%s: Supertrend=%s | антитренд=%s | серія=%d",
            self.instrument,
            current_direction,
            state.locked_color,
            state.count,
        )

        # ----------------------------------------------------
        # Перевіряємо досягнення потрібної кількості
        # ----------------------------------------------------

        required = self._required_candles()

        # Нам потрібен саме момент переходу:
        #
        # було 3
        # стало 4
        #
        # А не кожен наступний update зі значенням 4+.
        if previous_count < required <= state.count:

            # ------------------------------------------------
            # Перевірка payout
            # ------------------------------------------------

            if payout < self.min_payout_percent:
                logger.info(
                    "%s: серія досягла %d, але payout %.2f%% "
                    "нижче мінімального %.2f%% — сигнал не створюємо.",
                    self.instrument,
                    state.count,
                    payout,
                    self.min_payout_percent,
                )
                return

            if state.locked_color is None:
                logger.warning(
                    "%s: серія досягла %d, але locked_color=None.",
                    self.instrument,
                    state.count,
                )
                return

# ------------------------------------------------
            # Реєструємо досягнення серії (без відправки попереджень)
            # ------------------------------------------------

            self.signal_queue.on_series_reached(
                instrument=self.instrument,
                locked_color=state.locked_color,
                payout=payout,
                timeframe_seconds=self.timeframe_seconds,
                expiration_seconds=self._expiration_seconds(),
                required_candles=required,
            )

            logger.info(
                "%s: Серія досягла %d | Очікуємо підтвердження (без попередження)",
                self.instrument,
                state.count,
            )

    # --------------------------------------------------------
    # Перевірка поточної формуючої свічки
    # --------------------------------------------------------

    async def check_forming_candle(
        self,
        forming_candle: Optional[Candle],
        on_signal: SignalCallback,
    ) -> None:
        """
        Перевіряє поточну формуючу свічку.

        Вона НЕ передається в:
          - Supertrend
          - CandleCounter

        Вона використовується тільки для SignalQueue,
        яка вирішує, чи підтвердився сигнал.
        """

        if forming_candle is None:
            return

        if not self.signal_queue.has_pending(self.instrument):
            return

        event = self.signal_queue.check_confirmation(
            instrument=self.instrument,
            forming_candle=forming_candle,
        )

        if event is None:
            return

        logger.info(
            "%s: 🚨 ПІДТВЕРДЖЕНО %s",
            self.instrument,
            event.type.value,
        )

        await on_signal(event)

    # --------------------------------------------------------
    # Повна обробка реального Feed
    # --------------------------------------------------------

    async def process_live(
        self,
        feed,
        on_signal: SignalCallback,
        payout: float,
    ) -> None:
        """
        Один цикл аналізу для Pocket Option.

        1. Беремо останню закриту свічку.
        2. Якщо вона нова — обробляємо її.
        3. Беремо формуючу свічку.
        4. Перевіряємо pending confirmation.
        """

        # ----------------------------------------------------
        # 1. ЗАКРИТА свічка
        # ----------------------------------------------------

        closed_candle = await feed.get_latest_closed_candle(
            instrument=self.instrument,
            timeframe_seconds=self.timeframe_seconds,
        )

        if closed_candle is not None:

            await self.process_closed_candle(
                candle=closed_candle,
                payout=payout,
                on_signal=on_signal,
            )

        # ----------------------------------------------------
        # 2. ФОРМУЮЧА свічка
        # ----------------------------------------------------

        forming_candle = await feed.get_current_forming_candle(
            instrument=self.instrument,
            timeframe_seconds=self.timeframe_seconds,
        )

        await self.check_forming_candle(
            forming_candle=forming_candle,
            on_signal=on_signal,
        )

    # --------------------------------------------------------
    # Повна обробка симулятора
    # --------------------------------------------------------

    async def process_simulated(
        self,
        feed,
        on_signal: SignalCallback,
        payout: float = 100.0,
    ) -> None:
        """
        Обробка для SimulatedDataFeed.

        Симулятор повертає свічки як послідовність закритих свічок,
        тому вони одразу передаються в process_closed_candle().
        """

        candle = await feed.get_latest_candle(
            instrument=self.instrument,
            timeframe_seconds=self.timeframe_seconds,
        )

        if candle is None:
            return

        await self.process_closed_candle(
            candle=candle,
            payout=payout,
            on_signal=on_signal,
        )


# ============================================================
# Реальний Pocket Option
# ============================================================

async def run_with_live_feed(
    engine: InstrumentEngine,
    feed,
    on_signal: SignalCallback,
) -> None:
    """
    Нескінченний цикл аналізу одного інструменту
    через реальний Pocket Option Feed.

    Кожен InstrumentEngine працює незалежно.
    main.py запускає кілька таких корутин через asyncio.gather().
    """

    logger.info(
        "%s: запущено live-аналіз | timeframe=%s сек",
        engine.instrument,
        engine.timeframe_seconds,
    )

    while True:
        try:
            payout = feed.get_payout(engine.instrument)

            await engine.process_live(
                feed=feed,
                on_signal=on_signal,
                payout=payout,
            )

        except asyncio.CancelledError:
            logger.info(
                "%s: live-цикл скасовано.",
                engine.instrument,
            )
            raise

        except Exception:
            logger.exception(
                "%s: помилка live-циклу.",
                engine.instrument,
            )

        # ----------------------------------------------------
        # Не потрібно опитувати API сотні разів за секунду.
        # 1 секунда достатня для confirmation.
        # ----------------------------------------------------

        await asyncio.sleep(1)


# ============================================================
# Симулятор
# ============================================================

async def run_with_feed(
    engine: InstrumentEngine,
    feed,
    on_signal: SignalCallback,
) -> None:
    """
    Нескінченний цикл для SimulatedDataFeed.
    """

    logger.info(
        "%s: запущено simulation-аналіз | timeframe=%s сек",
        engine.instrument,
        engine.timeframe_seconds,
    )

    while True:
        try:
            payout = 100.0

            await engine.process_simulated(
                feed=feed,
                on_signal=on_signal,
                payout=payout,
            )

        except asyncio.CancelledError:
            logger.info(
                "%s: simulation-цикл скасовано.",
                engine.instrument,
            )
            raise

        except Exception:
            logger.exception(
                "%s: помилка simulation-циклу.",
                engine.instrument,
            )

        await asyncio.sleep(1)
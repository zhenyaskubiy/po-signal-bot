"""
Об'єднує Supertrend, підрахунок антитрендових свічок і чергу сигналів
в один робочий цикл для ОДНОГО інструменту.

Логіка прийняття рішень (process_closed_candle / process_confirmation)
навмисно відокремлена від реального часу (asyncio) — це дозволяє тестувати
її напряму, підставляючи свічки вручну, без очікування реальних секунд.
Асинхронна частина (run_with_feed) — це вже "жива" обгортка, яка тягне
дані з джерела (симулятора чи, пізніше, реального Pocket Option) в
реальному часі.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from core.candle import Candle
from core.candle_counter import CandleCounter
from core.signal_queue import SignalEvent, SignalQueue
from core.supertrend import SupertrendCalculator

logger = logging.getLogger(__name__)

OnSignal = Callable[[SignalEvent], Awaitable[None]]


class InstrumentEngine:
    """Веде повний цикл прийняття рішень для одного інструменту."""

    def __init__(
        self,
        instrument: str,
        signal_queue: SignalQueue,
        supertrend_atr_period: int,
        supertrend_multiplier: float,
        timeframe_seconds: int,
        min_payout_percent: float,
    ):
        self.instrument = instrument
        self.signal_queue = signal_queue
        self.timeframe_seconds = timeframe_seconds
        self.min_payout_percent = min_payout_percent

        self.supertrend = SupertrendCalculator(atr_period=supertrend_atr_period, multiplier=supertrend_multiplier)
        self.candle_counter = CandleCounter()
        self._prev_count = 0

    def process_closed_candle(self, candle: Candle, payout: float, now: Optional[float] = None) -> Optional[SignalEvent]:
        """
        Обробляє щойно закриту свічку. Повертає попередження (🟡), якщо
        серія антитрендових свічок щойно (саме на цій свічці) досягла 4.

        now — необов'язковий unix-час (для тестів на симульованому часі);
        за замовчуванням береться реальний поточний час.
        """
        st_result = self.supertrend.update(candle)
        state = self.candle_counter.update(candle, st_result.direction, st_result.changed)

        warning = None
        just_reached_four = state.active and state.count == 4 and self._prev_count != 4
        if just_reached_four:
            if payout >= self.min_payout_percent:
                warning = self.signal_queue.on_series_reached_four(
                    instrument=self.instrument,
                    locked_color=state.locked_color,
                    payout=payout,
                    timeframe_seconds=self.timeframe_seconds,
                    now=now,
                )
            else:
                logger.info("%s: виплата %.1f%% нижче мінімальної — сигнал пропущено", self.instrument, payout)

        self._prev_count = state.count if state.active else 0
        return warning

    def process_confirmation(self, forming_candle: Candle, now: Optional[float] = None) -> Optional[SignalEvent]:
        """Перевіряє 5-ту (ще не закриту) свічку — повертає основний сигнал або None."""
        return self.signal_queue.check_confirmation(self.instrument, forming_candle, now=now)


async def run_with_feed(
    engine: InstrumentEngine,
    feed,  # data.simulator.SimulatedDataFeed або майбутній реальний фід
    on_signal: OnSignal,
) -> None:
    """
    "Жива" обгортка навколо InstrumentEngine: тягне дані з feed у реальному
    часі, тікає ціну, закриває свічки по таймфрейму, і в потрібний момент
    запускає перевірку підтвердження — все паралельно, не блокуючи інші
    інструменти чи Telegram-бота.
    """
    while True:
        for _ in range(engine.timeframe_seconds):
            feed.tick(engine.instrument)
            await asyncio.sleep(1)

        candle = feed.close_candle(engine.instrument)
        payout = feed.get_payout(engine.instrument)
        warning = engine.process_closed_candle(candle, payout)

        if warning:
            await on_signal(warning)
            asyncio.create_task(_confirm_later(engine, feed, on_signal))


async def _confirm_later(engine: InstrumentEngine, feed, on_signal: OnSignal) -> None:
    delay = engine.signal_queue.confirmation_delay_seconds
    await asyncio.sleep(delay)
    forming = feed.current_forming_candle(engine.instrument)
    result = engine.process_confirmation(forming)
    if result:
        await on_signal(result)
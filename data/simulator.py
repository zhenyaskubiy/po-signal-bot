"""
Симулятор ринкових даних — для прогону всієї логіки бота (Supertrend →
підрахунок свічок → сигнали → Telegram) end-to-end, без підключення до
реального Pocket Option.

Це НЕ спроба реалістично змоделювати ринок — просто випадкове блукання
ціни, достатнє, щоб перевірити, що всі частини бота працюють разом.
"""

from __future__ import annotations

import random
import time
from typing import Dict, List

from core.candle import Candle


class SimulatedDataFeed:
    def __init__(
        self,
        instruments: List[str],
        base_price: float = 100.0,
        volatility: float = 0.3,
        seed: int | None = None,
    ):
        self._rng = random.Random(seed)
        self.volatility = volatility

        self._price: Dict[str, float] = {i: base_price for i in instruments}
        self._open: Dict[str, float] = dict(self._price)
        self._high: Dict[str, float] = dict(self._price)
        self._low: Dict[str, float] = dict(self._price)
        self._payout: Dict[str, float] = {i: round(self._rng.uniform(85, 96), 1) for i in instruments}

    def get_payout(self, instrument: str) -> float:
        return self._payout[instrument]

    def tick(self, instrument: str) -> None:
        """Один випадковий крок ціни всередині свічки, що зараз формується."""
        step = self._rng.gauss(0, self.volatility)
        self._price[instrument] += step
        self._high[instrument] = max(self._high[instrument], self._price[instrument])
        self._low[instrument] = min(self._low[instrument], self._price[instrument])

    def current_forming_candle(self, instrument: str) -> Candle:
        """Стан свічки, яка ЗАРАЗ формується (ще не закрита)."""
        return Candle(
            open=self._open[instrument],
            high=self._high[instrument],
            low=self._low[instrument],
            close=self._price[instrument],
            timestamp=time.time(),
        )

    def close_candle(self, instrument: str) -> Candle:
        """Закриває поточну свічку і одразу відкриває наступну."""
        closed = self.current_forming_candle(instrument)
        self._open[instrument] = closed.close
        self._high[instrument] = closed.close
        self._low[instrument] = closed.close
        return closed
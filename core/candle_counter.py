from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from core.candle import Candle


class BodySize(Enum):
    DOJI = "doji"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass
class CandleCounterConfig:
    """Пороги класифікації розміру тіла відносно середнього за останні N свічок."""

    candles_for_average: int = 20
    doji_ratio: float = 0.1     # тіло < 10% середнього → доджі
    small_ratio: float = 0.5    # тіло < 50% середнього → маленька
    large_ratio: float = 1.5    # тіло > 150% середнього → велика


@dataclass
class SeriesState:
    """Стан поточної серії антитрендових свічок для одного інструменту."""

    active: bool = False
    count: int = 0
    locked_color: Optional[str] = None  # "bullish" або "bearish" — колір, зафіксований на старті серії


class CandleCounter:
    """
    Веде підрахунок безперервної антитрендової серії свічка за свічкою для ОДНОГО інструменту.
    """

    def __init__(self, config: Optional[CandleCounterConfig] = None):
        self.config = config or CandleCounterConfig()
        self._recent_bodies: List[float] = []
        self._state = SeriesState()

    # ---------- допоміжні методи ----------

    def _classify_body(self, candle: Candle) -> BodySize:
        if not self._recent_bodies:
            return BodySize.MEDIUM  # ще немає історії — вважаємо середньою

        avg_body = sum(self._recent_bodies) / len(self._recent_bodies)
        if avg_body == 0:
            return BodySize.MEDIUM

        ratio = candle.body_size / avg_body
        if ratio < self.config.doji_ratio:
            return BodySize.DOJI
        if ratio < self.config.small_ratio:
            return BodySize.SMALL
        if ratio > self.config.large_ratio:
            return BodySize.LARGE
        return BodySize.MEDIUM

    def _remember_body(self, candle: Candle) -> None:
        self._recent_bodies.append(candle.body_size)
        if len(self._recent_bodies) > self.config.candles_for_average:
            self._recent_bodies.pop(0)

    def _color_for_direction(self, supertrend_direction: str) -> str:
        """Який колір вважається антитрендовим при даному напрямку Supertrend."""
        # Якщо тренд вниз (SELL), антитрендом є зелені свічки (bullish)
        # Якщо тренд вгору (BUY), антитрендом є червоні свічки (bearish)
        if supertrend_direction.upper() == "SELL":
            return "bullish"
        return "bearish"

    def _matches_color(self, candle: Candle, color: str) -> bool:
        return candle.is_bearish if color == "bearish" else candle.is_bullish

    def _reset(self) -> None:
        self._state = SeriesState()

    # ---------- головний метод ----------

    def update(self, candle: Candle, supertrend_direction: str, supertrend_changed: bool) -> SeriesState:
        # ЗАХИСТ: Якщо напрямок Supertrend змінився в процесі активної серії — одразу скидаємо її, 
        # щоб не торгувати за застарілим трендом!
        if supertrend_changed and self._state.active:
            self._reset()

        if self._state.active:
            anti_trend_color = self._state.locked_color
        else:
            anti_trend_color = self._color_for_direction(supertrend_direction)

        is_anti_trend = self._matches_color(candle, anti_trend_color)

        if is_anti_trend:
            body_class = self._classify_body(candle)

            if not self._state.active:
                if body_class in (BodySize.MEDIUM, BodySize.LARGE):
                    self._state = SeriesState(active=True, count=1, locked_color=anti_trend_color)
            else:
                self._state.count += 1
        else:
            if self._state.active:
                self._reset()

        self._remember_body(candle)
        return self._state

    @property
    def state(self) -> SeriesState:
        return self._state
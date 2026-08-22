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
        return "bearish" if supertrend_direction == "BUY" else "bullish"

    def _matches_color(self, candle: Candle, color: str) -> bool:
        return candle.is_bearish if color == "bearish" else candle.is_bullish

    def _reset(self) -> None:
        self._state = SeriesState()

    # ---------- головний метод ----------

    def update(self, candle: Candle, supertrend_direction: str, supertrend_changed: bool) -> SeriesState:
        """
        Додає нову свічку і повертає поточний стан серії.

        supertrend_direction — поточний напрямок Supertrend ("BUY"/"SELL").
        supertrend_changed — True, якщо напрямок Supertrend змінився саме на цій свічці.
        """
        if supertrend_changed and self._state.active and self._state.count < 2:
            # Зміна відбулась зарано (до 2 підрахованих свічок) — серія недійсна
            self._reset()

        if self._state.active:
            # Серія вже йде — колір антитрендової свічки "заблокований" з моменту старту
            anti_trend_color = self._state.locked_color
        else:
            # Серія ще не почалась — колір визначається поточним напрямком Supertrend
            anti_trend_color = self._color_for_direction(supertrend_direction)

        is_anti_trend = self._matches_color(candle, anti_trend_color)

        if is_anti_trend:
            body_class = self._classify_body(candle)

            if not self._state.active:
                # Старт серії: перша свічка має обов'язково бути середньою або великою
                if body_class in (BodySize.MEDIUM, BodySize.LARGE):
                    self._state = SeriesState(active=True, count=1, locked_color=anti_trend_color)
                # маленька/доджі до старту — ігнорується, серія не починається
            else:
                # Продовження активної серії (свічка того ж заблокованого кольору)
                self._state.count += 1
        else:
            # Якщо серія вже активна, але прийшла свічка НЕ антитрендового кольору (переривання),
            # або якщо серія не активна, але прийшла протилежна свічка — обробляємо розрив.
            if self._state.active:
                # Побажання клієнта: якщо ланцюжок перервався свічкою іншого кольору — скидаємо серію
                self._reset()

        self._remember_body(candle)
        return self._state

    @property
    def state(self) -> SeriesState:
        return self._state
"""
Визначення антитрендових свічок і підрахунок їх серії (п.5-7 ТЗ).

Правила:
- Якщо Supertrend = BUY, антитрендові свічки — червоні (ведмежі).
- Якщо Supertrend = SELL, антитрендові свічки — зелені (бичачі).
- Серія починається з ПЕРШОЇ антитрендової свічки із середнім/великим тілом.
  Маленькі й доджі-свічки до цього моменту серію не запускають — вони
  просто ігноруються, доки не з'явиться "якісна" свічка.
- Після старту серії — усі наступні антитрендові свічки рахуються
  незалежно від розміру тіла (навіть маленькі й доджі).
- Зміна напрямку Supertrend допускається, але лише якщо на момент зміни
  вже нараховано мінімум 2 антитрендові свічки. Якщо змінилось раніше —
  серія скидається. Якщо після 2+ — серія продовжується як і раніше,
  колір антитрендової свічки лишається "заблокованим" тим, яким був
  на старті серії (а не перераховується заново під новий напрямок).

Класифікація розміру тіла (доджі/маленька/середня/велика) робиться відносно
ковзного середнього тіла останніх N свічок — ТЗ не задає точних чисел,
це розумні значення за замовчуванням (config/settings.yaml поки що їх не
містить — можна додати туди пізніше, якщо знадобиться підлаштування
після тестів на реальних даних).
"""

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
    Веде підрахунок антитрендової серії свічка за свічкою для ОДНОГО інструменту.
    Для кожного інструменту зі списку в конфігурації створюйте окремий екземпляр.
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
            # Серія вже йде — колір антитрендової свічки "заблокований" з моменту старту,
            # навіть якщо Supertrend після цього змінився (це дозволено п.7 ТЗ).
            anti_trend_color = self._state.locked_color
        else:
            # Серія ще не почалась — колір визначається поточним напрямком Supertrend.
            anti_trend_color = self._color_for_direction(supertrend_direction)

        is_anti_trend = self._matches_color(candle, anti_trend_color)

        if is_anti_trend:
            body_class = self._classify_body(candle)

            if not self._state.active:
                if body_class in (BodySize.MEDIUM, BodySize.LARGE):
                    self._state = SeriesState(active=True, count=1, locked_color=anti_trend_color)
                # маленька/доджі до старту серії — просто ігнорується, серія не починається
            else:
                self._state.count += 1
        # свічка "за трендом" (не антитрендова) — на підрахунок не впливає,
        # серія не скидається (скидання лише через зарану зміну Supertrend, див. вище)

        self._remember_body(candle)
        return self._state

    @property
    def state(self) -> SeriesState:
        return self._state
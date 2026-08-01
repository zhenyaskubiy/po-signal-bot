"""
Розрахунок індикатора Supertrend (ATR + Multiplier).

Supertrend показує напрямок ринку на кожній свічці: "BUY" (тренд вгору)
або "SELL" (тренд вниз). Саме за зміною цього напрямку визначаються
антитрендові свічки (п.5 ТЗ).

Використання:
    from core.candle import Candle
    from core.supertrend import SupertrendCalculator

    calc = SupertrendCalculator(atr_period=10, multiplier=3)
    for candle in candles:          # свічки подаються по порядку: старі → нові
        result = calc.update(candle)
        print(result.direction, result.changed)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.candle import Candle


@dataclass
class SupertrendResult:
    """Результат розрахунку Supertrend для однієї свічки."""

    value: float       # значення лінії Supertrend (підтримка або опір)
    direction: str     # "BUY" (тренд вгору) або "SELL" (тренд вниз)
    changed: bool      # True, якщо напрямок змінився саме на цій свічці


class SupertrendCalculator:
    """
    Рахує Supertrend поступово, свічка за свічкою — так, як це буде
    відбуватись у реальному часі при надходженні нових котирувань.

    Перші (atr_period - 1) свічок дають менш точний ATR (просте середнє,
    поки не назбирається достатньо даних) — це нормально й очікувано
    для будь-якого індикатора на основі ковзного середнього.
    """

    def __init__(self, atr_period: int = 10, multiplier: float = 3.0):
        if atr_period <= 0:
            raise ValueError("atr_period повинен бути додатним числом.")
        if multiplier <= 0:
            raise ValueError("multiplier повинен бути додатним числом.")

        self.atr_period = atr_period
        self.multiplier = multiplier

        self._prev_close: Optional[float] = None
        self._atr: Optional[float] = None
        self._tr_values: List[float] = []  # накопичення для першого простого середнього ATR

        self._prev_support: Optional[float] = None     # "up"-смуга з попередньої свічки
        self._prev_resistance: Optional[float] = None  # "dn"-смуга з попередньої свічки
        self._direction: Optional[str] = None

    def _true_range(self, candle: Candle) -> float:
        if self._prev_close is None:
            return candle.full_range
        return max(
            candle.full_range,
            abs(candle.high - self._prev_close),
            abs(candle.low - self._prev_close),
        )

    def _update_atr(self, tr: float) -> float:
        if self._atr is None:
            self._tr_values.append(tr)
            if len(self._tr_values) < self.atr_period:
                # Ще недостатньо даних для повного періоду — просте середнє того, що є
                return sum(self._tr_values) / len(self._tr_values)
            self._atr = sum(self._tr_values) / len(self._tr_values)
            return self._atr

        # Згладжування Уайлдера — стандарт для ATR
        self._atr = (self._atr * (self.atr_period - 1) + tr) / self.atr_period
        return self._atr

    def update(self, candle: Candle) -> SupertrendResult:
        tr = self._true_range(candle)
        atr = self._update_atr(tr)

        hl2 = (candle.high + candle.low) / 2
        basic_support = hl2 - self.multiplier * atr
        basic_resistance = hl2 + self.multiplier * atr

        if self._prev_support is None:
            # Перша свічка — немає попередніх смуг, ініціалізуємо напряму
            support = basic_support
            resistance = basic_resistance
            direction = "BUY"  # довільна початкова точка відліку
        else:
            # "Липкість" смуг — стандартне правило Supertrend:
            # смуга рухається лише в бік тренду, не "стрибає" назад просто так.
            if self._prev_close > self._prev_support:
                support = max(basic_support, self._prev_support)
            else:
                support = basic_support

            if self._prev_close < self._prev_resistance:
                resistance = min(basic_resistance, self._prev_resistance)
            else:
                resistance = basic_resistance

            if self._direction == "SELL" and candle.close > self._prev_resistance:
                direction = "BUY"
            elif self._direction == "BUY" and candle.close < self._prev_support:
                direction = "SELL"
            else:
                direction = self._direction

        changed = self._direction is not None and direction != self._direction
        value = support if direction == "BUY" else resistance

        # Зберігаємо стан для наступного виклику
        self._prev_support = support
        self._prev_resistance = resistance
        self._direction = direction
        self._prev_close = candle.close

        return SupertrendResult(value=value, direction=direction, changed=changed)
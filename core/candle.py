"""
Проста структура даних для однієї свічки (OHLC).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    timestamp: float  # unix-час закриття свічки

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) не може бути меншим за low ({self.low}).")
        if not (self.low <= self.open <= self.high):
            raise ValueError(f"open ({self.open}) виходить за межі [low, high].")
        if not (self.low <= self.close <= self.high):
            raise ValueError(f"close ({self.close}) виходить за межі [low, high].")

    @property
    def is_bullish(self) -> bool:
        """Зелена (бичача) свічка — закрилась вище, ніж відкрилась."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """Червона (ведмежа) свічка — закрилась нижче, ніж відкрилась."""
        return self.close < self.open

    @property
    def body_size(self) -> float:
        """Розмір тіла свічки (абсолютна різниця open/close)."""
        return abs(self.close - self.open)

    @property
    def full_range(self) -> float:
        """Повний діапазон свічки (high - low), для порівняння розміру тіла."""
        return self.high - self.low
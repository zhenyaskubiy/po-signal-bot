"""
Черга сигналів (п.8, 9, 12 ТЗ).

Коли серія антитрендових свічок (з core/candle_counter.py) досягає 4,
надсилається попередження (🟡). Через налаштований час (10-50 сек — з
конфігурації) перевіряється, чи свічка, яка ЗАРАЗ формується (5-та),
залишається антитрендовою. Якщо так — надсилається основний сигнал
(🟢 CALL / 🔴 PUT). Якщо ні — сигнал просто скасовується, без відправки.

Захист від дублікатів (п.12): по одній ситуації — рівно одне попередження
і рівно одне підтвердження (або мовчазне скасування). Поки ситуація не
розв'язана (confirmed чи invalidated), нове попередження по тому самому
інструменту не створюється.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from core.candle import Candle


class SignalType(Enum):
    WARNING = "warning"
    CALL = "CALL"
    PUT = "PUT"


@dataclass
class SignalEvent:
    type: SignalType
    instrument: str
    payout: float
    timeframe_seconds: int
    expiration_seconds: int
    message: str


@dataclass
class _PendingConfirmation:
    instrument: str
    locked_color: str  # "bearish" → PUT, "bullish" → CALL
    deadline: float  # unix-час, коли перевіряти 5-ту свічку
    payout: float
    timeframe_seconds: int
    expiration_seconds: int
    resolved: bool = False


class SignalQueue:
    """
    Один екземпляр на весь бот — веде чергу одразу для всіх інструментів,
    щоб дедублікація (п.12) керувалась з одного місця.
    """

    def __init__(self, confirmation_delay_seconds: int = 30):
        self.confirmation_delay_seconds = confirmation_delay_seconds
        self._pending: Dict[str, _PendingConfirmation] = {}

    def on_series_reached_four(
        self,
        instrument: str,
        locked_color: str,
        payout: float,
        timeframe_seconds: int,
        expiration_seconds: int,
        now: Optional[float] = None,
    ) -> Optional[SignalEvent]:
        """
        Викликайте, коли серія антитрендових свічок інструменту щойно
        досягла рівно 4 (перехід з 3 у 4 в candle_counter).

        Повертає попередження — рівно один раз на ситуацію. Якщо для цього
        інструменту вже є непідтверджена ситуація в черзі, повертає None
        (захист від дублікатів).
        """
        now = now if now is not None else time.time()

        if instrument in self._pending and not self._pending[instrument].resolved:
            return None

        self._pending[instrument] = _PendingConfirmation(
            instrument=instrument,
            locked_color=locked_color,
            deadline=now + self.confirmation_delay_seconds,
            payout=payout,
            timeframe_seconds=timeframe_seconds,
            expiration_seconds=expiration_seconds,
        )

        direction_label = "PUT (SELL)" if locked_color == "bearish" else "CALL (BUY)"
        message = (
            "🟡 Попередження\n"
            f"Інструмент: {instrument}\n"
            f"Напрямок: {direction_label}\n"
            f"Виплата: {payout}%\n"
            f"Таймфрейм: {timeframe_seconds} сек\n"
            f"Експірація: {expiration_seconds} сек\n"
            "Закрилися 4 антитрендові свічки. Очікуємо підтвердження."
        )
        return SignalEvent(
            type=SignalType.WARNING,
            instrument=instrument,
            payout=payout,
            timeframe_seconds=timeframe_seconds,
            expiration_seconds=expiration_seconds,
            message=message,
        )

    def check_confirmation(
        self, instrument: str, forming_candle: Candle, now: Optional[float] = None
    ) -> Optional[SignalEvent]:
        """
        Викликайте регулярно (наприклад, раз на секунду) для кожного
        інструменту, поки для нього є непідтверджена ситуація в черзі.

        forming_candle — свічка, яка ЗАРАЗ формується (5-та), з поточними,
        ще не фінальними high/low/close на момент виклику.

        Повертає основний сигнал, якщо час настав і 5-та свічка досі
        антитрендова. Повертає None, якщо ще не час, або якщо час настав,
        але свічка вже розвернулась (сигнал мовчки скасовується).
        """
        pending = self._pending.get(instrument)
        if pending is None or pending.resolved:
            return None

        now = now if now is not None else time.time()
        if now < pending.deadline:
            return None  # ще не час перевіряти

        pending.resolved = True  # ситуація закрита незалежно від результату (п.12)

        still_anti_trend = (
            forming_candle.is_bearish if pending.locked_color == "bearish" else forming_candle.is_bullish
        )
        if not still_anti_trend:
            return None  # 5-та свічка розвернулась — сигнал не підтвердився

        signal_type = SignalType.PUT if pending.locked_color == "bearish" else SignalType.CALL
        emoji = "🔴" if signal_type == SignalType.PUT else "🟢"
        message = (
            f"{emoji} {signal_type.value}\n"
            f"Інструмент: {instrument}\n"
            f"Виплата: {pending.payout}%\n"
            f"Таймфрейм: {pending.timeframe_seconds} сек\n"
            f"Експірація: {pending.expiration_seconds} сек"
        )
        return SignalEvent(
            type=signal_type,
            instrument=instrument,
            payout=pending.payout,
            timeframe_seconds=pending.timeframe_seconds,
            expiration_seconds=pending.expiration_seconds,
            message=message,
        )

    def clear(self, instrument: str) -> None:
        """Прибрати ситуацію по інструменту вручну (наприклад, для тестів)."""
        self._pending.pop(instrument, None)

    def has_pending(self, instrument: str) -> bool:
        pending = self._pending.get(instrument)
        return pending is not None and not pending.resolved
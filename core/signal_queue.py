from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from core.candle import Candle


class SignalType(Enum):
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
    deadline: float  # unix-час, коли перевіряти формуючу свічку
    payout: float
    timeframe_seconds: int
    expiration_seconds: int
    required_candles: int
    resolved: bool = False


class SignalQueue:
    """
    Черга сигналів без попереджень: при досягненні серії одразу запускається 
    очікування підтвердження, а фінальний сигнал містить кількість свічок.
    """

    def __init__(self, confirmation_delay_seconds: int = 30):
        self.confirmation_delay_seconds = confirmation_delay_seconds
        self._pending: Dict[str, _PendingConfirmation] = {}

    def on_series_reached(
        self,
        instrument: str,
        locked_color: str,
        payout: float,
        timeframe_seconds: int,
        expiration_seconds: int,
        required_candles: int,
        now: Optional[float] = None,
    ) -> None:
        """
        Викликається, коли серія досягла потрібної кількості. 
        Попередження більше не надсилається (повертає None), лише реєструється очікування.
        """
        now = now if now is not None else time.time()

        if instrument in self._pending and not self._pending[instrument].resolved:
            return

        self._pending[instrument] = _PendingConfirmation(
            instrument=instrument,
            locked_color=locked_color,
            deadline=now + self.confirmation_delay_seconds,
            payout=payout,
            timeframe_seconds=timeframe_seconds,
            expiration_seconds=expiration_seconds,
            required_candles=required_candles,
        )

    def check_confirmation(
        self, instrument: str, forming_candle: Candle, now: Optional[float] = None
    ) -> Optional[SignalEvent]:
        """
        Перевіряє формуючу свічку після закінчення затримки та формує 
        фінальний сигнал із кількістю свічок.
        """
        pending = self._pending.get(instrument)
        if pending is None or pending.resolved:
            return None

        now = now if now is not None else time.time()
        if now < pending.deadline:
            return None  # ще не час перевіряти

        pending.resolved = True  # ситуація закрита

        still_anti_trend = (
            forming_candle.is_bearish if pending.locked_color == "bearish" else forming_candle.is_bullish
        )
        if not still_anti_trend:
            return None  # формуюча свічка розвернулась — сигнал скасовано мовчки

        signal_type = SignalType.PUT if pending.locked_color == "bearish" else SignalType.CALL
        emoji = "🔴" if signal_type == SignalType.PUT else "🟢"
        
        message = (
            f"{emoji} {signal_type.value}\n"
            f"Інструмент: {instrument}\n"
            f"Таймфрейм: {pending.timeframe_seconds} сек\n"
            f"Експірація: {pending.expiration_seconds} сек\n"
            f"Закрилися {pending.required_candles} антитрендові свічки."
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
        """Прибрати ситуацію по інструменту вручну."""
        self._pending.pop(instrument, None)

    def has_pending(self, instrument: str) -> bool:
        pending = self._pending.get(instrument)
        return pending is not None and not pending.resolved
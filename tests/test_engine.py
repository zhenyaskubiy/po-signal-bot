"""
Перевірка InstrumentEngine — повний ланцюжок: свічка → Supertrend →
підрахунок серії → чергу сигналів, без реального очікування секунд
(process_closed_candle / process_confirmation викликаються напряму).
"""

from __future__ import annotations

from core.candle import Candle
from core.engine import InstrumentEngine
from core.signal_queue import SignalQueue, SignalType


def bearish_step(open_price: float, body: float, ts: float) -> Candle:
    """Ведмежа свічка, що продовжує ціну від попередньої (без штучних розривів)."""
    close = open_price - body
    high = open_price + 0.1
    low = close - 0.1
    return Candle(open=open_price, high=high, low=low, close=close, timestamp=ts)


def uptrend_candle(price: float, ts: float) -> Candle:
    """Свічка, що продовжує висхідний тренд (для розгону Supertrend у BUY)."""
    return Candle(open=price - 0.3, high=price + 0.3, low=price - 0.5, close=price, timestamp=ts)


def test_full_pipeline_produces_warning_and_signal() -> None:
    signal_queue = SignalQueue(confirmation_delay_seconds=30)
    engine = InstrumentEngine(
        instrument="EURUSD_OTC",
        signal_queue=signal_queue,
        supertrend_atr_period=5,
        supertrend_multiplier=2,
        timeframe_seconds=60,
        min_payout_percent=89,
    )

    ts = 0.0
    warnings = []

    # Розганяємо чіткий висхідний тренд, щоб Supertrend впевнено став BUY
    price = 100.0
    for _ in range(15):
        price += 1.0
        result = engine.process_closed_candle(uptrend_candle(price, ts), payout=90, now=ts)
        ts += 60
        if result:
            warnings.append(result)

    assert not warnings, "На чистому висхідному тренді попереджень бути не повинно"
    print("✅ На чистому тренді (без антитрендових свічок) сигналів немає")

    # Тепер антитрендові (червоні) свічки, що продовжують ціну від попередньої:
    # маленька, доджі, середня→1, маленька→2, маленька→3, велика→4
    bodies = [0.1, 0.02, 0.5, 0.15, 0.15, 0.6]
    p = price
    for body in bodies:
        candle = bearish_step(p, body, ts)
        p = candle.close
        result = engine.process_closed_candle(candle, payout=90, now=ts)
        ts += 60
        if result:
            warnings.append(result)

    assert len(warnings) == 1, f"Очікували рівно одне попередження, отримали {len(warnings)}"
    assert warnings[0].type == SignalType.WARNING
    print(f"✅ Попередження надіслано рівно один раз: {warnings[0].message.splitlines()[0]}")

    # 5-та свічка (яка формується) досі червона, перевіряємо через 30 сек (симульований час)
    forming = bearish_step(p, 0.3, ts)
    confirmation = engine.process_confirmation(forming, now=ts + 30)

    assert confirmation is not None
    assert confirmation.type == SignalType.PUT
    print(f"✅ Основний сигнал підтверджено: {confirmation.type.value}")


def test_low_payout_blocks_signal() -> None:
    signal_queue = SignalQueue(confirmation_delay_seconds=30)
    engine = InstrumentEngine(
        instrument="LOWPAYOUT_OTC",
        signal_queue=signal_queue,
        supertrend_atr_period=5,
        supertrend_multiplier=2,
        timeframe_seconds=60,
        min_payout_percent=89,
    )

    ts = 0.0
    price = 100.0
    for _ in range(15):
        price += 1.0
        engine.process_closed_candle(uptrend_candle(price, ts), payout=70)  # виплата нижче мінімальної
        ts += 60

    bodies = [0.5, 0.15, 0.15, 0.6]
    warnings = []
    p = price
    for body in bodies:
        candle = bearish_step(p, body, ts)
        p = candle.close
        result = engine.process_closed_candle(candle, payout=70)
        ts += 60
        if result:
            warnings.append(result)

    assert not warnings, "При виплаті нижче мінімальної сигнал не повинен надсилатись"
    print("✅ Інструмент з низькою виплатою коректно відфільтровано (п.10 ТЗ)")


if __name__ == "__main__":
    test_full_pipeline_produces_warning_and_signal()
    test_low_payout_blocks_signal()
    print("\nВсі перевірки повного циклу InstrumentEngine пройдені успішно.")
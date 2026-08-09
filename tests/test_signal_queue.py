"""
Перевірка черги сигналів: попередження, підтвердження, скасування,
захист від дублікатів (п.12 ТЗ).

"""

from __future__ import annotations

from core.candle import Candle
from core.signal_queue import SignalQueue, SignalType


def make_candle(is_bearish: bool, ts: float) -> Candle:
    if is_bearish:
        return Candle(open=100.0, high=100.5, low=98.0, close=99.0, timestamp=ts)
    return Candle(open=99.0, high=101.0, low=98.5, close=100.5, timestamp=ts)


def test_warning_sent_once() -> None:
    queue = SignalQueue(confirmation_delay_seconds=30)

    warning = queue.on_series_reached_four(
        instrument="EURUSD_OTC", locked_color="bearish", payout=89, timeframe_seconds=60,
        expiration_seconds=60, now=1000.0
    )
    assert warning is not None
    assert warning.type == SignalType.WARNING
    print("✅ Перше попередження надіслано")

    # Другий виклик по тому самому інструменту, доки ситуація не розв'язана — має дати None
    duplicate = queue.on_series_reached_four(
        instrument="EURUSD_OTC", locked_color="bearish", payout=89, timeframe_seconds=60,
        expiration_seconds=60, now=1005.0
    )
    assert duplicate is None
    print("✅ Дублікат попередження заблоковано (п.12)")


def test_confirmation_before_deadline_returns_none() -> None:
    queue = SignalQueue(confirmation_delay_seconds=30)
    queue.on_series_reached_four("EURUSD_OTC", "bearish", 89, 60, expiration_seconds=60, now=1000.0)

    result = queue.check_confirmation("EURUSD_OTC", make_candle(is_bearish=True, ts=1010.0), now=1010.0)
    assert result is None
    print("✅ До настання часу перевірки — сигнал не надсилається")


def test_confirmation_success_gives_put() -> None:
    queue = SignalQueue(confirmation_delay_seconds=30)
    queue.on_series_reached_four("EURUSD_OTC", "bearish", 89, 60, expiration_seconds=60, now=1000.0)

    # Час підтвердження настав (1000 + 30 = 1030), 5-та свічка досі червона
    result = queue.check_confirmation("EURUSD_OTC", make_candle(is_bearish=True, ts=1030.0), now=1030.0)
    assert result is not None
    assert result.type == SignalType.PUT
    print(f"✅ Підтверджено сигнал: {result.type.value}")

    # Повторний виклик — ситуація вже розв'язана, більше сигналів не буде
    again = queue.check_confirmation("EURUSD_OTC", make_candle(is_bearish=True, ts=1031.0), now=1031.0)
    assert again is None
    print("✅ Повторний виклик після підтвердження нічого не дає (немає дублікату)")


def test_confirmation_reversed_cancels_silently() -> None:
    queue = SignalQueue(confirmation_delay_seconds=30)
    queue.on_series_reached_four("EURUSD_OTC", "bearish", 89, 60, expiration_seconds=60, now=1000.0)

    # 5-та свічка розвернулась (стала зеленою, хоча очікували червону)
    result = queue.check_confirmation("EURUSD_OTC", make_candle(is_bearish=False, ts=1030.0), now=1030.0)
    assert result is None
    print("✅ Розворот 5-ї свічки → сигнал скасовано без відправки")

    # Ситуація вважається розв'язаною — новий цикл можна почати
    assert queue.has_pending("EURUSD_OTC") is False
    print("✅ Після скасування ситуація звільнена — новий сигнал по цьому інструменту можливий")


def test_new_warning_after_resolution() -> None:
    queue = SignalQueue(confirmation_delay_seconds=30)
    queue.on_series_reached_four("EURUSD_OTC", "bearish", 89, 60, expiration_seconds=60, now=1000.0)
    queue.check_confirmation("EURUSD_OTC", make_candle(is_bearish=True, ts=1030.0), now=1030.0)

    # Нова серія сформувалась пізніше — має дозволити нове попередження
    new_warning = queue.on_series_reached_four("EURUSD_OTC", "bearish", 91, 60, expiration_seconds=60, now=2000.0)
    assert new_warning is not None
    print("✅ Після завершення попередньої ситуації нове попередження дозволене")


def test_independent_instruments() -> None:
    queue = SignalQueue(confirmation_delay_seconds=30)
    w1 = queue.on_series_reached_four("EURUSD_OTC", "bearish", 89, 60, expiration_seconds=60, now=1000.0)
    w2 = queue.on_series_reached_four("GBPUSD_OTC", "bullish", 90, 60, expiration_seconds=60, now=1000.0)
    assert w1 is not None and w2 is not None
    print("✅ Різні інструменти обробляються незалежно один від одного")


if __name__ == "__main__":
    test_warning_sent_once()
    test_confirmation_before_deadline_returns_none()
    test_confirmation_success_gives_put()
    test_confirmation_reversed_cancels_silently()
    test_new_warning_after_resolution()
    test_independent_instruments()
    print("\nВсі перевірки черги сигналів пройдені успішно.")
"""
Перевірка логіки підрахунку антитрендових свічок — точно за прикладом із ТЗ:

❌ маленька
❌ доджі
✅ середня → №1
✅ маленька → №2
✅ маленька → №3
✅ велика → №4

Плюс перевірка правила про зміну Supertrend (п.7):
- зміна ДО 2 підрахованих свічок → серія скидається;
- зміна ПІСЛЯ 2+ підрахованих свічок → серія продовжується.

Запуск:
    python -m tests.test_candle_counter
"""

from __future__ import annotations

from core.candle import Candle
from core.candle_counter import CandleCounter


def bearish_candle(body: float, ts: float) -> Candle:
    """Червона (ведмежа) свічка із заданим розміром тіла."""
    high = 100.0
    low = 100.0 - max(body, 0.01) - 1.0  # трохи більший range, ніж тіло
    open_ = 100.0
    close = open_ - body
    return Candle(open=open_, high=high, low=low, close=close, timestamp=ts)


def test_series_start_example() -> None:
    """Точно відтворює приклад із ТЗ."""
    counter = CandleCounter()

    # Розганяємо "середнє" тіло на кількох попередніх свічках (~2.0),
    # щоб класифікація маленька/середня/велика мала з чим порівнювати.
    for i in range(5):
        counter.update(bearish_candle(body=2.0, ts=float(i)), supertrend_direction="BUY", supertrend_changed=False)

    # Скидаємо стан серії (лишаємо історію тіл) — почнемо приклад "з чистого аркуша"
    counter._state = counter._state.__class__()

    steps = [
        (0.1, "маленька", False),   # ❌ не запускає серію
        (0.05, "доджі", False),     # ❌ не запускає серію
        (2.0, "середня → №1", True),
        (0.1, "маленька → №2", True),
        (0.1, "маленька → №3", True),
        (5.0, "велика → №4", True),
    ]

    ts = 100.0
    for body, label, should_be_anti_trend in steps:
        state_before = counter.state.count
        result = counter.update(bearish_candle(body=body, ts=ts), supertrend_direction="BUY", supertrend_changed=False)
        ts += 1
        counted = result.count > state_before or (not counter.state.active and result.active)
        status = "✅" if should_be_anti_trend else "❌"
        print(f"{status} {label}: active={result.active}, count={result.count}")

    assert counter.state.active is True
    assert counter.state.count == 4, f"Очікували count=4, отримали {counter.state.count}"
    print("\n✅ Приклад із ТЗ відтворено точно: серія сформована, count=4")


def test_supertrend_change_before_two_resets() -> None:
    """Зміна Supertrend ДО 2 підрахованих свічок повинна скинути серію."""
    counter = CandleCounter()

    for i in range(5):
        counter.update(bearish_candle(body=2.0, ts=float(i)), supertrend_direction="BUY", supertrend_changed=False)
    counter._state = counter._state.__class__()

    counter.update(bearish_candle(body=2.0, ts=100.0), supertrend_direction="BUY", supertrend_changed=False)
    assert counter.state.count == 1

    # Зміна Supertrend на цьому кроці — до 2 підрахованих свічок
    result = counter.update(bearish_candle(body=2.0, ts=101.0), supertrend_direction="SELL", supertrend_changed=True)

    assert result.active is False, "Серія мала скинутись через зарану зміну Supertrend"
    print("✅ Зміна Supertrend до 2 свічок → серія коректно скинута")


def test_supertrend_change_after_two_continues() -> None:
    """Зміна Supertrend ПІСЛЯ 2+ підрахованих свічок не повинна скидати серію."""
    counter = CandleCounter()

    for i in range(5):
        counter.update(bearish_candle(body=2.0, ts=float(i)), supertrend_direction="BUY", supertrend_changed=False)
    counter._state = counter._state.__class__()

    counter.update(bearish_candle(body=2.0, ts=100.0), supertrend_direction="BUY", supertrend_changed=False)
    counter.update(bearish_candle(body=2.0, ts=101.0), supertrend_direction="BUY", supertrend_changed=False)
    assert counter.state.count == 2

    # Зміна Supertrend після 2 підрахованих свічок — серія продовжується,
    # колір антитрендової свічки лишається "заблокований" (bearish/червона)
    result = counter.update(bearish_candle(body=2.0, ts=102.0), supertrend_direction="SELL", supertrend_changed=True)

    assert result.active is True, "Серія не мала скинутись — зміна відбулась після 2+ свічок"
    assert result.count == 3
    print("✅ Зміна Supertrend після 2+ свічок → серія коректно продовжена")


if __name__ == "__main__":
    test_series_start_example()
    test_supertrend_change_before_two_resets()
    test_supertrend_change_after_two_continues()
    print("\nВсі перевірки підрахунку антитрендових свічок пройдені успішно.")
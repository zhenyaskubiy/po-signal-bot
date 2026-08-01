"""
Перевірка Supertrend на простих синтетичних даних:
- чіткий висхідний тренд повинен дати напрямок BUY;
- чіткий низхідний тренд повинен дати напрямок SELL;
- при зміні тренду напрямок Supertrend теж має змінитись (changed=True).

Запуск:
    python -m tests.test_supertrend
"""

from __future__ import annotations

from core.candle import Candle
from core.supertrend import SupertrendCalculator


def make_candle(price: float, spread: float, ts: float) -> Candle:
    """Створює просту свічку навколо ціни price з невеликим розкидом high/low."""
    return Candle(
        open=price,
        high=price + spread,
        low=price - spread,
        close=price,
        timestamp=ts,
    )


def run_uptrend_then_downtrend() -> None:
    calc = SupertrendCalculator(atr_period=5, multiplier=2)

    prices = list(range(100, 130))          # чіткий висхідний тренд: 100 → 129
    prices += list(range(129, 90, -1))       # потім чіткий низхідний тренд: 129 → 91

    results = []
    for i, price in enumerate(prices):
        candle = make_candle(price=float(price), spread=0.5, ts=float(i))
        result = calc.update(candle)
        results.append(result)

    # Перевірка 1: наприкінці висхідного тренду напрямок має бути BUY
    last_uptrend_result = results[29]
    assert last_uptrend_result.direction == "BUY", (
        f"Очікували BUY наприкінці висхідного тренду, отримали {last_uptrend_result.direction}"
    )
    print("✅ Висхідний тренд → напрямок BUY")

    # Перевірка 2: десь у низхідній частині напрямок має стати SELL
    downtrend_directions = [r.direction for r in results[30:]]
    assert "SELL" in downtrend_directions, "Очікували, що напрямок зміниться на SELL у низхідному тренді"
    print("✅ Низхідний тренд → напрямок змінився на SELL")

    # Перевірка 3: має бути хоч один момент, коли changed=True (сама зміна напрямку)
    changes = [r for r in results if r.changed]
    assert len(changes) >= 1, "Очікували хоча б одну зміну напрямку (changed=True)"
    print(f"✅ Зафіксовано {len(changes)} зміну(и) напрямку — changed=True спрацював коректно")


if __name__ == "__main__":
    run_uptrend_then_downtrend()
    print("\nВсі перевірки Supertrend пройдені успішно.")
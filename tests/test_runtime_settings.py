"""
Перевірка RuntimeSettingsStore: зміни застосовуються одразу і видно з будь-якого місця.

"""

from __future__ import annotations

from core.runtime_settings import RuntimeSettingsStore


def test_initial_values() -> None:
    store = RuntimeSettingsStore(expiration_seconds=60, required_anti_trend_candles=4)
    current = store.get()
    assert current.expiration_seconds == 60
    assert current.required_anti_trend_candles == 4
    print("✅ Початкові значення застосовані коректно")


def test_change_expiration() -> None:
    store = RuntimeSettingsStore(expiration_seconds=60, required_anti_trend_candles=4)
    store.set_expiration(120)
    assert store.get().expiration_seconds == 120
    print("✅ Зміна часу експірації застосовується одразу")


def test_change_required_candles() -> None:
    store = RuntimeSettingsStore(expiration_seconds=60, required_anti_trend_candles=4)
    store.set_required_candles(6)
    assert store.get().required_anti_trend_candles == 6
    print("✅ Зміна кількості свічок застосовується одразу")


def test_get_returns_independent_copy() -> None:
    """get() не повинен повертати об'єкт, зміна якого поза класом ламає внутрішній стан."""
    store = RuntimeSettingsStore(expiration_seconds=60, required_anti_trend_candles=4)
    snapshot = store.get()
    snapshot.expiration_seconds = 999  # змінюємо копію, а не оригінал

    assert store.get().expiration_seconds == 60, "Зовнішня зміна копії не повинна впливати на сховище"
    print("✅ get() повертає незалежну копію — випадково зламати стан ззовні неможливо")


if __name__ == "__main__":
    test_initial_values()
    test_change_expiration()
    test_change_required_candles()
    test_get_returns_independent_copy()
    print("\nВсі перевірки RuntimeSettingsStore пройдені успішно.")
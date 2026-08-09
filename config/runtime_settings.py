"""
Налаштування, які можна змінювати "на льоту" через кнопки в Telegram,
без перезапуску бота і без редагування config/settings.yaml.

Це ОКРЕМО від config/settings.yaml: там — початкові значення при старті
бота, тут — поточні "живі" значення, які може міняти будь-хто з правом
доступу до бота командою /settings. Один спільний екземпляр на весь бот.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace


@dataclass
class RuntimeSettings:
    expiration_seconds: int
    required_anti_trend_candles: int


class RuntimeSettingsStore:
    """Потокобезпечне сховище — спільне для всіх інструментів одночасно."""

    def __init__(self, expiration_seconds: int, required_anti_trend_candles: int):
        self._lock = threading.Lock()
        self._settings = RuntimeSettings(
            expiration_seconds=expiration_seconds,
            required_anti_trend_candles=required_anti_trend_candles,
        )

    def get(self) -> RuntimeSettings:
        with self._lock:
            return replace(self._settings)

    def set_expiration(self, seconds: int) -> None:
        with self._lock:
            self._settings.expiration_seconds = seconds

    def set_required_candles(self, count: int) -> None:
        with self._lock:
            self._settings.required_anti_trend_candles = count
"""
Завантаження та перевірка конфігурації з settings.yaml.

Використання:
    from config.loader import load_config
    cfg = load_config()
    print(cfg.timeframe_seconds)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

import yaml


DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "settings.yaml")


@dataclass
class SupertrendConfig:
    atr_period: int
    multiplier: float


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/bot.log"


@dataclass
class BotConfig:
    timeframe_seconds: int
    expiration_seconds: int
    required_anti_trend_candles: int
    supertrend: SupertrendConfig
    min_payout_percent: float
    confirmation_delay_seconds: int
    instruments: List[str]
    telegram: TelegramConfig
    data_source: str
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class ConfigError(Exception):
    """Помилка у файлі конфігурації."""


def load_config(path: str = DEFAULT_CONFIG_PATH) -> BotConfig:
    if not os.path.exists(path):
        raise ConfigError(f"Файл конфігурації не знайдено: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    try:
        supertrend = SupertrendConfig(**raw["supertrend"])
        telegram = TelegramConfig(**raw["telegram"])
        logging_cfg = LoggingConfig(**raw.get("logging", {}))

        instruments = raw["instruments"]
        if not instruments:
            raise ConfigError("Список інструментів (instruments) не може бути порожнім.")

        cfg = BotConfig(
            timeframe_seconds=int(raw["timeframe_seconds"]),
            expiration_seconds=int(raw.get("expiration_seconds", raw["timeframe_seconds"])),
            required_anti_trend_candles=int(raw.get("required_anti_trend_candles", 4)),
            supertrend=supertrend,
            min_payout_percent=float(raw["min_payout_percent"]),
            confirmation_delay_seconds=int(raw["confirmation_delay_seconds"]),
            instruments=list(instruments),
            telegram=telegram,
            data_source=raw.get("data_source", "simulator"),
            logging=logging_cfg,
        )
    except KeyError as e:
        raise ConfigError(f"У конфігурації відсутнє обов'язкове поле: {e}") from e

    _validate(cfg)
    return cfg


def _validate(cfg: BotConfig) -> None:
    if cfg.timeframe_seconds <= 0:
        raise ConfigError("timeframe_seconds повинен бути додатним числом.")
    if cfg.expiration_seconds <= 0:
        raise ConfigError("expiration_seconds повинен бути додатним числом.")
    if cfg.required_anti_trend_candles <= 0:
        raise ConfigError("required_anti_trend_candles повинен бути додатним числом.")
    if cfg.supertrend.atr_period <= 0:
        raise ConfigError("supertrend.atr_period повинен бути додатним числом.")
    if cfg.supertrend.multiplier <= 0:
        raise ConfigError("supertrend.multiplier повинен бути додатним числом.")
    if not (0 <= cfg.min_payout_percent <= 100):
        raise ConfigError("min_payout_percent повинен бути в межах 0-100.")
    if cfg.confirmation_delay_seconds <= 0:
        raise ConfigError("confirmation_delay_seconds повинен бути додатним числом.")
    if cfg.data_source not in ("simulator", "pocket_option"):
        raise ConfigError("data_source повинен бути 'simulator' або 'pocket_option'.")


if __name__ == "__main__":
    config = load_config()
    print("Конфігурація завантажена успішно:")
    print(config)
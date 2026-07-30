from __future__ import annotations

import logging

from config.loader import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    cfg = load_config()
    logger.info("Бот запущений.")
    logger.info("Таймфрейм: %s сек, інструментів у списку: %d", cfg.timeframe_seconds, len(cfg.instruments))
    print("Бот працює. Конфігурація завантажена успішно.")


if __name__ == "__main__":
    main()
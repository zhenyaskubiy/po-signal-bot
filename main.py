from __future__ import annotations

import logging

import requests

from config.loader import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    """Надсилає одне повідомлення в Telegram напряму через API бота."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)

    if response.status_code != 200:
        logger.error("Telegram не прийняв повідомлення: %s", response.text)
    else:
        logger.info("Повідомлення надіслано в Telegram.")


def main() -> None:
    cfg = load_config()
    logger.info("Бот запущений.")
    logger.info("Таймфрейм: %s сек, інструментів у списку: %d", cfg.timeframe_seconds, len(cfg.instruments))
    print("✅ Бот працює. Конфігурація завантажена успішно.")

    send_telegram_message(
        bot_token=cfg.telegram.bot_token,
        chat_id=cfg.telegram.chat_id,
        text="Бот запущений. Конфігурація завантажена успішно.",
    )


if __name__ == "__main__":
    main()
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.loader import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Бот запущений. Конфігурація завантажена успішно.")
    logger.info("Відповів на /start для chat_id=%s", update.effective_chat.id)


def main() -> None:
    cfg = load_config()
    logger.info("Конфігурація завантажена успішно.")

    app = Application.builder().token(cfg.telegram.bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))

    print("Бот запущений і чекає /start у Telegram. Ctrl+C — вихід.")
    app.run_polling()


if __name__ == "__main__":
    main()
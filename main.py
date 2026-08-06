"""
Головна точка входу.

Запускає:
  1. Telegram-бота — реагує на /start підтвердженням, що бот працює;
  2. Цикл аналізу ринку по кожному інструменту зі списку в конфігурації
     (Supertrend → підрахунок антитрендових свічок → черга сигналів),
     поки що на СИМУЛЬОВАНИХ даних (data/simulator.py) — реальне
     підключення до Pocket Option буде окремим наступним кроком.

Сигнали (🟡 попередження і 🟢/🔴 основний сигнал) надсилаються в
Telegram-чат, вказаний у config/settings.yaml (telegram.chat_id).

Запуск:
    python main.py
Зупинка:
    Ctrl+C
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.loader import load_config
from core.engine import InstrumentEngine, run_with_feed
from core.signal_queue import SignalEvent, SignalQueue
from data.simulator import SimulatedDataFeed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("✅ Бот запущений. Конфігурація завантажена успішно.")
    logger.info("Відповів на /start для chat_id=%s", update.effective_chat.id)


async def main() -> None:
    cfg = load_config()
    logger.info("Конфігурація завантажена успішно. Інструментів: %d", len(cfg.instruments))

    app = Application.builder().token(cfg.telegram.bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("Telegram-бот запущено, очікує /start.")

    async def on_signal(event: SignalEvent) -> None:
        try:
            await app.bot.send_message(chat_id=cfg.telegram.chat_id, text=event.message)
            logger.info("Надіслано %s для %s", event.type.value, event.instrument)
        except Exception as e:
            logger.error("Не вдалося надіслати сигнал у Telegram: %s", e)

    feed = SimulatedDataFeed(instruments=cfg.instruments)
    signal_queue = SignalQueue(confirmation_delay_seconds=cfg.confirmation_delay_seconds)

    engines = [
        InstrumentEngine(
            instrument=instrument,
            signal_queue=signal_queue,
            supertrend_atr_period=cfg.supertrend.atr_period,
            supertrend_multiplier=cfg.supertrend.multiplier,
            timeframe_seconds=cfg.timeframe_seconds,
            min_payout_percent=cfg.min_payout_percent,
        )
        for instrument in cfg.instruments
    ]

    print(f"✅ Бот запущений. Аналізую {len(engines)} інструмент(ів) на симульованих даних.")
    print("Напишіть /start у Telegram, щоб перевірити зв'язок. Ctrl+C — вихід.\n")

    try:
        await asyncio.gather(*(run_with_feed(engine, feed, on_signal) for engine in engines))
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот зупинено.")
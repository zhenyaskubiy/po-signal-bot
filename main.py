"""
Головна точка входу.

Запускає:
  1. Telegram-бота — /start підтверджує роботу, /settings відкриває
     кнопки для зміни часу експірації та кількості антитрендових свічок
     "на льоту", без редагування конфігурації чи перезапуску бота;
  2. Цикл аналізу ринку по кожному інструменту (Supertrend → підрахунок
     антитрендових свічок → черга сигналів), поки що на СИМУЛЬОВАНИХ
     даних (data/simulator.py).

Сигнали надсилаються в Telegram-чат, вказаний у config/settings.yaml
(telegram.chat_id).

Запуск:
    python main.py
Зупинка:
    Ctrl+C
"""

from __future__ import annotations

import asyncio
import logging

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.loader import load_config
from core.engine import InstrumentEngine, run_with_feed
from core.runtime_settings import RuntimeSettingsStore
from core.signal_queue import SignalEvent, SignalQueue
from data.simulator import SimulatedDataFeed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Варіанти, які пропонуються кнопками (можна відредагувати під потреби)
EXPIRATION_OPTIONS_SECONDS = [60, 120, 180, 300, 600]  # 1, 2, 3, 5, 10 хвилин
CANDLE_COUNT_OPTIONS = [3, 4, 5, 6, 7, 8]

SETTINGS_BUTTON_LABEL = "⚙️ Налаштування"

# Постійна клавіатура знизу екрана — завжди на видноті, не зникає між повідомленнями
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton(SETTINGS_BUTTON_LABEL)]],
    resize_keyboard=True,  # робить кнопку компактною, а не на весь екран
    is_persistent=True,    # не ховається після натискання
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "✅ Бот запущений. Конфігурація завантажена успішно.",
        reply_markup=MAIN_KEYBOARD,
    )
    logger.info("Відповів на /start для chat_id=%s", update.effective_chat.id)


def _chunk(items: list, size: int) -> list:
    """Розбиває список на групи по size елементів — для акуратних рядків кнопок."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def _settings_keyboard(runtime_settings: RuntimeSettingsStore) -> InlineKeyboardMarkup:
    current = runtime_settings.get()

    expiration_buttons = [
        InlineKeyboardButton(
            f"{'✅ ' if sec == current.expiration_seconds else ''}{sec // 60} хв",
            callback_data=f"exp:{sec}",
        )
        for sec in EXPIRATION_OPTIONS_SECONDS
    ]
    candles_buttons = [
        InlineKeyboardButton(
            f"{'✅ ' if n == current.required_anti_trend_candles else ''}{n} свічок",
            callback_data=f"cnt:{n}",
        )
        for n in CANDLE_COUNT_OPTIONS
    ]

    rows = _chunk(expiration_buttons, 3) + _chunk(candles_buttons, 3)
    return InlineKeyboardMarkup(rows)


def _settings_text(runtime_settings: RuntimeSettingsStore) -> str:
    current = runtime_settings.get()
    return (
        "⚙️ Налаштування бота\n\n"
        f"Час експірації: {current.expiration_seconds // 60} хв\n"
        f"Кількість антитрендових свічок для сигналу: {current.required_anti_trend_candles}\n\n"
        "Оберіть нове значення кнопками нижче:"
    )


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime_settings: RuntimeSettingsStore = context.bot_data["runtime_settings"]
    await update.message.reply_text(
        _settings_text(runtime_settings), reply_markup=_settings_keyboard(runtime_settings)
    )


async def on_settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    runtime_settings: RuntimeSettingsStore = context.bot_data["runtime_settings"]

    kind, value = query.data.split(":")
    if kind == "exp":
        runtime_settings.set_expiration(int(value))
        logger.info("Час експірації змінено на %s сек (chat_id=%s)", value, update.effective_chat.id)
    elif kind == "cnt":
        runtime_settings.set_required_candles(int(value))
        logger.info("Кількість свічок змінено на %s (chat_id=%s)", value, update.effective_chat.id)

    await query.answer("Збережено ✅")
    await query.edit_message_text(
        _settings_text(runtime_settings), reply_markup=_settings_keyboard(runtime_settings)
    )


async def main() -> None:
    cfg = load_config()
    logger.info("Конфігурація завантажена успішно. Інструментів: %d", len(cfg.instruments))

    runtime_settings = RuntimeSettingsStore(
        expiration_seconds=cfg.expiration_seconds,
        required_anti_trend_candles=cfg.required_anti_trend_candles,
    )

    app = Application.builder().token(cfg.telegram.bot_token).build()
    app.bot_data["runtime_settings"] = runtime_settings
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CallbackQueryHandler(on_settings_button))
    # Натискання постійної кнопки знизу екрана надсилає її текст як звичайне
    # повідомлення — цей обробник ловить саме його і відкриває те саме меню.
    app.add_handler(MessageHandler(filters.Text([SETTINGS_BUTTON_LABEL]), cmd_settings))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Список команд, який Telegram показує біля значка "/" у полі вводу
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Перевірити, що бот працює"),
            BotCommand("settings", "Змінити час експірації та кількість свічок"),
        ]
    )
    logger.info("Telegram-бот запущено, очікує /start і /settings.")

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
            runtime_settings=runtime_settings,
        )
        for instrument in cfg.instruments
    ]

    print(f"✅ Бот запущений. Аналізую {len(engines)} інструмент(ів) на симульованих даних.")
    print("У Telegram: /start — перевірка зв'язку, /settings — змінити параметри. Ctrl+C — вихід.\n")

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
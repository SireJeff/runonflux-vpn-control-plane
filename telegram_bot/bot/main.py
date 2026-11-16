import logging
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    PicklePersistence,
)

from bot.config import init_config, get_config
from bot.api.client import get_api

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("An unexpected error occurred.")


async def post_init(application: Application) -> None:
    logger.info("Reseller bot started")


async def post_shutdown(application: Application) -> None:
    await get_api().close()
    logger.info("Reseller bot shut down")


def register_handlers(application: Application) -> None:
    from bot.handlers.start import get_start_handlers
    from bot.handlers.users import get_users_handlers
    from bot.handlers.wallet import get_wallet_handlers
    from bot.handlers.connections import get_connections_handlers
    from bot.handlers.settings import get_settings_handlers
    from bot.handlers.superadmin import get_superadmin_handlers
    from bot.handlers.orders import get_orders_handlers
    from bot.handlers.packages import get_packages_handlers

    application.add_handlers(get_start_handlers())
    application.add_handlers(get_users_handlers())
    application.add_handlers(get_wallet_handlers())
    application.add_handlers(get_connections_handlers())
    application.add_handlers(get_settings_handlers())
    application.add_handlers(get_superadmin_handlers())
    application.add_handlers(get_orders_handlers())
    application.add_handlers(get_packages_handlers())


def main() -> None:
    config = init_config()

    # Set up logging after config is initialized
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.DEBUG if config.DEBUG else logging.INFO,
    )

    persistence = PicklePersistence(filepath="bot_data.pickle")

    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .persistence(persistence)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    register_handlers(application)

    # Add error handler
    application.add_error_handler(error_handler)

    if config.ENVIRONMENT == "production" and config.WEBHOOK_SECRET:
        application.run_webhook(
            listen=config.WEBHOOK_HOST,
            port=config.WEBHOOK_PORT,
            secret_token=config.WEBHOOK_SECRET,
            url_path=config.TELEGRAM_BOT_TOKEN,
            webhook_url=f"https://api.operator7.example.invalid/{config.TELEGRAM_BOT_TOKEN}",
        )
    else:
        application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

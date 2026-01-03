"""Main entry point for Telegram bot."""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import Application, ContextTypes

from config.settings import settings
from database.session import AsyncSessionLocal, close_db, init_db
from handlers import register_handlers
from services.automation import (
    job_admin_daily_report,
    job_cleanup,
    job_expiry_and_traffic_reminders,
    job_payment_reconcile,
)
from services.bootstrap import bootstrap_seed_data
from services.migrations import run_migrations
from services.usage_sync import job_sync_usage


async def post_init(application: Application) -> None:
    """Initialize database on bot startup."""
    logger.info("Initializing database...")
    try:
        # Ensure schema is up-to-date before ORM touches new columns
        await run_migrations()
    except Exception as e:
        logger.error(f"Migrations failed: {e}", exc_info=e)
    await init_db()
    logger.info("Database initialized")
    try:
        await bootstrap_seed_data()
    except Exception as e:
        logger.error(f"Bootstrap seed failed: {e}", exc_info=e)

    if settings.usage_sync_enabled and application.job_queue is not None:
        application.job_queue.run_repeating(
            job_sync_usage,
            interval=settings.usage_sync_interval_seconds,
            first=10,
            name="usage_sync",
        )
        logger.info(
            f"Usage sync enabled: interval={settings.usage_sync_interval_seconds}s batch={settings.usage_sync_batch_size}"
        )

    if settings.automation_enabled and application.job_queue is not None:
        from services.cron_settings import get_cron_interval

        async def _get_interval(job_name: str, default: int) -> int:
            async with AsyncSessionLocal() as db:
                return await get_cron_interval(db, job_name=job_name, default_seconds=default)

        reminders_interval = await _get_interval("reminders", 600)
        cleanup_interval = await _get_interval("cleanup", 3600)
        report_interval = await _get_interval("admin_daily_report", 86400)

        application.job_queue.run_repeating(
            job_expiry_and_traffic_reminders,
            interval=reminders_interval,
            first=30,
            name="reminders",
        )
        logger.info(f"Automation reminders enabled (interval={reminders_interval}s)")
        application.job_queue.run_repeating(
            job_cleanup,
            interval=cleanup_interval,
            first=120,
            name="cleanup",
        )
        application.job_queue.run_repeating(
            job_admin_daily_report,
            interval=report_interval,
            first=180,
            name="admin_daily_report",
        )
        if settings.payment_reconcile_enabled:
            application.job_queue.run_repeating(
                job_payment_reconcile,
                interval=settings.payment_reconcile_interval_seconds,
                first=60,
                name="payment_reconcile",
            )
            logger.info("Payment reconcile enabled")
    logger.info("Bot ready!")


async def post_shutdown(application: Application) -> None:
    """Cleanup on bot shutdown."""
    logger.info("Shutting down bot...")
    await close_db()
    logger.info("Bot shutdown complete")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)


def main() -> None:
    """Main function to run the bot."""
    # Configure logging
    logger.add(
        settings.log_file,
        rotation="100 MB",
        retention="10 days",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
    )

    # Create application
    application = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register handlers
    register_handlers(application)

    # Register error handler
    application.add_error_handler(error_handler)

    # Run bot
    logger.info("Bot starting...")
    if settings.webhook_url:
        logger.info(f"Using webhook: {settings.webhook_url}")
        application.run_webhook(
            listen=settings.web_panel_host,
            port=settings.webhook_port,
            webhook_url=settings.webhook_url,
        )
    else:
        logger.info("Using polling mode")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()


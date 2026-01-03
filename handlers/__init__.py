"""Bot handlers package."""

from telegram.ext import Application

from .commands import register_command_handlers
from .callbacks import register_callback_handlers
from .messages import register_message_handlers
from .admin_handlers import register_admin_handlers


def register_handlers(application: Application) -> None:
    """Register all bot handlers."""
    register_command_handlers(application)
    register_callback_handlers(application)
    register_message_handlers(application)
    register_admin_handlers(application)


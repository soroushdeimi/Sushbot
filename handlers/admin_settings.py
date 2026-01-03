"""
Admin Settings Handler - Generic UI for managing dynamic config.

Features:
- Category-based navigation
- Bool toggle on click
- Input prompts for other types
- Search by key/description
- Reset to defaults
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from database.models.app_setting import AppSetting, SettingCategory
from database.session import get_db
from services.config_manager import config
from utils.admin_check import require_admin


# Conversation states
WAITING_VALUE = 1


def get_category_keyboard() -> InlineKeyboardMarkup:
    """Build category selection keyboard."""
    buttons = []
    for cat in SettingCategory:
        buttons.append([
            InlineKeyboardButton(cat.value, callback_data=f"cfg_cat_{cat.name}")
        ])
    buttons.append([
        InlineKeyboardButton("🔍 Search", callback_data="cfg_search"),
        InlineKeyboardButton("🔙 Back", callback_data="admin"),
    ])
    return InlineKeyboardMarkup(buttons)


def get_settings_keyboard(
    settings: list[AppSetting],
    category: str,
) -> InlineKeyboardMarkup:
    """Build settings list keyboard for a category."""
    buttons = []
    
    for s in sorted(settings, key=lambda x: x.key):
        # For bools, show toggle state
        if s.setting_type == "bool":
            emoji = s.emoji
            label = f"{emoji} {s.key.split('.')[-1]}"
        else:
            label = f"📝 {s.key.split('.')[-1]}: {s.display_value[:20]}"
        
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"cfg_edit_{s.key}")
        ])
    
    buttons.append([
        InlineKeyboardButton("🔙 Categories", callback_data="cfg_main"),
    ])
    
    return InlineKeyboardMarkup(buttons)


def get_setting_detail_keyboard(setting: AppSetting) -> InlineKeyboardMarkup:
    """Build detail view keyboard for a setting."""
    buttons = []
    
    if setting.setting_type == "bool":
        current = "ON" if setting.get_typed_value() else "OFF"
        buttons.append([
            InlineKeyboardButton(
                f"🔄 Toggle (currently {current})",
                callback_data=f"cfg_toggle_{setting.key}",
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton("✏️ Edit Value", callback_data=f"cfg_input_{setting.key}")
        ])
    
    if setting.default_value:
        buttons.append([
            InlineKeyboardButton(
                f"↩️ Reset to default ({setting.default_value[:15]})",
                callback_data=f"cfg_reset_{setting.key}",
            )
        ])
    
    buttons.append([
        InlineKeyboardButton("🔙 Back", callback_data=f"cfg_cat_{setting.category.upper()}"),
    ])
    
    return InlineKeyboardMarkup(buttons)


@require_admin
async def settings_main_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Entry point: /settings or cfg_main callback."""
    text = (
        "⚙️ **Dynamic Settings**\n\n"
        "Select a category to view/edit settings.\n"
        "Changes apply instantly (no restart needed)."
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=get_category_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=get_category_keyboard(),
            parse_mode="Markdown",
        )


@require_admin
async def settings_category_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    category: str,
) -> None:
    """Show settings in a category."""
    query = update.callback_query
    
    async for db in get_db():
        settings = await config.get_category(category.lower(), db=db)
        
        if not settings:
            await query.answer("No settings in this category")
            return
        
        # Find category display name
        cat_display = category
        for cat in SettingCategory:
            if cat.name == category:
                cat_display = cat.value
                break
        
        text = f"{cat_display}\n\n"
        for s in sorted(settings, key=lambda x: x.key):
            text += f"• `{s.key}`: {s.display_value}\n"
        
        await query.edit_message_text(
            text,
            reply_markup=get_settings_keyboard(settings, category),
            parse_mode="Markdown",
        )


@require_admin
async def settings_edit_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
) -> None:
    """Show setting detail view."""
    query = update.callback_query
    
    async for db in get_db():
        setting = await db.get(AppSetting, key)
        
        if not setting:
            await query.answer("Setting not found")
            return
        
        text = (
            f"**{setting.key}**\n\n"
            f"📝 Value: `{setting.display_value}`\n"
            f"📋 Type: {setting.setting_type}\n"
            f"📁 Category: {setting.category}\n"
        )
        
        if setting.description:
            text += f"\n💡 {setting.description}"
        
        if setting.default_value:
            text += f"\n🔄 Default: `{setting.default_value}`"
        
        await query.edit_message_text(
            text,
            reply_markup=get_setting_detail_keyboard(setting),
            parse_mode="Markdown",
        )


@require_admin
async def settings_toggle_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
) -> None:
    """Toggle a boolean setting."""
    query = update.callback_query
    user_id = query.from_user.id
    
    async for db in get_db():
        new_value = await config.toggle(key, updated_by=user_id, db=db)
        
        if new_value is None:
            await query.answer("Cannot toggle this setting")
            return
        
        status = "ON ✅" if new_value else "OFF ❌"
        await query.answer(f"{key.split('.')[-1]} is now {status}")
        
        # Refresh the view
        await settings_edit_handler(update, context, key)


@require_admin
async def settings_input_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
) -> int:
    """Start input flow for non-bool settings."""
    query = update.callback_query
    
    async for db in get_db():
        setting = await db.get(AppSetting, key)
        
        if not setting:
            await query.answer("Setting not found")
            return ConversationHandler.END
        
        # Store key for the input handler
        context.user_data["editing_setting_key"] = key
        
        hint = ""
        if setting.setting_type == "int":
            hint = "Enter a number"
        elif setting.setting_type == "float":
            hint = "Enter a decimal number"
        elif setting.setting_type == "json":
            hint = "Enter valid JSON (e.g., [\"a\", \"b\"])"
        elif setting.setting_type == "list":
            hint = "Enter comma-separated values"
        else:
            hint = "Enter new value"
        
        text = (
            f"✏️ **Editing: {key}**\n\n"
            f"Current: `{setting.display_value}`\n\n"
            f"{hint}\n\n"
            f"Send /cancel to abort."
        )
        
        await query.edit_message_text(text, parse_mode="Markdown")
        return WAITING_VALUE


@require_admin
async def settings_value_received(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Handle user input for setting value."""
    key = context.user_data.get("editing_setting_key")
    if not key:
        await update.message.reply_text("No setting being edited. Use /settings")
        return ConversationHandler.END
    
    new_value = update.message.text.strip()
    user_id = update.from_user.id
    
    async for db in get_db():
        setting = await db.get(AppSetting, key)
        
        if not setting:
            await update.message.reply_text("Setting not found")
            return ConversationHandler.END
        
        # Validate
        is_valid, error = setting.validate(new_value)
        if not is_valid:
            await update.message.reply_text(f"❌ Invalid value: {error}")
            return WAITING_VALUE
        
        # Save
        success = await config.set(key, new_value, updated_by=user_id, db=db)
        
        if success:
            await update.message.reply_text(
                f"✅ Updated `{key}` = `{new_value}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Settings", callback_data="cfg_main")
                ]]),
            )
        else:
            await update.message.reply_text("❌ Failed to save")
        
        context.user_data.pop("editing_setting_key", None)
        return ConversationHandler.END


@require_admin
async def settings_reset_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
) -> None:
    """Reset setting to default."""
    query = update.callback_query
    user_id = query.from_user.id
    
    async for db in get_db():
        success = await config.reset_to_default(key, updated_by=user_id, db=db)
        
        if success:
            await query.answer(f"Reset to default ✅")
        else:
            await query.answer("No default value")
        
        await settings_edit_handler(update, context, key)


@require_admin
async def settings_search_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Start search flow."""
    query = update.callback_query
    
    await query.edit_message_text(
        "🔍 **Search Settings**\n\n"
        "Send a search term (key or description).\n"
        "Send /cancel to go back.",
        parse_mode="Markdown",
    )
    
    context.user_data["settings_searching"] = True
    return WAITING_VALUE


@require_admin
async def settings_search_results(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Show search results."""
    if not context.user_data.get("settings_searching"):
        return await settings_value_received(update, context)
    
    query_text = update.message.text.strip()
    
    async for db in get_db():
        results = await config.search(query_text, db=db)
        
        if not results:
            await update.message.reply_text(
                f"No settings matching '{query_text}'",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Settings", callback_data="cfg_main")
                ]]),
            )
        else:
            text = f"🔍 Results for '{query_text}':\n\n"
            for s in results[:10]:
                text += f"• `{s.key}`: {s.display_value}\n"
            
            await update.message.reply_text(
                text,
                reply_markup=get_settings_keyboard(results[:10], "search"),
                parse_mode="Markdown",
            )
        
        context.user_data.pop("settings_searching", None)
        return ConversationHandler.END


async def settings_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Cancel settings editing."""
    context.user_data.pop("editing_setting_key", None)
    context.user_data.pop("settings_searching", None)
    
    await update.message.reply_text(
        "Cancelled.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Settings", callback_data="cfg_main")
        ]]),
    )
    return ConversationHandler.END


async def settings_callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int | None:
    """Route settings callbacks."""
    query = update.callback_query
    data = query.data
    
    if not data.startswith("cfg_"):
        return None
    
    await query.answer()
    
    if data == "cfg_main":
        await settings_main_handler(update, context)
    
    elif data.startswith("cfg_cat_"):
        category = data.removeprefix("cfg_cat_")
        await settings_category_handler(update, context, category)
    
    elif data.startswith("cfg_edit_"):
        key = data.removeprefix("cfg_edit_")
        await settings_edit_handler(update, context, key)
    
    elif data.startswith("cfg_toggle_"):
        key = data.removeprefix("cfg_toggle_")
        await settings_toggle_handler(update, context, key)
    
    elif data.startswith("cfg_input_"):
        key = data.removeprefix("cfg_input_")
        return await settings_input_handler(update, context, key)
    
    elif data.startswith("cfg_reset_"):
        key = data.removeprefix("cfg_reset_")
        await settings_reset_handler(update, context, key)
    
    elif data == "cfg_search":
        return await settings_search_handler(update, context)
    
    return None

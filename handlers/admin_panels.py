"""Admin panel management handlers."""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.admin_keyboards import (
    admin_main_keyboard,
    admin_panel_detail_keyboard,
    admin_panels_list_keyboard,
)
from database.models import Panel, PanelStatus
from database.session import get_db
from integrations.exceptions import PanelError
from integrations.factory import PanelFactory


async def admin_panels_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """List all panels with pagination."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        res = await db.execute(select(Panel).where(Panel.deleted_at.is_(None)).order_by(Panel.id.desc()))
        panels = list(res.scalars().all())

        if not panels:
            await query.edit_message_text(
                "📭 هیچ پنلی ثبت نشده است.\n\nاز منوی ادمین می‌توانید پنل جدید اضافه کنید.",
                reply_markup=admin_main_keyboard(),
            )
            return

        text = f"🖥️ مدیریت پنل‌ها\n\nتعداد کل: {len(panels)}\n\n"
        await query.edit_message_text(text, reply_markup=admin_panels_list_keyboard(panels, page=page))


async def admin_panel_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, panel_id: int) -> None:
    """Show panel details and actions."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        panel = await db.get(Panel, panel_id)
        if not panel:
            await query.edit_message_text("❌ پنل پیدا نشد.", reply_markup=admin_main_keyboard())
            return

        # Build panel info text
        text = (
            f"🖥️ پنل: {panel.name}\n\n"
            f"📍 وضعیت: {panel.status.value}\n"
            f"🌐 URL: {panel.api_url}\n"
            f"🆔 Node ID: {panel.node_id}\n"
            f"📊 تعداد کانفیگ: {panel.current_config_count}"
        )

        if panel.max_configs_per_panel:
            text += f" / {panel.max_configs_per_panel}"
        if panel.location:
            text += f"\n📍 موقعیت: {panel.location}"
        if panel.notes:
            text += f"\n📝 یادداشت: {panel.notes[:100]}"

        await query.edit_message_text(text, reply_markup=admin_panel_detail_keyboard(panel_id))


async def admin_panel_test_connection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, panel_id: int) -> None:
    """Test panel connection."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        panel = await db.get(Panel, panel_id)
        if not panel:
            await query.edit_message_text("❌ پنل پیدا نشد.")
            return

        await query.edit_message_text("⏳ در حال تست اتصال...")

        panel_service = None
        try:
            panel_service = await PanelFactory.create_panel(panel)
            is_healthy = await panel_service.health_check()

            if is_healthy:
                # Get system stats if available
                try:
                    stats = await panel_service.get_system_stats()
                    text = (
                        f"✅ اتصال موفق!\n\n"
                        f"📊 آمار پنل:\n"
                        f"👥 کل کاربران: {stats.total_users}\n"
                        f"✅ کاربران فعال: {stats.active_users}"
                    )
                    if stats.version:
                        text += f"\n🔢 نسخه: {stats.version}"
                    if stats.memory_total:
                        text += f"\n💾 حافظه: {stats.memory_used // (1024**3)}GB / {stats.memory_total // (1024**3)}GB"
                except Exception as e:
                    logger.warning(f"Could not get system stats: {e}")
                    text = "✅ اتصال موفق!"
            else:
                text = "❌ اتصال ناموفق. پنل در دسترس نیست."
                panel.status = PanelStatus.ERROR
                await db.commit()
        except PanelError as e:
            text = f"❌ خطا: {e.message}"
            panel.status = PanelStatus.ERROR
            await db.commit()
        except Exception as e:
            logger.error(f"Panel connection test failed: {e}", exc_info=True)
            text = f"❌ خطا در تست اتصال: {str(e)[:200]}"
            panel.status = PanelStatus.ERROR
            await db.commit()
        finally:
            if panel_service:
                await panel_service.close()

        await query.edit_message_text(text, reply_markup=admin_panel_detail_keyboard(panel_id))


async def admin_panel_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start adding a new panel."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin
        from services.state_machine import set_step

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        text = (
            "➕ افزودن پنل جدید\n\n"
            "لطفاً اطلاعات پنل را به ترتیب ارسال کنید:\n\n"
            "1️⃣ نام پنل\n"
            "2️⃣ نوع پنل (pasarguard/marzban)\n"
            "3️⃣ URL پنل\n"
            "4️⃣ API Key یا Username:Password\n"
            "5️⃣ Node ID (برای PasarGuard)\n\n"
            "برای لغو /cancel را ارسال کنید."
        )

        await set_step(user.id, step="admin.add_panel.name")
        await query.edit_message_text(text)


async def admin_panel_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, panel_id: int) -> None:
    """Delete a panel (soft delete)."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        panel = await db.get(Panel, panel_id)
        if not panel:
            await query.edit_message_text("❌ پنل پیدا نشد.")
            return

        # Soft delete
        panel.deleted_at = datetime.utcnow()
        panel.status = PanelStatus.INACTIVE
        await db.commit()

        await query.edit_message_text(
            f"✅ پنل '{panel.name}' حذف شد.",
            reply_markup=admin_main_keyboard(),
        )


async def admin_panel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, panel_id: int) -> None:
    """Show panel statistics."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        panel = await db.get(Panel, panel_id)
        if not panel:
            await query.edit_message_text("❌ پنل پیدا نشد.")
            return

        await query.edit_message_text("⏳ در حال دریافت آمار...")

        panel_service = None
        try:
            panel_service = await PanelFactory.create_panel(panel)
            stats = await panel_service.get_system_stats()

            text = (
                f"📊 آمار پنل: {panel.name}\n\n"
                f"👥 کل کاربران: {stats.total_users:,}\n"
                f"✅ کاربران فعال: {stats.active_users:,}\n"
            )

            if stats.version:
                text += f"🔢 نسخه: {stats.version}\n"

            if stats.memory_total:
                mem_used_gb = stats.memory_used // (1024**3) if stats.memory_used else 0
                mem_total_gb = stats.memory_total // (1024**3)
                text += f"💾 حافظه: {mem_used_gb}GB / {mem_total_gb}GB\n"

            if stats.bandwidth_total:
                bw_total_gb = stats.bandwidth_total // (1024**3)
                text += f"📡 پهنای باند کل: {bw_total_gb}GB\n"

            if stats.bandwidth_incoming and stats.bandwidth_outgoing:
                bw_in_gb = stats.bandwidth_incoming // (1024**3)
                bw_out_gb = stats.bandwidth_outgoing // (1024**3)
                text += f"⬇️ ورودی: {bw_in_gb}GB | ⬆️ خروجی: {bw_out_gb}GB"

        except Exception as e:
            logger.error(f"Failed to get panel stats: {e}", exc_info=True)
            text = f"❌ خطا در دریافت آمار: {str(e)[:200]}"
        finally:
            if panel_service:
                await panel_service.close()

        await query.edit_message_text(text, reply_markup=admin_panel_detail_keyboard(panel_id))


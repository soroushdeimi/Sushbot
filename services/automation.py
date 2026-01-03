"""Background automation jobs (reminders, reconciliation)."""

from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import and_, func, or_, select
from telegram.ext import ContextTypes

from config.settings import settings
from database.models import Admin, Payment, PaymentGateway, PaymentStatus, Purchase, PurchaseStatus, Service, ServiceStatus, User
from database.models.purchase import PurchaseType
from database.session import AsyncSessionLocal
from integrations.payments.nowpayments import NowPaymentsGateway


async def job_expiry_and_traffic_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.automation_enabled:
        return

    now = datetime.utcnow()

    async with AsyncSessionLocal() as db:
        if settings.expiry_reminder_enabled:
            threshold = now + timedelta(hours=settings.expiry_reminder_threshold_hours)
            res = await db.execute(
                select(Service).where(
                    Service.status == ServiceStatus.ACTIVE,
                    Service.expiry_date.is_not(None),
                    Service.expiry_date <= threshold,
                    or_(
                        Service.last_expiry_notified_at.is_(None),
                        Service.last_expiry_notified_at < (now - timedelta(hours=24)),
                    ),
                )
            )
            expiring = list(res.scalars().all())
            for svc in expiring:
                try:
                    days = svc.days_remaining or 0
                    await context.bot.send_message(
                        chat_id=svc.user_id,
                        text=f"⏳ یادآوری: سرویس شما #{svc.id} تا {days} روز دیگر منقضی می‌شود. برای تمدید وارد سرویس شوید.",
                    )
                    svc.last_expiry_notified_at = now
                except Exception as e:
                    logger.warning(f"Failed expiry reminder svc_id={svc.id}: {e}")

        if settings.low_traffic_reminder_enabled:
            res = await db.execute(
                select(Service).where(
                    Service.status == ServiceStatus.ACTIVE,
                    Service.is_unlimited.is_(False),
                    Service.remaining_traffic_gb.is_not(None),
                    Service.remaining_traffic_gb <= float(settings.low_traffic_threshold_gb),
                    or_(
                        Service.last_traffic_notified_at.is_(None),
                        Service.last_traffic_notified_at < (now - timedelta(hours=24)),
                    ),
                )
            )
            low = list(res.scalars().all())
            for svc in low:
                try:
                    await context.bot.send_message(
                        chat_id=svc.user_id,
                        text=f"📉 هشدار: حجم سرویس شما #{svc.id} کم شده ({svc.remaining_traffic_gb:.2f}GB). برای خرید حجم وارد سرویس شوید.",
                    )
                    svc.last_traffic_notified_at = now
                except Exception as e:
                    logger.warning(f"Failed traffic reminder svc_id={svc.id}: {e}")

        await db.commit()


async def job_payment_reconcile(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reconcile processing payments for online gateways (best-effort)."""
    if not (settings.automation_enabled and settings.payment_reconcile_enabled):
        return
    if not settings.nowpayments_api_key:
        return

    np = NowPaymentsGateway()
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Payment).where(
                Payment.gateway == PaymentGateway.NOWPAYMENTS,
                Payment.status == PaymentStatus.PROCESSING,
                Payment.gateway_transaction_id.is_not(None),
            ).limit(50)
        )
        pays = list(res.scalars().all())
        for pay in pays:
            try:
                was_processing = pay.status == PaymentStatus.PROCESSING
                r = await np.verify_payment(str(pay.gateway_transaction_id))
                st = str(r.get("payment_status") or "").lower()
                if st in {"finished", "confirmed", "paid"}:
                    pay.status = PaymentStatus.COMPLETED
                    pay.paid_at = now
                elif st in {"failed", "expired", "refunded"}:
                    pay.status = PaymentStatus.FAILED
                pay.gateway_response = str(r)

                # If completed, also complete/fulfill purchase (idempotent)
                if was_processing and pay.status == PaymentStatus.COMPLETED:
                    from database.models import Purchase, PurchaseStatus
                    from services.fulfillment import fulfill_purchase
                    from services.affiliate import award_referral_commission_for_purchase

                    purchase = await db.get(Purchase, int(pay.purchase_id))
                    if purchase and purchase.status != PurchaseStatus.COMPLETED:
                        purchase.status = PurchaseStatus.COMPLETED
                        purchase.completed_at = purchase.completed_at or now
                        await db.commit()
                        try:
                            svc = await fulfill_purchase(db, purchase=purchase)
                            await award_referral_commission_for_purchase(db, purchase=purchase)
                            if svc and getattr(svc, "config_link", None):
                                await context.bot.send_message(chat_id=purchase.user_id, text=f"✅ پرداخت شما تایید شد.\n\n🔗 {svc.config_link}")
                            else:
                                # wallet top-up or non-service purchase
                                await context.bot.send_message(
                                    chat_id=purchase.user_id,
                                    text=f"✅ پرداخت شما تایید شد.\n\n💰 کیف پول شما به مبلغ {int(purchase.final_amount):,} تومان شارژ شد.",
                                )
                        except Exception as e:
                            logger.warning(f"Reconcile fulfill failed purchase_id={purchase.id}: {e}")
            except Exception as e:
                logger.warning(f"Reconcile failed payment_id={pay.id}: {e}")
        await db.commit()


async def job_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cleanup stale pending objects (best-effort)."""
    if not settings.automation_enabled:
        return
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=24)
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Purchase).where(Purchase.status == PurchaseStatus.PENDING, Purchase.created_at < cutoff).limit(200)
        )
        stale = list(res.scalars().all())
        for p in stale:
            p.status = PurchaseStatus.CANCELLED
            p.cancelled_at = now
        if stale:
            await db.commit()


async def job_admin_daily_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Daily admin report (best-effort)."""
    if not settings.automation_enabled:
        return
    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Admin).where(Admin.is_active.is_(True)))
        admins = list(res.scalars().all())
        if not admins:
            return

        res = await db.execute(select(func.count(User.id)).where(User.created_at >= since))
        new_users = int(res.scalar() or 0)
        res = await db.execute(select(func.count(Service.id)).where(Service.status == ServiceStatus.ACTIVE))
        active_services = int(res.scalar() or 0)
        res = await db.execute(
            select(func.count(Purchase.id)).where(Purchase.status == PurchaseStatus.COMPLETED, Purchase.completed_at >= since)
        )
        completed_purchases = int(res.scalar() or 0)
        res = await db.execute(
            select(func.coalesce(func.sum(Purchase.final_amount), 0)).where(
                Purchase.status == PurchaseStatus.COMPLETED, Purchase.completed_at >= since
            )
        )
        revenue = int(res.scalar() or 0)
        res = await db.execute(select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PROCESSING))
        processing_payments = int(res.scalar() or 0)
        res = await db.execute(
            select(func.count(Purchase.id)).where(
                Purchase.purchase_type == PurchaseType.WALLET_TOPUP,
                Purchase.status == PurchaseStatus.COMPLETED,
                Purchase.completed_at >= since,
            )
        )
        topups = int(res.scalar() or 0)

        txt = (
            "📊 Daily Report (last 24h)\n\n"
            f"👤 New users: {new_users}\n"
            f"📦 Active services: {active_services}\n"
            f"🧾 Completed purchases: {completed_purchases}\n"
            f"💰 Revenue: {revenue:,} Toman\n"
            f"💳 Processing payments: {processing_payments}\n"
            f"💰 Wallet top-ups: {topups}\n"
        )
        for a in admins:
            try:
                await context.bot.send_message(chat_id=a.user_id, text=txt)
            except Exception as e:
                logger.warning(f"Failed to send report to admin {a.user_id}: {e}")



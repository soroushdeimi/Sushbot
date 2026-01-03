"""Payment routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from config.settings import settings
from database.models import Payment, PaymentGateway, PaymentStatus, Purchase, PurchaseStatus
from database.session import AsyncSessionLocal
from integrations.payments.aqayepardakht import AqayepardakhtGateway
from integrations.payments.nowpayments import NowPaymentsGateway

router = APIRouter()


@router.post("/webhook/nowpayments")
async def nowpayments_webhook(
    request: Request,
    x_nowpayments_sig: str | None = Header(default=None),
) -> dict:
    """NowPayments IPN webhook (idempotent)."""
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    ipn_secret = settings.nowpayments_ipn_secret
    if not x_nowpayments_sig:
        raise HTTPException(status_code=400, detail="missing signature")

    # Allow DB runtime override for secrets
    async with AsyncSessionLocal() as db:
        if not ipn_secret:
            try:
                from services.runtime_settings import get_setting

                ipn_secret = await get_setting(db, "nowpayments_ipn_secret")
            except Exception:
                ipn_secret = None

    if not ipn_secret:
        raise HTTPException(status_code=403, detail="ipn secret not configured")

    gw = NowPaymentsGateway(ipn_secret=ipn_secret)
    if not gw.verify_webhook_raw(raw_body=raw, signature=x_nowpayments_sig):
        raise HTTPException(status_code=403, detail="bad signature")

    order_id = payload.get("order_id")
    payment_id = payload.get("payment_id") or payload.get("id")
    payment_status = str(payload.get("payment_status") or "").lower()
    if not order_id:
        raise HTTPException(status_code=400, detail="missing order_id")

    async with AsyncSessionLocal() as db:
        purchase = await db.get(Purchase, int(order_id))
        if not purchase:
            raise HTTPException(status_code=404, detail="purchase not found")

        existing: Payment | None = None
        if payment_id:
            res = await db.execute(
                select(Payment).where(
                    Payment.gateway == PaymentGateway.NOWPAYMENTS,
                    Payment.gateway_transaction_id == str(payment_id),
                )
            )
            existing = res.scalars().first()

        completed_now = False
        if payment_status in {"finished", "confirmed", "paid"}:
            from datetime import datetime

            purchase.status = PurchaseStatus.COMPLETED
            purchase.completed_at = purchase.completed_at or datetime.utcnow()
            completed_now = True
            if existing:
                existing.status = PaymentStatus.COMPLETED
                existing.gateway_response = raw.decode("utf-8", errors="ignore")
            else:
                db.add(
                    Payment(
                        purchase_id=purchase.id,
                        gateway=PaymentGateway.NOWPAYMENTS,
                        status=PaymentStatus.COMPLETED,
                        amount=int(purchase.final_amount),
                        currency="IRR",
                        gateway_transaction_id=str(payment_id) if payment_id else None,
                        gateway_response=raw.decode("utf-8", errors="ignore"),
                    )
                )
        elif payment_status in {"failed", "expired", "refunded"}:
            purchase.status = PurchaseStatus.FAILED
            if existing:
                existing.status = PaymentStatus.FAILED
                existing.gateway_response = raw.decode("utf-8", errors="ignore")
            else:
                db.add(
                    Payment(
                        purchase_id=purchase.id,
                        gateway=PaymentGateway.NOWPAYMENTS,
                        status=PaymentStatus.FAILED,
                        amount=int(purchase.final_amount),
                        currency="IRR",
                        gateway_transaction_id=str(payment_id) if payment_id else None,
                        gateway_response=raw.decode("utf-8", errors="ignore"),
                    )
                )
        else:
            if existing:
                existing.status = PaymentStatus.PROCESSING
                existing.gateway_response = raw.decode("utf-8", errors="ignore")
            else:
                db.add(
                    Payment(
                        purchase_id=purchase.id,
                        gateway=PaymentGateway.NOWPAYMENTS,
                        status=PaymentStatus.PROCESSING,
                        amount=int(purchase.final_amount),
                        currency="IRR",
                        gateway_transaction_id=str(payment_id) if payment_id else None,
                        gateway_response=raw.decode("utf-8", errors="ignore"),
                    )
                )

        await db.commit()

        if completed_now:
            # Best-effort: fulfill immediately + affiliate commission (both idempotent).
            try:
                from services.affiliate import award_referral_commission_for_purchase
                from services.fulfillment import fulfill_purchase

                await fulfill_purchase(db, purchase=purchase)
                await award_referral_commission_for_purchase(db, purchase=purchase)
            except Exception:
                # keep webhook ack fast and robust
                pass

    return {"status": "ok"}


@router.api_route("/webhook/aqayepardakht", methods=["GET", "POST"])
async def aqayepardakht_webhook(request: Request) -> HTMLResponse:
    """
    Aqayepardakht callback endpoint.
    Provider commonly posts form fields:
      - invoice_id
      - transid
    We'll verify by calling /verify with (pin, amount, transid).
    """
    # Collect params from form, json, and query for robustness
    invoice_id: str | None = None
    transid: str | None = None

    try:
        form = await request.form()
        invoice_id = invoice_id or (form.get("invoice_id") if form else None)
        transid = transid or (form.get("transid") if form else None)
    except Exception:
        pass

    if not invoice_id or not transid:
        try:
            payload = await request.json()
            invoice_id = invoice_id or str(
                payload.get("invoice_id") or payload.get("order_id") or ""
            )
            transid = transid or str(
                payload.get("transid")
                or payload.get("trans_id")
                or payload.get("transaction_id")
                or ""
            )
        except Exception:
            pass

    qp = request.query_params
    invoice_id = invoice_id or qp.get("invoice_id") or qp.get("order_id")
    transid = transid or qp.get("transid") or qp.get("trans_id") or qp.get("transaction_id")

    if not invoice_id or not transid:
        raise HTTPException(status_code=400, detail="missing invoice_id/transid")

    pin = settings.aqayepardakht_api_key

    async with AsyncSessionLocal() as db:
        if not pin:
            try:
                from services.runtime_settings import get_setting

                pin = await get_setting(db, "aqayepardakht_pin")
            except Exception:
                pin = None
        if not pin:
            raise HTTPException(status_code=403, detail="aqayepardakht pin not configured")

        purchase = await db.get(Purchase, int(invoice_id))
        if not purchase:
            raise HTTPException(status_code=404, detail="purchase not found")

        # Verify against provider
        gw = AqayepardakhtGateway(pin=pin)
        ok = False
        try:
            v = await gw.verify_payment(transid=str(transid), amount=int(purchase.final_amount))
            # Provider returns code == 1 on success (per common docs)
            ok = str(v.get("code") or v.get("status") or "") in {"1", "success", "SUCCESS"}
        except Exception:
            ok = False

        # Idempotent payment record
        res = await db.execute(
            select(Payment).where(
                Payment.gateway == PaymentGateway.AQAYEPARDAKHT,
                Payment.purchase_id == purchase.id,
            )
        )
        pay = res.scalars().first()
        if not pay:
            pay = Payment(
                purchase_id=purchase.id,
                gateway=PaymentGateway.AQAYEPARDAKHT,
                status=PaymentStatus.PROCESSING,
                amount=int(purchase.final_amount),
                currency="IRR",
                gateway_transaction_id=str(transid),
            )
            db.add(pay)

        if ok:
            from datetime import datetime

            purchase.status = PurchaseStatus.COMPLETED
            purchase.completed_at = purchase.completed_at or datetime.utcnow()
            pay.status = PaymentStatus.COMPLETED
            pay.paid_at = pay.paid_at or datetime.utcnow()
        else:
            pay.status = PaymentStatus.FAILED
            if purchase.status == PurchaseStatus.PENDING:
                purchase.status = PurchaseStatus.FAILED

        await db.commit()

        if ok:
            # Best-effort fulfillment
            try:
                from services.affiliate import award_referral_commission_for_purchase
                from services.fulfillment import fulfill_purchase

                await fulfill_purchase(db, purchase=purchase)
                await award_referral_commission_for_purchase(db, purchase=purchase)
            except Exception:
                pass

    title = "Payment Successful" if ok else "Payment Failed"
    body = (
        f"<h3>{title}</h3>"
        "<p>You can close this page and return to the bot.</p>"
        f"<p><a href='https://t.me/{settings.bot_username}'>Back to bot</a></p>"
    )
    return HTMLResponse(body)

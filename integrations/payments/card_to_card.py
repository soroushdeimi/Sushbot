"""Card-to-card payment gateway."""

from __future__ import annotations

from typing import Any

from loguru import logger

from utils.security import generate_tracking_code


class CardToCardGateway:
    """Card-to-card payment gateway handler."""

    def __init__(self) -> None:
        """Initialize card-to-card gateway."""

    async def create_payment(
        self,
        amount: int,
        order_id: str,
        callback_url: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a card-to-card payment request."""
        tracking_code = generate_tracking_code()

        # Card-to-card payment requires manual verification
        payment_data = {
            "gateway": "card_to_card",
            "tracking_code": tracking_code,
            "amount": amount,
            "order_id": order_id,
            "status": "pending",
            "message": "Please transfer the amount to the specified card and submit the tracking code.",
        }

        logger.info(f"Card-to-card payment created: {tracking_code} for order {order_id}")
        return payment_data

    async def verify_payment(
        self,
        tracking_code: str,
        card_number: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Verify card-to-card payment (manual verification)."""
        # This would typically integrate with bank APIs or admin verification
        # For now, return pending status - admin must verify manually
        return {
            "status": "pending",
            "tracking_code": tracking_code,
            "message": "Payment verification pending admin approval",
        }

    async def check_status(
        self,
        tracking_code: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Check card-to-card payment status."""
        # Implementation would check database or external service
        return {
            "status": "pending",
            "tracking_code": tracking_code,
        }

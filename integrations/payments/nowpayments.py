"""NowPayments payment gateway integration."""

from __future__ import annotations

import hmac
import hashlib
from typing import Any

import httpx
from loguru import logger

from config.settings import settings


class NowPaymentsGateway:
    """NowPayments payment gateway handler."""

    def __init__(self, api_key: str | None = None, ipn_secret: str | None = None) -> None:
        """Initialize NowPayments gateway."""
        self.api_key = api_key or settings.nowpayments_api_key
        self.ipn_secret = ipn_secret or settings.nowpayments_ipn_secret
        self.base_url = "https://api.nowpayments.io/v1"
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request to NowPayments API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=data,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"NowPayments API error: {e}")
                raise

    async def create_payment(
        self,
        amount: float,
        order_id: str,
        callback_url: str,
        currency: str = "USD",
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a NowPayments payment request."""
        data = {
            "price_amount": amount,
            "price_currency": currency,
            "pay_currency": currency,
            "order_id": order_id,
            "order_description": description or f"Payment for order {order_id}",
            "ipn_callback_url": callback_url,
            "success_url": callback_url,
            "cancel_url": callback_url,
        }
        result = await self._request("POST", "/payment", data=data)
        return result

    async def verify_payment(
        self,
        payment_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Verify NowPayments payment."""
        result = await self._request("GET", f"/payment/{payment_id}")
        return result

    async def check_status(
        self,
        payment_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Check NowPayments payment status."""
        return await self.verify_payment(payment_id)

    def verify_webhook_raw(self, raw_body: bytes, signature: str) -> bool:
        """Verify NowPayments webhook signature against raw request body."""
        expected_signature = hmac.new(
            (self.ipn_secret or "").encode(),
            raw_body,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(signature, expected_signature)


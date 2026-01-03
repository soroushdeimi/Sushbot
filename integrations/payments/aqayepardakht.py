"""Aqayepardakht payment gateway integration.

Implements the public API compatible with the common flow:
- Create: POST https://panel.aqayepardakht.ir/api/v2/create
- Pay:    https://panel.aqayepardakht.ir/startpay/{transid}
- Verify: POST https://panel.aqayepardakht.ir/api/v2/verify
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from config.settings import settings


class AqayepardakhtGateway:
    """Aqayepardakht payment gateway handler."""

    def __init__(self, pin: str | None = None) -> None:
        """Initialize Aqayepardakht gateway."""
        self.pin = pin or settings.aqayepardakht_api_key  # stored as "pin" in provider docs
        self.base_url = "https://panel.aqayepardakht.ir/api/v2"
        self.headers = {"Content-Type": "application/json"}

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request to Aqayepardakht API."""
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
                logger.error(f"Aqayepardakht API error: {e}")
                raise

    async def create_payment(
        self,
        amount: int,
        order_id: str,
        callback_url: str,
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create an Aqayepardakht payment request.

        Returns dict including 'transid' and 'payment_url' on success.
        """
        if not self.pin:
            raise ValueError("Aqayepardakht pin is not configured")
        data = {
            "pin": self.pin,
            "amount": int(amount),
            "callback": callback_url,
            "invoice_id": str(order_id),
        }
        result = await self._request("POST", "/create", data=data)
        # provider returns {status: "success", transid: "..."} on success
        transid = str(result.get("transid") or "")
        if transid:
            result["payment_url"] = f"https://panel.aqayepardakht.ir/startpay/{transid}"
        return result

    async def verify_payment(
        self,
        transid: str,
        amount: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Verify Aqayepardakht payment."""
        if not self.pin:
            raise ValueError("Aqayepardakht pin is not configured")
        data = {"pin": self.pin, "amount": int(amount), "transid": str(transid)}
        return await self._request("POST", "/verify", data=data)

    async def check_status(
        self,
        transid: str,
        amount: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Check Aqayepardakht payment status."""
        return await self.verify_payment(transid=transid, amount=amount)

"""Base payment gateway interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PaymentGatewayBase(ABC):
    """Base class for payment gateways."""

    @abstractmethod
    async def create_payment(
        self,
        amount: int,
        order_id: str,
        callback_url: str,
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a payment request."""
        pass

    @abstractmethod
    async def verify_payment(
        self,
        transaction_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Verify a payment transaction."""
        pass

    @abstractmethod
    async def check_status(
        self,
        transaction_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Check payment status."""
        pass


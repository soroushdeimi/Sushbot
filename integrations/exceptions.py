"""Custom exceptions for VPN panel integrations."""

from __future__ import annotations

from typing import Any


class PanelError(Exception):
    """Base exception for all panel-related errors."""

    def __init__(self, message: str, panel_name: str | None = None, details: dict[str, Any] | None = None) -> None:
        """
        Initialize panel error.

        Args:
            message: Error message
            panel_name: Name of the panel that raised the error
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.panel_name = panel_name
        self.details = details or {}


class PanelConnectionError(PanelError):
    """Raised when connection to panel fails."""

    pass


class PanelAuthenticationError(PanelError):
    """Raised when panel authentication fails."""

    pass


class PanelUserNotFoundError(PanelError):
    """Raised when a requested user is not found on the panel."""

    def __init__(self, username: str, panel_name: str | None = None) -> None:
        """
        Initialize user not found error.

        Args:
            username: Username that was not found
            panel_name: Name of the panel
        """
        super().__init__(f"User '{username}' not found", panel_name=panel_name)
        self.username = username


class PanelOperationError(PanelError):
    """Raised when a panel operation fails."""

    pass


class PanelValidationError(PanelError):
    """Raised when panel data validation fails."""

    pass


class PanelRateLimitError(PanelError):
    """Raised when panel rate limit is exceeded."""

    pass


class PanelTimeoutError(PanelError):
    """Raised when panel operation times out."""

    pass


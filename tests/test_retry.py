"""Tests for utils/retry.py - retry utilities with exponential backoff."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from integrations.exceptions import PanelError
from utils.retry import retry_with_backoff


class TestRetryWithBackoff:
    """Tests for retry_with_backoff decorator."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """Function should return immediately on success."""
        call_count = 0

        @retry_with_backoff(max_retries=3)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self):
        """Function should retry and eventually succeed."""
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        async def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return "success"

        result = await eventually_succeeds()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries_then_raises(self):
        """Function should raise after exhausting retries."""
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Connection failed")

        with pytest.raises(ConnectionError):
            await always_fails()
        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_respects_max_retries(self):
        """Function should respect max_retries setting."""
        call_count = 0

        @retry_with_backoff(max_retries=1, initial_delay=0.01)
        async def fails():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Timeout")

        with pytest.raises(TimeoutError):
            await fails()
        assert call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_panel_error_is_retried(self):
        """PanelError should trigger retry."""
        call_count = 0

        @retry_with_backoff(max_retries=2, initial_delay=0.01)
        async def panel_error_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise PanelError("Panel error")
            return "recovered"

        result = await panel_error_func()
        assert result == "recovered"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        """Non-retryable exceptions should not trigger retry."""
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        async def value_error_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            await value_error_func()
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_custom_retryable_exceptions(self):
        """Custom retryable exceptions should be respected."""
        call_count = 0

        @retry_with_backoff(
            max_retries=2, initial_delay=0.01, retryable_exceptions=(ValueError,)
        )
        async def custom_retry_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Retryable now")
            return "success"

        result = await custom_retry_func()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff_applied(self):
        """Delay should increase exponentially."""

        @retry_with_backoff(
            max_retries=3,
            initial_delay=0.1,
            exponential_base=2.0,
            jitter=False,
            max_delay=10.0,
        )
        async def track_delays():
            raise ConnectionError("Fail")

        with patch("utils.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ConnectionError):
                await track_delays()

            # Check sleep was called with increasing delays
            calls = mock_sleep.call_args_list
            assert len(calls) == 3
            # Delays should be ~0.1, ~0.2, ~0.4 (exponential with base 2)
            assert 0.09 < calls[0][0][0] < 0.11  # ~0.1
            assert 0.19 < calls[1][0][0] < 0.21  # ~0.2
            assert 0.39 < calls[2][0][0] < 0.41  # ~0.4

    @pytest.mark.asyncio
    async def test_max_delay_caps_backoff(self):
        """Delay should not exceed max_delay."""

        @retry_with_backoff(
            max_retries=5,
            initial_delay=1.0,
            exponential_base=10.0,
            jitter=False,
            max_delay=2.0,
        )
        async def capped_delay():
            raise ConnectionError("Fail")

        with patch("utils.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ConnectionError):
                await capped_delay()

            calls = mock_sleep.call_args_list
            for call in calls:
                assert call[0][0] <= 2.0  # All delays capped at max_delay

    @pytest.mark.asyncio
    async def test_jitter_adds_variation(self):
        """Jitter should add variation to delays."""
        delays = []

        @retry_with_backoff(
            max_retries=10, initial_delay=0.5, jitter=True, exponential_base=1.0  # No growth
        )
        async def jittered_func():
            raise ConnectionError("Fail")

        with patch("utils.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ConnectionError):
                await jittered_func()

            delays = [call[0][0] for call in mock_sleep.call_args_list]
            # With jitter, not all delays should be identical
            # (statistically very unlikely to have all same)
            unique_delays = set(round(d, 4) for d in delays)
            assert len(unique_delays) > 1  # At least some variation

    @pytest.mark.asyncio
    async def test_preserves_function_metadata(self):
        """Decorator should preserve function metadata."""

        @retry_with_backoff(max_retries=1)
        async def documented_func():
            """This is a docstring."""
            return True

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is a docstring."

    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs(self):
        """Function should receive args and kwargs correctly."""

        @retry_with_backoff(max_retries=1)
        async def func_with_args(a, b, c=None):
            return (a, b, c)

        result = await func_with_args(1, 2, c=3)
        assert result == (1, 2, 3)

    @pytest.mark.asyncio
    async def test_zero_retries(self):
        """With max_retries=0, should only try once."""
        call_count = 0

        @retry_with_backoff(max_retries=0)
        async def no_retry_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Fail")

        with pytest.raises(ConnectionError):
            await no_retry_func()
        assert call_count == 1

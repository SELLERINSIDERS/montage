"""Tests for shared retry utility."""

import pytest
import requests
from unittest.mock import MagicMock, patch

from shared.utils.retry import transient_retry, critical_retry, is_transient_error


# --- is_transient_error tests ---


class TestIsTransientError:
    """Test the is_transient_error predicate function."""

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
    def test_transient_http_errors_return_true(self, status_code, mock_response_factory):
        """Transient HTTP status codes should be retryable."""
        resp = mock_response_factory(status_code=status_code)
        exc = requests.exceptions.HTTPError(response=resp)
        assert is_transient_error(exc) is True

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404])
    def test_client_errors_return_false(self, status_code, mock_response_factory):
        """Client HTTP errors should NOT be retried."""
        resp = mock_response_factory(status_code=status_code)
        exc = requests.exceptions.HTTPError(response=resp)
        assert is_transient_error(exc) is False

    def test_connection_error_returns_true(self):
        """ConnectionError is transient and should be retried."""
        exc = requests.exceptions.ConnectionError("Connection refused")
        assert is_transient_error(exc) is True

    def test_timeout_returns_true(self):
        """Timeout is transient and should be retried."""
        exc = requests.exceptions.Timeout("Read timed out")
        assert is_transient_error(exc) is True

    def test_generic_exception_returns_false(self):
        """Non-HTTP exceptions should NOT be retried."""
        exc = ValueError("something wrong")
        assert is_transient_error(exc) is False


# --- transient_retry decorator tests ---


class TestTransientRetry:
    """Test the transient_retry decorator behavior."""

    def test_retries_on_transient_error(self, mock_response_factory):
        """Should retry on 502 and eventually succeed."""
        call_count = 0

        @transient_retry
        def flaky_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                resp = mock_response_factory(status_code=502)
                resp.raise_for_status()
            return "success"

        result = flaky_call()
        assert result == "success"
        assert call_count == 3

    def test_does_not_retry_on_client_error(self, mock_response_factory):
        """Should NOT retry on 400 errors."""
        call_count = 0

        @transient_retry
        def bad_request():
            nonlocal call_count
            call_count += 1
            resp = mock_response_factory(status_code=400)
            resp.raise_for_status()

        with pytest.raises(requests.exceptions.HTTPError):
            bad_request()
        assert call_count == 1

    def test_max_attempts_is_four(self, mock_response_factory):
        """Should stop after 4 attempts."""
        call_count = 0

        @transient_retry
        def always_fails():
            nonlocal call_count
            call_count += 1
            resp = mock_response_factory(status_code=500)
            resp.raise_for_status()

        with pytest.raises(requests.exceptions.HTTPError):
            always_fails()
        assert call_count == 4

    def test_succeeds_without_retry(self):
        """Should pass through on first success."""
        call_count = 0

        @transient_retry
        def works_fine():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert works_fine() == "ok"
        assert call_count == 1


# --- critical_retry decorator tests ---


class TestCriticalRetry:
    """Test the critical_retry decorator behavior."""

    def test_max_attempts_is_five(self, mock_response_factory):
        """critical_retry should stop after 5 attempts."""
        call_count = 0

        @critical_retry
        def always_fails():
            nonlocal call_count
            call_count += 1
            resp = mock_response_factory(status_code=500)
            resp.raise_for_status()

        with pytest.raises(requests.exceptions.HTTPError):
            always_fails()
        assert call_count == 5

    def test_retries_on_connection_error(self):
        """critical_retry should retry on ConnectionError."""
        call_count = 0

        @critical_retry
        def connection_flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.exceptions.ConnectionError("reset")
            return "connected"

        result = connection_flaky()
        assert result == "connected"
        assert call_count == 3


# --- 429 Retry-After header tests ---


class TestRetryAfterHeader:
    """Test that 429 responses with Retry-After header are handled."""

    def test_429_is_transient(self, mock_response_factory):
        """429 Too Many Requests should be retryable."""
        resp = mock_response_factory(status_code=429, headers={"Retry-After": "2"})
        exc = requests.exceptions.HTTPError(response=resp)
        assert is_transient_error(exc) is True

"""Shared test fixtures for VSL Video Framework tests."""

import pytest
import requests


class MockResponse:
    """Factory for mock HTTP responses."""

    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            error = requests.exceptions.HTTPError(
                f"{self.status_code} Error", response=self
            )
            raise error


@pytest.fixture
def mock_response_factory():
    """Return a factory function for creating MockResponse objects."""
    return MockResponse


@pytest.fixture
def mock_transient_responses():
    """Pre-built mock responses for transient HTTP errors."""
    return {
        429: MockResponse(429, headers={"Retry-After": "1"}),
        500: MockResponse(500),
        502: MockResponse(502),
        503: MockResponse(503),
        504: MockResponse(504),
    }


@pytest.fixture
def mock_client_error_responses():
    """Pre-built mock responses for client errors (non-retryable)."""
    return {
        400: MockResponse(400),
        401: MockResponse(401),
        403: MockResponse(403),
        404: MockResponse(404),
    }

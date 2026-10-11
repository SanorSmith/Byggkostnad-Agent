"""Shared retry policy for outbound HTTP calls."""

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


http_retry = retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential_jitter(initial=1, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)

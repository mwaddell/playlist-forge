"""Helpers for honoring API rate-limit responses consistently."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0


def header_value(headers: Mapping[str, object] | None, name: str) -> str | None:
    """Return a header value using case-insensitive name lookup.

    Args:
        headers: Response headers mapping, or None when unavailable.
        name: Header name to resolve.

    Returns:
        The header value as a string when present, otherwise None.
    """
    if not headers:
        return None
    if name in headers:
        value = headers[name]
        return None if value is None else str(value)

    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return None if value is None else str(value)
    return None


def retry_delay_seconds(
    retry_after: str | None,
    attempt: int,
    *,
    default: float = DEFAULT_BACKOFF_SECONDS,
    maximum: float = MAX_BACKOFF_SECONDS,
) -> float:
    """Compute a retry delay from Retry-After or exponential backoff.

    Args:
        retry_after: Retry-After header value as seconds or HTTP-date, if present.
        attempt: Zero-based retry attempt number.
        default: Base delay used for exponential backoff.
        maximum: Maximum allowed delay in seconds.

    Returns:
        Delay in seconds to wait before retrying.
    """
    if retry_after:
        value = retry_after.strip()
        try:
            return max(0.0, min(float(value), maximum))
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
            except (TypeError, ValueError, IndexError):
                pass
            else:
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                seconds = (target - datetime.now(timezone.utc)).total_seconds()
                return max(0.0, min(seconds, maximum))

    return min(default * (2**attempt), maximum)

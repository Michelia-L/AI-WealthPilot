"""Shared business clock: Asia/Shanghai, independent of the API host timezone.

Holdings valuation dates, monitoring as_of dates and IPS save timestamps all
derive from this single clock, so a UTC host (the default Docker image sets
no TZ) cannot split one business day across two calendar dates.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = "Asia/Shanghai"


def business_now() -> datetime:
    """Current timezone-aware time in the business timezone."""
    return datetime.now(ZoneInfo(BUSINESS_TIMEZONE))


def business_today() -> date:
    """Current business calendar date."""
    return business_now().date()

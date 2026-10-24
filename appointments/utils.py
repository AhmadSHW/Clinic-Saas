# appointments/utils.py
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def today_range():
    """
    (start, end) of today in the clinic's local time zone. Use with __range /
    __gte/__lt instead of __date lookups, which return nothing on MySQL unless
    its time zone tables are loaded.
    """
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def parse_scheduled_at(raw):
    """Parses a datetime-local form value into an aware datetime, or None if invalid."""
    try:
        scheduled_at = parse_datetime(raw or "")
    except ValueError:
        return None
    if scheduled_at and timezone.is_naive(scheduled_at):
        scheduled_at = timezone.make_aware(scheduled_at)
    return scheduled_at

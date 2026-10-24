# appointments/utils.py
from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def day_range(day):
    """
    (start, end) of a local calendar date as aware datetimes. Use with
    __gte/__lt instead of __date lookups, which return nothing on MySQL unless
    its time zone tables are loaded.
    """
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    return start, end


def today_range():
    """(start, end) of today in the clinic's local time zone."""
    return day_range(timezone.localdate())


def parse_scheduled_at(raw):
    """Parses a datetime-local form value into an aware datetime, or None if invalid."""
    try:
        scheduled_at = parse_datetime(raw or "")
    except ValueError:
        return None
    if scheduled_at and timezone.is_naive(scheduled_at):
        scheduled_at = timezone.make_aware(scheduled_at)
    return scheduled_at

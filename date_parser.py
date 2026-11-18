import re
from datetime import datetime, date, timedelta
from typing import Optional

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}


def parse_reminder_datetime(date_str: str, time_str: str, tz=None) -> Optional[datetime]:
    """
    Parse date + time strings into a naive local datetime.
    Pass a pytz timezone as `tz` to anchor relative dates to local time.
    Returns None if either part cannot be parsed.
    """
    today = datetime.now(tz).date() if tz else date.today()

    parsed_date = _parse_date(date_str.lower().strip(), today)
    if parsed_date is None:
        return None

    parsed_time = _parse_time(time_str.lower().strip())
    if parsed_time is None:
        return None

    hour, minute = parsed_time
    return datetime(parsed_date.year, parsed_date.month, parsed_date.day, hour, minute, 0)


def _parse_date(s: str, today: date) -> Optional[date]:
    if s == "today":
        return today
    if s in ("tomorrow", "tmrw", "tmr"):
        return today + timedelta(days=1)

    # "next <weekday>"
    m = re.match(r"^next\s+(\w+)$", s)
    if m and m.group(1) in _WEEKDAYS:
        target = _WEEKDAYS[m.group(1)]
        days = (target - today.weekday() + 7) % 7 or 7
        return today + timedelta(days=days)

    # Bare weekday: nearest future occurrence
    if s in _WEEKDAYS:
        target = _WEEKDAYS[s]
        days = (target - today.weekday()) % 7 or 7
        return today + timedelta(days=days)

    # DD/MM or DD/MM/YY(YY)
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?$", s)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        raw_year = m.group(3)
        year = int(raw_year) if raw_year else today.year
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
            if not raw_year and d < today:
                d = date(today.year + 1, month, day)
            return d
        except ValueError:
            return None

    # YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})$", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    # "25 dec" or "dec 25"
    m = re.match(r"^(\d{1,2})\s+([a-z]+)$", s)
    if m and m.group(2) in _MONTHS:
        try:
            d = date(today.year, _MONTHS[m.group(2)], int(m.group(1)))
            if d < today:
                d = date(today.year + 1, _MONTHS[m.group(2)], int(m.group(1)))
            return d
        except ValueError:
            return None

    m = re.match(r"^([a-z]+)\s+(\d{1,2})$", s)
    if m and m.group(1) in _MONTHS:
        try:
            d = date(today.year, _MONTHS[m.group(1)], int(m.group(2)))
            if d < today:
                d = date(today.year + 1, _MONTHS[m.group(1)], int(m.group(2)))
            return d
        except ValueError:
            return None

    return None


def _parse_time(s: str) -> Optional[tuple[int, int]]:
    if s == "noon":
        return (12, 0)
    if s == "midnight":
        return (0, 0)

    # 3pm / 10am
    m = re.match(r"^(\d{1,2})\s*(am|pm)$", s)
    if m:
        h, meridiem = int(m.group(1)), m.group(2)
        if meridiem == "pm" and h != 12:
            h += 12
        elif meridiem == "am" and h == 12:
            h = 0
        if 0 <= h <= 23:
            return (h, 0)

    # 3:30pm / 14:00
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)?$", s)
    if m:
        h, minute = int(m.group(1)), int(m.group(2))
        meridiem = m.group(3)
        if meridiem == "pm" and h != 12:
            h += 12
        elif meridiem == "am" and h == 12:
            h = 0
        if 0 <= h <= 23 and 0 <= minute <= 59:
            return (h, minute)

    # Military 1500
    m = re.match(r"^(\d{2})(\d{2})$", s)
    if m:
        h, minute = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= minute <= 59:
            return (h, minute)

    return None

"""Date expression -> real date range (SPEC §5). The LLM never computes dates; this code does."""

from datetime import date, timedelta

MAX_RANGE_DAYS = 366


class DateResolutionError(Exception):
    def __init__(self, kind: str):  # kind: future | range_too_long | invalid
        super().__init__(kind)
        self.kind = kind


def _parse(text: str | None, today: date) -> date:
    """YYYY-MM-DD, or MM-DD meaning the most recent past occurrence."""
    if not text:
        raise DateResolutionError("invalid")
    parts = text.strip().split("-")
    try:
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            d = date(today.year, int(parts[0]), int(parts[1]))
            return d if d <= today else d.replace(year=today.year - 1)
    except ValueError as exc:
        raise DateResolutionError("invalid") from exc
    raise DateResolutionError("invalid")


def resolve_dates(expression: str, n: int | None, from_date: str | None, to_date: str | None,
                  today: date) -> tuple[date, date]:
    monday = today - timedelta(days=today.weekday())
    first_of_month = today.replace(day=1)
    match expression:
        case "today" | "none":
            start, end = today, today
        case "yesterday":
            start = end = today - timedelta(days=1)
        case "day_before_yesterday":
            start = end = today - timedelta(days=2)
        case "this_week":
            start, end = monday, today
        case "last_week":
            start, end = monday - timedelta(days=7), monday - timedelta(days=1)
        case "this_month":
            start, end = first_of_month, today
        case "last_month":
            end = first_of_month - timedelta(days=1)
            start = end.replace(day=1)
        case "this_year":
            start, end = date(today.year, 1, 1), today
        case "last_n_days":
            if not n or n < 1:
                raise DateResolutionError("invalid")
            if n > MAX_RANGE_DAYS:
                raise DateResolutionError("range_too_long")
            start, end = today - timedelta(days=n - 1), today
        case "specific_date":
            start = end = _parse(from_date, today)
        case "date_range":
            start, end = _parse(from_date, today), _parse(to_date or from_date, today)
            if end < start:
                raise DateResolutionError("invalid")
        case _:
            raise DateResolutionError("invalid")

    if start > today or end > today:
        raise DateResolutionError("future")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise DateResolutionError("range_too_long")
    return start, end

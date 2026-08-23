"""Number-crunching for the analytics widget. Pure, no GTK."""

from datetime import date, datetime, timedelta

from .store import item_counts, next_event, normalize_events


def _day_of(entry):
    try:
        return datetime.fromisoformat(entry["ts"]).astimezone().date()
    except (KeyError, ValueError):
        return None


def per_day(history, days=14, today=None):
    """[(date, count)] for the last ``days`` days, oldest first."""
    today = today or date.today()
    first = today - timedelta(days=days - 1)
    counts = {first + timedelta(days=i): 0 for i in range(days)}
    for entry in history:
        day = _day_of(entry)
        if day is not None and day in counts:
            counts[day] += 1
    return sorted(counts.items())


def done_today(history, today=None):
    today = today or date.today()
    return sum(1 for e in history if _day_of(e) == today)


def done_this_week(history, today=None):
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    return sum(1 for e in history if (d := _day_of(e)) is not None and monday <= d <= today)


def streak(history, today=None):
    """Consecutive days ending today (or yesterday) with at least one tick."""
    days = {d for e in history if (d := _day_of(e)) is not None}
    today = today or date.today()
    start = today if today in days else today - timedelta(days=1)
    if start not in days:
        return 0
    run = 0
    while start in days:
        run += 1
        start -= timedelta(days=1)
    return run


def open_work(notes):
    """[(note, open_items, total_items)] for checklists that still have work,
    most open first."""
    out = []
    for note in notes:
        if note.get("mode") != "list":
            continue
        open_n, done_n = item_counts(note)
        if open_n:
            out.append((note, open_n, open_n + done_n))
    out.sort(key=lambda row: -row[1])
    return out


def recent(history, limit=5):
    return list(reversed(history[-limit:]))


def upcoming_events(notes, limit=3, today=None):
    """[(note, event)] for the next few dates on or after today."""
    today = (today or date.today()).isoformat()
    rows = []
    for note in notes:
        for event in normalize_events(note.get("events")):
            if event["date"] >= today:
                rows.append((note, event))
    rows.sort(key=lambda r: r[1]["date"])
    return rows[:limit]

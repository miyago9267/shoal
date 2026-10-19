"""Multi-week trends built on top of the weekly summary."""

from reports import calendar_utils
from reports.weekly import by_day


def weekly_totals(orders, today, weeks=8):
    """(week_start, revenue) for the last `weeks` full weeks, oldest first."""
    starts = calendar_utils.previous_weeks(today, weeks)
    return [
        (start, round(sum(by_day(orders, start).values()), 2))
        for start in reversed(starts)
    ]


def moving_average(values, window=3):
    """Simple moving average; the first window-1 points are None."""
    out = []
    for index in range(len(values)):
        if index + 1 < window:
            out.append(None)
        else:
            chunk = values[index + 1 - window : index + 1]
            out.append(round(sum(chunk) / float(window), 2))
    return out


def best_and_worst(orders, today, weeks=8):
    """(best_week_start, worst_week_start) by revenue over the window."""
    totals = weekly_totals(orders, today, weeks)
    if not totals:
        return None, None
    best = max(totals, key=lambda pair: pair[1])
    worst = min(totals, key=lambda pair: pair[1])
    return best[0], worst[0]


def growth_streak(orders, today, weeks=8):
    """Number of most recent consecutive weeks with higher revenue than the week before."""
    values = [value for _, value in weekly_totals(orders, today, weeks)]
    streak = 0
    for older, newer in reversed(list(zip(values, values[1:]))):
        if newer > older:
            streak += 1
        else:
            break
    return streak

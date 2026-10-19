"""Plain-text and CSV rendering of the weekly summary."""

from reports import calendar_utils


def money_text(value):
    """12345.5 -> '12,345.50'."""
    return "{:,.2f}".format(value)


def as_text(summary):
    """Multi-line text report."""
    lines = [
        "Week of %s (%s)"
        % (summary["week_start"], calendar_utils.iso_label(summary["week_start"]))
    ]
    for offset, total in sorted(summary["days"].items()):
        lines.append(
            "  %s  %12s" % (calendar_utils.weekday_name(offset), money_text(total))
        )
    lines.append(
        "  total %12s over %d orders"
        % (money_text(summary["sum"]), summary["order_count"])
    )
    if summary["best_day"]:
        lines.append("  best day: %s" % summary["best_day"])
    if summary["wow_percent"] is not None:
        lines.append("  vs last week: %+.1f%%" % summary["wow_percent"])
    for name, share in summary["channels"].items():
        lines.append("  channel %-8s %5.1f%%" % (name, share * 100))
    return "\n".join(lines)


def as_csv(summary):
    """One CSV row per weekday: date offset, weekday, total."""
    rows = ["offset,weekday,total"]
    for offset, total in sorted(summary["days"].items()):
        rows.append("%d,%s,%.2f" % (offset, calendar_utils.weekday_name(offset), total))
    return "\n".join(rows)

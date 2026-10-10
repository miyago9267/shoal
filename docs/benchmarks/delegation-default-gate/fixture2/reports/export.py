"""Scheduled export of the weekly summary to files and a mail body."""

import os

from reports import format as fmt
from reports.weekly import weekly_summary

SUBJECT = "Weekly sales summary {label}"


def build_export(orders, today):
    """Return (subject, text_body, csv_body) for the week containing today."""
    summary = weekly_summary(orders, today)
    from reports import calendar_utils

    label = calendar_utils.iso_label(summary["week_start"])
    return SUBJECT.format(label=label), fmt.as_text(summary), fmt.as_csv(summary)


def write_files(orders, today, directory):
    """Write <label>.txt and <label>.csv into directory; returns the two paths."""
    subject, text, csv = build_export(orders, today)
    label = subject.rsplit(" ", 1)[-1]
    os.makedirs(directory, exist_ok=True)
    paths = []
    for suffix, body in (("txt", text), ("csv", csv)):
        path = os.path.join(directory, "%s.%s" % (label, suffix))
        with open(path, "w") as handle:
            handle.write(body + "\n")
        paths.append(path)
    return paths


def should_send(orders, today):
    """Skip the mail for an empty week so the list does not get noise."""
    return weekly_summary(orders, today)["order_count"] > 0


def recipients(config):
    """Mail recipients from a config dict; blanks and duplicates removed."""
    raw = config.get("report_to", "")
    seen = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    return seen

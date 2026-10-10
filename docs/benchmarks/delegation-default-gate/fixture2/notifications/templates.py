"""Message templates per channel.

A template is a format string using the message fields. Unknown channels fall
back to the plain template so a typo never drops a message silently.
"""

TEMPLATES = {
    "email": "Subject: {subject}\n\n{body}\n\n-- Demo shop",
    "sms": "{body}",
    "push": "{title}: {body}",
    "plain": "[{channel}] {body}",
}

SMS_LIMIT = 160


class MissingField(KeyError):
    """A template needs a field the message does not have."""


def _fields(msg):
    fields = dict(msg)
    fields.setdefault("subject", "Notification")
    fields.setdefault("title", "Notice")
    return fields


def render(msg):
    """Render a message with the template of its channel."""
    template = TEMPLATES.get(msg["channel"], TEMPLATES["plain"])
    try:
        text = template.format(**_fields(msg))
    except KeyError as exc:
        raise MissingField(exc.args[0])
    if msg["channel"] == "sms" and len(text) > SMS_LIMIT:
        text = text[: SMS_LIMIT - 1] + "…"
    return text


def preview(channel, body, **extra):
    """Render without queueing, for the admin preview page."""
    msg = {"channel": channel, "body": body, "to": "preview"}
    msg.update(extra)
    return render(msg)

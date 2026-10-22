"""Remove duplicate orders produced by the exporter's retry logic.

Two rows are the same order when their order id and customer e-mail match,
ignoring case and surrounding whitespace. The first occurrence wins and the
original order of rows is preserved.
"""


def _normalize(order):
    return (order.order_id.strip().lower(), order.customer_email.strip().lower())


def is_duplicate(a, b):
    return _normalize(a) == _normalize(b)


def dedupe_orders(orders):
    unique = []
    for order in orders:
        if not any(is_duplicate(order, kept) for kept in unique):
            unique.append(order)
    return unique

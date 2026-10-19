"""Append-only ledger of posted invoices and payments."""

from decimal import Decimal

from billing.invoice import invoice_total
from billing.rounding import money

ENTRIES = []


class AlreadyPosted(Exception):
    """An invoice id can be posted only once."""


def post_invoice(invoice):
    """Post an invoice; returns the ledger entry."""
    if any(
        e["invoice_id"] == invoice.invoice_id and e["kind"] == "invoice"
        for e in ENTRIES
    ):
        raise AlreadyPosted(invoice.invoice_id)
    totals = invoice_total(invoice)
    entry = {
        "invoice_id": invoice.invoice_id,
        "kind": "invoice",
        "amount": totals.total,
        "memo": "tax %s shipping %s" % (totals.tax, totals.shipping),
    }
    ENTRIES.append(entry)
    return entry


def post_payment(invoice_id, amount):
    """Record a payment against an invoice (a negative balance movement)."""
    entry = {
        "invoice_id": invoice_id,
        "kind": "payment",
        "amount": -money(amount),
        "memo": "payment",
    }
    ENTRIES.append(entry)
    return entry


def balance(invoice_id):
    """Outstanding balance of an invoice (positive = customer owes)."""
    return money(
        sum(
            (e["amount"] for e in ENTRIES if e["invoice_id"] == invoice_id),
            Decimal("0"),
        )
    )


def open_invoices():
    """Invoice ids whose balance is above zero, oldest first."""
    seen = []
    for entry in ENTRIES:
        if entry["invoice_id"] not in seen:
            seen.append(entry["invoice_id"])
    return [i for i in seen if balance(i) > 0]


def reset():
    """Clear the ledger (tests only)."""
    del ENTRIES[:]

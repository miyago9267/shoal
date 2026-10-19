"""Invoice totals.

invoice_total() is the single place that turns order lines into the amount a
customer pays. The steps, in order:

1. line net  : unit price x qty minus the quantity discount (pricing.line_net)
2. promo     : one optional promo code on the subtotal, capped (pricing)
3. allocation: the promo discount is spread over the lines (pricing)
4. tax       : per line on the discounted amount (tax.tax_lines), unless the
               sale is reverse-charge
5. shipping  : flat fee, waived above FREE_SHIPPING_FROM (taxed as standard)
6. total     : discounted lines + tax + shipping, rounded to cents
"""

from dataclasses import dataclass, field
from decimal import Decimal

from billing import pricing, tax
from billing.rounding import money

FLAT_SHIPPING = Decimal("12.00")
FREE_SHIPPING_FROM = Decimal("500.00")


@dataclass
class Invoice:
    invoice_id: str
    lines: list
    region: str = tax.DEFAULT_REGION
    promo: str = None
    buyer_region: str = None
    buyer_has_business_id: bool = False
    notes: list = field(default_factory=list)


@dataclass
class Totals:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal


def shipping_for(discounted_subtotal):
    """Flat shipping, free once the discounted subtotal reaches the threshold."""
    if discounted_subtotal >= FREE_SHIPPING_FROM:
        return Decimal("0.00")
    return FLAT_SHIPPING


def invoice_total(invoice):
    """Compute Totals for an Invoice (see the module docstring for the steps)."""
    lines = invoice.lines
    if not lines:
        zero = money(0)
        return Totals(zero, zero, zero, zero, zero)

    subtotal = pricing.subtotal(lines)
    discount = pricing.promo_discount(invoice.promo, subtotal)
    shares = pricing.spread_discount(lines, discount)
    discounted = [pricing.line_net(line) - share for line, share in zip(lines, shares)]
    discounted_subtotal = money(sum(discounted, Decimal("0")))

    reverse = tax.is_reverse_charge(
        invoice.region,
        invoice.buyer_region or invoice.region,
        invoice.buyer_has_business_id,
    )
    if reverse:
        invoice.notes.append("reverse charge: tax due by the buyer")
    kinds = [line["tax_kind"] for line in lines]
    line_tax = tax.tax_lines(discounted, kinds, invoice.region, exempt=reverse)
    total_tax = money(sum(line_tax, Decimal("0")))

    shipping = shipping_for(discounted_subtotal)
    shipping_tax = Decimal("0.00") if reverse else tax.tax_for(shipping, invoice.region)
    total = money(discounted_subtotal + total_tax + shipping + shipping_tax)
    return Totals(
        subtotal=subtotal,
        discount=discount,
        tax=money(total_tax + shipping_tax),
        shipping=shipping,
        total=total,
    )


def summary_lines(invoice):
    """Printable lines for an invoice, used by the CLI and by the ledger memo."""
    totals = invoice_total(invoice)
    out = [
        "invoice %s (%s)" % (invoice.invoice_id, invoice.region),
        "  subtotal  %10s" % totals.subtotal,
        "  discount  %10s" % totals.discount,
        "  tax       %10s" % totals.tax,
        "  shipping  %10s" % totals.shipping,
        "  total     %10s" % totals.total,
    ]
    out.extend("  note: " + note for note in invoice.notes)
    return out

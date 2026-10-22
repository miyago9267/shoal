# shopcore

Order, pricing and inventory logic for a small shop backend.

- `app/core.py` holds the domain: settings, errors, money helpers,
  validation, models, discounts and tax, inventory, the order service,
  reports and (de)serialisation. Its public names are listed in `__all__`
  and are imported elsewhere as `from app.core import X`.
- `app/catalog.py` loads a product catalog CSV into an `Inventory`.
- `app/api.py` is a JSON-in/JSON-out facade used by the HTTP layer.
- `app/cli.py` prints an invoice for an order JSON file.

All amounts are integer cents. Discounts are pluggable through
`register_discount(name)`; built-in rules are bulk, loyalty and coupon.

Run tests: `python3 -m unittest discover -s tests -t .`

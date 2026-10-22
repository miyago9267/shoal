"""Load a product catalog CSV (``sku,name,price,stock[,taxable]``)."""
import csv
import io

from app.core import Inventory, Product, ValidationError, to_cents


def load_catalog(text, inventory=None):
    inventory = inventory or Inventory()
    reader = csv.DictReader(io.StringIO(text))
    for lineno, row in enumerate(reader, start=2):
        try:
            taxable = row.get("taxable", "yes").strip().lower() not in ("no", "0", "false")
            product = Product(row["sku"].strip(), row["name"].strip(),
                              to_cents(row["price"]), taxable)
            inventory.add_product(product, int(row["stock"]))
        except (KeyError, ValueError) as exc:
            raise ValidationError(f"catalog line {lineno}: {exc}") from exc
    return inventory

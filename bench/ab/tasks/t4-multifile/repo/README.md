# shop

Core checkout helpers shared by the storefront API and the admin tools.

- `shop.cart.add_item(cart, sku, qty)`: add units to a cart line
- `shop.pricing.apply_discount(price_cents, percent)`: percentage discount
- `shop.shipping.shipping_cost(weight_kg, zone)`: zone-based parcel price

All money values are integer cents.

Run tests: `python3 -m unittest discover -s tests -t .`

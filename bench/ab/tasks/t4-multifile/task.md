The checkout helpers in `shop` accept garbage input and either crash with random errors or return
nonsense (a negative quantity, a 150% discount, an unknown shipping zone). Please add input
validation to `add_item` (non-empty string `sku`, `qty` a positive integer), `apply_discount`
(`price_cents` a non-negative integer, `percent` between 0 and 100) and `shipping_cost` (`weight_kg`
a positive number, `zone` one of the known zones). Invalid input should raise one shared
`ValidationError` defined in a new `shop/errors.py`; it should be a subclass of `ValueError` and
expose a `field` attribute holding the name of the offending parameter. Valid input must behave
exactly as it does now.
